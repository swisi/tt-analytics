import re
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from itertools import groupby
from io import BytesIO
from pathlib import Path
import threading
from uuid import uuid4

import markdown as md
from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import or_
from sqlalchemy.orm.exc import ObjectDeletedError
from werkzeug.utils import secure_filename
from weasyprint import HTML

from ..extensions import db
from ..models import AnalysisRun, Clip, ClipAnalysis, ClipMetadata, Game, Report, ReportRun, Season, Team
from ..services.breakdown_import import CANONICAL_BREAKDOWN_COLUMNS, build_breakdown_xlsx_bytes, normalize_breakdown_row, parse_xlsx_rows
from ..services.gemini_analysis import analyze_clip_with_gemini, synthesize_play_by_play_report_with_gemini, synthesize_report_with_gemini

bp = Blueprint("main", __name__)


REPORT_TYPE_LABELS = {
    "multi_game_opponent": "Multi Game Opponent",
    "single_game": "Single Game",
    "self_scout": "Self Scout",
    "play_by_play": "Play by Play",
}




def require_login(endpoint="main.index"):
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=url_for(endpoint)))
    return None


def _normalize_bucket_value(value, bucket_kind):
    raw = str(value or "").strip()
    if not raw:
        return None

    lowered = raw.casefold()
    if lowered in {"null", "none", "n/a", "na", "unknown", "unk", "-", "tbd"}:
        return None

    aliases = {
        "play_type": {
            "run": "Run",
            "pass": "Pass",
            "punt": "Punt",
            "kickoff return": "Kickoff Return",
            "ko rec": "Kickoff Return",
            "kickoff rec": "Kickoff Return",
            "kickoff": "Kickoff",
            "ko": "Kickoff",
            "punt rec": "Punt Return",
            "punt return": "Punt Return",
            "field goal": "Field Goal",
            "fg": "Field Goal",
            "extra point": "Extra Point",
            "pat": "Extra Point",
        },
        "side_of_ball": {
            "offense": "Offense",
            "offensive": "Offense",
            "defense": "Defense",
            "defensive": "Defense",
            "special teams": "Special Teams",
            "specialteam": "Special Teams",
        },
        "formation": {
            "shotgun": "Shotgun",
            "gun": "Shotgun",
            "under center": "Under Center",
            "under-centre": "Under Center",
            "i formation": "I-Formation",
            "i-formation": "I-Formation",
            "pro formation": "Pro Formation",
            "pro-style": "Pro Formation",
            "empty": "Empty",
            "trips": "Trips",
        },
        "front": {
            "4-3": "4-3",
            "4 3": "4-3",
            "43": "4-3",
            "4-man front": "4-Man Front",
            "4 man front": "4-Man Front",
            "four-man front": "4-Man Front",
            "3-4": "3-4",
            "3 4": "3-4",
            "34": "3-4",
            "4-2-5": "4-2-5",
            "4 2 5": "4-2-5",
            "425": "4-2-5",
            "nickel": "Nickel",
            "bear": "Bear",
            "odd": "Odd Front",
            "even": "Even Front",
        },
        "coverage": {
            "zone": "Zone",
            "man": "Man",
            "two-high safety": "Two-High Safety",
            "2 high": "Two-High Safety",
            "two high": "Two-High Safety",
            "cover 2": "Cover 2",
            "cover 3": "Cover 3",
            "cover 4": "Cover 4",
            "quarters": "Quarters",
        },
        "personnel": {
            "11 personnel": "11 Personnel",
            "12 personnel": "12 Personnel",
            "10 personnel": "10 Personnel",
            "21 personnel": "21 Personnel",
            "22 personnel": "22 Personnel",
            "13 personnel": "13 Personnel",
            "20 personnel": "20 Personnel",
            "empty": "Empty",
        },
        "result": {
            "short gain": "Short Gain",
            "positive gain": "Positive Gain",
            "big gain": "Big Gain",
            "touchdown": "Touchdown",
            "tackle for loss": "Tackle For Loss",
            "no gain": "No Gain",
            "incomplete": "Incomplete",
            "interception": "Interception",
            "sack": "Sack",
            "fumble": "Fumble",
        },
        "blitz": {
            "true": "Blitz",
            "false": "No Blitz",
            "yes": "Blitz",
            "no": "No Blitz",
        },
        "pressure": {
            "true": "Pressure",
            "false": "No Pressure",
            "yes": "Pressure",
            "no": "No Pressure",
        },
    }

    if bucket_kind in aliases and lowered in aliases[bucket_kind]:
        return aliases[bucket_kind][lowered]

    if bucket_kind in {"play_type", "side_of_ball", "coverage", "result", "formation", "front", "personnel"}:
        return raw.title()

    return raw[0].upper() + raw[1:] if raw else raw


def _count_bucket(counter, value, bucket_kind):
    normalized = _normalize_bucket_value(value, bucket_kind)
    if normalized:
        counter[normalized] += 1


def _normalize_report_text(text):
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").strip()
    lines = []
    for index, raw_line in enumerate(normalized.splitlines()):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue

        if index == 0 and re.match(r"^#?\s*Scouting\s+", line, flags=re.IGNORECASE):
            continue

        line = re.sub(r"^##\s*\d+\.\s*", "## ", line)
        line = re.sub(r"^\d+\.\s+(Executive Summary|Offense|Defense|Situational Tendencies|Top Coaching Points|Data Gaps / Confidence)$", r"## \1", line, flags=re.IGNORECASE)
        line = re.sub(r"^Analysebasis:\s*", "**Analysebasis:** ", line, flags=re.IGNORECASE)
        line = re.sub(r"^(Allgemeine Offensive Tendenzen|Formationen & Personnel|Blitz & Pressure|Situative Tendenzen)$", r"### \1", line)
        if line == "---":
            lines.append("")
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def _strip_inline_markdown(text):
    clean = text or ""
    clean = re.sub(r"\*\*(.*?)\*\*", r"\1", clean)
    clean = re.sub(r"\*(.*?)\*", r"\1", clean)
    clean = re.sub(r"`(.*?)`", r"\1", clean)
    clean = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean)
    return clean.strip()


def _split_report_sections(text):
    normalized = _normalize_report_text(text)
    sections = []
    current_title = None
    current_lines = []

    for raw_line in normalized.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = _strip_inline_markdown(line[3:])
            current_lines = []
            continue
        current_lines.append(line)

    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))

    return sections


def _safe_int(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _first_non_empty(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _stringify(value, fallback="n/a"):
    if value in (None, ""):
        return fallback
    return str(value).strip() or fallback


def _empty_if_placeholder(value, placeholders=None):
    placeholder_values = {"", None, "n/a", "unknown", "unk", "none", "null", "-", "tbd"}
    if placeholders:
        placeholder_values.update(item.casefold() for item in placeholders if isinstance(item, str))

    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.casefold() in placeholder_values:
        return ""
    return text


def _analysis_first(primary, fallback=None, placeholders=None):
    primary_value = _empty_if_placeholder(primary, placeholders=placeholders)
    if primary_value:
        return primary_value
    return _empty_if_placeholder(fallback, placeholders=placeholders)


def _ordinal_down(value):
    down = _safe_int(value)
    if down == 1:
        return "1st"
    if down == 2:
        return "2nd"
    if down == 3:
        return "3rd"
    if down == 4:
        return "4th"
    return None


def _play_type_for_summary(value):
    normalized = _normalize_bucket_value(value, "play_type")
    if normalized:
        return normalized

    raw = _empty_if_placeholder(value)
    if not raw:
        return None

    aliases = {
        "ko rec": "Kickoff Return",
        "kickoff rec": "Kickoff Return",
        "punt rec": "Punt Return",
        "fg": "Field Goal",
        "pat": "Extra Point",
    }
    return aliases.get(raw.casefold(), raw)


def _build_export_summary(play, breakdown):
    play_type = _play_type_for_summary(breakdown.get("PLAY TYPE") or play.get("play_type"))
    focus_team = _empty_if_placeholder(play.get("focus_team"))
    side_of_ball = _analysis_first(
        "" if play.get("side_of_ball") == "Unknown" else play.get("side_of_ball"),
        breakdown.get("SIDE"),
    )
    result = _analysis_first(
        "" if play.get("result") == "Unknown" else play.get("result"),
        breakdown.get("RESULT"),
    )
    down = _ordinal_down("" if play.get("down") == "n/a" else play.get("down"))
    distance = _analysis_first("" if play.get("distance") == "n/a" else play.get("distance"), breakdown.get("DIST"))
    field_position = _analysis_first(
        "" if play.get("field_position") == "n/a" else play.get("field_position"),
        breakdown.get("YARD LN"),
    )
    play_direction = _analysis_first(_empty_if_placeholder(play.get("play_direction")), breakdown.get("PLAY DIR"))
    yards_gained = play.get("yards_gained")
    if yards_gained is None:
        yards_gained = _safe_int(breakdown.get("YDS")) or _safe_int(breakdown.get("GN/LS"))

    details = []
    if down and distance:
        details.append(f"{down} & {distance}")
    elif down:
        details.append(down)
    if field_position:
        details.append(f"at the {field_position}")

    prefix = ""
    if details:
        prefix = f"{' '.join(details)}: "

    perspective_prefix = ""
    if focus_team and side_of_ball == "Offense":
        perspective_prefix = f"{focus_team} offense "
    elif focus_team and side_of_ball == "Defense":
        perspective_prefix = f"{focus_team} defense "
    elif focus_team and side_of_ball == "Special Teams":
        perspective_prefix = f"{focus_team} special teams "

    if play_type in {"Kickoff", "Kickoff Return", "Punt", "Punt Return", "Field Goal", "Extra Point"}:
        if result and result.casefold() != play_type.casefold():
            return f"{prefix}{perspective_prefix}{play_type}; result: {result}."
        return f"{prefix}{perspective_prefix}{play_type}."

    if play_type:
        fragments = [play_type]
        if play_direction:
            fragments.append(play_direction.lower())
        sentence = " ".join(fragments)
        if result:
            sentence += f", result: {result.lower()}"
        if yards_gained is not None:
            yard_label = "yard" if abs(yards_gained) == 1 else "yards"
            sentence += f" for {yards_gained} {yard_label}"
        return f"{prefix}{perspective_prefix}{sentence}."

    if result:
        return f"{prefix}{perspective_prefix}play result: {result}."

    return ""


def _breakdown_payload_for_analysis(analysis):
    if not analysis.clip:
        return {}
    breakdown = next(
        (item for item in analysis.clip.metadata_entries if item.source_kind == "breakdown_excel"),
        None,
    )
    return normalize_breakdown_row(breakdown.payload_json if breakdown else {})


def _build_play_entry(run, analysis):
    payload = analysis.result_json or {}
    offense = payload.get("offense") or {}
    defense = payload.get("defense") or {}
    outcome = payload.get("outcome") or {}
    breakdown = _breakdown_payload_for_analysis(analysis)

    game_state = payload.get("game_state") or {}
    quarter = _analysis_first(game_state.get("quarter"), breakdown.get("QTR"))
    series = _analysis_first(game_state.get("series"), breakdown.get("SERIES"))
    down = _analysis_first(game_state.get("down"), breakdown.get("DN"))
    distance = _analysis_first(game_state.get("distance"), breakdown.get("DIST"))
    field_position = _analysis_first(game_state.get("yard_line"), breakdown.get("YARD LN"))
    hash_value = _analysis_first(game_state.get("hash"), breakdown.get("HASH"))
    breakdown_play_type = breakdown.get("PLAY TYPE")
    play_number = (
        _safe_int(breakdown.get("PLAY #"))
        or _safe_int(analysis.clip.external_play_number if analysis.clip else None)
        or analysis.clip.clip_number
        or payload.get("play_number")
    )
    yards_gained = outcome.get("yards_gained")
    explosive = isinstance(yards_gained, int) and abs(yards_gained) >= 12
    summary = _analysis_first(payload.get("summary"), breakdown.get("SUMMARY"), placeholders={"Keine Zusammenfassung"})
    play_type = _analysis_first(payload.get("play_type"), breakdown_play_type)
    side_of_ball = _analysis_first(payload.get("side_of_ball"), breakdown.get("SIDE"))
    result = _analysis_first(outcome.get("result"), breakdown.get("RESULT"))
    formation = _analysis_first(offense.get("formation"), breakdown.get("FORMATION"))
    personnel = _analysis_first(offense.get("personnel"), breakdown.get("PERSONNEL"))
    motion = _analysis_first(offense.get("motion"), breakdown.get("MOTION"))
    play_direction = _analysis_first(offense.get("play_direction"), breakdown.get("PLAY DIR"))
    front = _analysis_first(defense.get("front"), breakdown.get("FRONT"))
    coverage = _analysis_first(defense.get("coverage"), breakdown.get("COVERAGE"))
    blitz = _analysis_first(defense.get("blitz"), breakdown.get("BLITZ"))
    pressure = _analysis_first(defense.get("pressure"), breakdown.get("PRESSURE"))
    field_zone = _analysis_first(outcome.get("field_zone"), breakdown.get("FIELD ZONE"))
    situation = _analysis_first(outcome.get("situation"), breakdown.get("SITUATION"))

    return {
        "run_id": run.id,
        "game": run.game.label,
        "game_id": run.game_id,
        "focus_team": run.focus_team.name,
        "analysis_mode": run.analysis_mode,
        "clip_id": analysis.clip.id if analysis.clip else None,
        "clip_number": analysis.clip.clip_number if analysis.clip else None,
        "play_number": play_number,
        "external_play_number": analysis.clip.external_play_number if analysis.clip else None,
        "quarter": _stringify(quarter),
        "quarter_num": _safe_int(quarter) or 99,
        "series": _stringify(series),
        "series_num": _safe_int(series) or 999,
        "down": _stringify(down),
        "down_num": _safe_int(down) or 99,
        "distance": _stringify(distance),
        "field_position": _stringify(field_position),
        "hash": _stringify(hash_value),
        "play_type": _normalize_bucket_value(play_type, "play_type") or "Unknown",
        "side_of_ball": _normalize_bucket_value(side_of_ball, "side_of_ball") or "Unknown",
        "summary": _stringify(summary, fallback="Keine Zusammenfassung"),
        "formation": _normalize_bucket_value(formation, "formation") or "n/a",
        "personnel": _normalize_bucket_value(personnel, "personnel") or "n/a",
        "motion": _stringify(motion),
        "play_direction": _stringify(play_direction),
        "front": _normalize_bucket_value(front, "front") or "n/a",
        "coverage": _normalize_bucket_value(coverage, "coverage") or "n/a",
        "blitz": _normalize_bucket_value(blitz, "blitz") or "n/a",
        "pressure": _normalize_bucket_value(pressure, "pressure") or "n/a",
        "result": _normalize_bucket_value(result, "result") or "Unknown",
        "yards_gained": yards_gained,
        "field_zone": _stringify(field_zone),
        "situation": _stringify(situation),
        "notes": [note.strip() for note in (payload.get("notes") or []) if str(note).strip()],
        "explosive": explosive,
        "breakdown": breakdown,
        "sort_key": (
            _safe_int(quarter) or 99,
            _safe_int(series) or 999,
            _safe_int(play_number) or 9999,
            analysis.clip.clip_number if analysis.clip and analysis.clip.clip_number is not None else 9999,
            analysis.id,
        ),
    }


def _collect_report_plays(report):
    plays = []
    for entry in report.runs:
        run = entry.analysis_run
        for analysis in run.clip_analyses:
            if analysis.status != "completed" or not analysis.result_json:
                continue
            plays.append(_build_play_entry(run, analysis))
    return sorted(plays, key=lambda item: item["sort_key"])


def _build_play_by_play_view(report, plays, request_args=None):
    request_args = request_args or {}
    filters = {
        "quarter": (request_args.get("quarter") or "").strip(),
        "down": (request_args.get("down") or "").strip(),
        "play_type": (request_args.get("play_type") or "").strip(),
        "side": (request_args.get("side") or "").strip(),
    }

    filtered_plays = []
    for play in plays:
        if filters["quarter"] and play["quarter"] != filters["quarter"]:
            continue
        if filters["down"] and play["down"] != filters["down"]:
            continue
        if filters["play_type"] and play["play_type"] != filters["play_type"]:
            continue
        if filters["side"] and play["side_of_ball"] != filters["side"]:
            continue
        filtered_plays.append(play)

    quarter_options = sorted({play["quarter"] for play in plays if play["quarter"] != "n/a"}, key=lambda item: (_safe_int(item) or 99, item))
    down_options = sorted({play["down"] for play in plays if play["down"] != "n/a"}, key=lambda item: (_safe_int(item) or 99, item))
    play_type_options = sorted({play["play_type"] for play in plays if play["play_type"] != "Unknown"})
    side_options = sorted({play["side_of_ball"] for play in plays if play["side_of_ball"] != "Unknown"})

    quarter_counter = Counter(play["quarter"] for play in filtered_plays if play["quarter"] != "n/a")
    result_counter = Counter(play["result"] for play in filtered_plays if play["result"] != "Unknown")
    explosive_count = sum(1 for play in filtered_plays if play["explosive"])
    notes = []
    for play in filtered_plays:
        for note in play["notes"]:
            if note not in notes:
                notes.append(note)
            if len(notes) >= 10:
                break
        if len(notes) >= 10:
            break

    series_summaries = []
    for (quarter, series), group in groupby(filtered_plays, key=lambda item: (item["quarter"], item["series"])):
        grouped = list(group)
        first_play = grouped[0]
        last_play = grouped[-1]
        series_summaries.append(
            {
                "label": f"Q{quarter} · Serie {series}",
                "play_count": len(grouped),
                "start_down": f"{first_play['down']} & {first_play['distance']}",
                "end_result": last_play["result"],
                "top_type": Counter(play["play_type"] for play in grouped).most_common(1)[0][0],
                "explosive_count": sum(1 for play in grouped if play["explosive"]),
                "summary": last_play["summary"],
            }
        )

    quarter_summaries = []
    for quarter, group in groupby(filtered_plays, key=lambda item: item["quarter"]):
        grouped = list(group)
        quarter_summaries.append(
            {
                "quarter": quarter,
                "play_count": len(grouped),
                "top_type": Counter(play["play_type"] for play in grouped).most_common(1)[0][0],
                "top_result": Counter(play["result"] for play in grouped).most_common(1)[0][0],
                "explosive_count": sum(1 for play in grouped if play["explosive"]),
            }
        )

    return {
        "filters": filters,
        "options": {
            "quarter": quarter_options,
            "down": down_options,
            "play_type": play_type_options,
            "side": side_options,
        },
        "plays": filtered_plays,
        "series_summaries": series_summaries,
        "quarter_summaries": quarter_summaries,
        "notes": notes,
        "highlights": {
            "total_plays": len(filtered_plays),
            "total_series": len(series_summaries),
            "explosive_plays": explosive_count,
            "top_quarter": quarter_counter.most_common(1)[0][0] if quarter_counter else "n/a",
            "top_result": result_counter.most_common(1)[0][0] if result_counter else "Unknown",
        },
    }


def _build_breakdown_export_rows(report, plays):
    rows = []
    for play in plays:
        breakdown = normalize_breakdown_row(play.get("breakdown") or {})
        summary = _empty_if_placeholder(play.get("summary"), placeholders={"Keine Zusammenfassung"})
        motion = _empty_if_placeholder(play.get("motion"))
        play_direction = _empty_if_placeholder(play.get("play_direction"))
        yards_gained = play.get("yards_gained")
        export_summary = _build_export_summary(play, breakdown) or _analysis_first(
            summary,
            breakdown.get("SUMMARY"),
            placeholders={"Keine Zusammenfassung"},
        )
        rows.append(
            {
                "PLAY #": breakdown.get("PLAY #") or play.get("external_play_number") or play.get("play_number") or "",
                "QTR": _analysis_first("" if play.get("quarter") == "n/a" else play.get("quarter"), breakdown.get("QTR")),
                "SERIES": _analysis_first("" if play.get("series") == "n/a" else play.get("series"), breakdown.get("SERIES")),
                "DN": _analysis_first("" if play.get("down") == "n/a" else play.get("down"), breakdown.get("DN")),
                "DIST": _analysis_first("" if play.get("distance") == "n/a" else play.get("distance"), breakdown.get("DIST")),
                "HASH": _analysis_first("" if play.get("hash") == "n/a" else play.get("hash"), breakdown.get("HASH")),
                "YARD LN": _analysis_first("" if play.get("field_position") == "n/a" else play.get("field_position"), breakdown.get("YARD LN")),
                "SIDE": _analysis_first("" if play.get("side_of_ball") == "Unknown" else play.get("side_of_ball"), breakdown.get("SIDE")),
                "PLAY TYPE": _analysis_first("" if play.get("play_type") == "Unknown" else play.get("play_type"), breakdown.get("PLAY TYPE")),
                "RESULT": _analysis_first("" if play.get("result") == "Unknown" else play.get("result"), breakdown.get("RESULT")),
                "YDS": yards_gained if yards_gained is not None else _empty_if_placeholder(breakdown.get("YDS")),
                "FORMATION": _analysis_first("" if play.get("formation") == "n/a" else play.get("formation"), breakdown.get("FORMATION")),
                "PERSONNEL": _analysis_first("" if play.get("personnel") == "n/a" else play.get("personnel"), breakdown.get("PERSONNEL")),
                "MOTION": _analysis_first(motion, breakdown.get("MOTION")),
                "PLAY DIR": _analysis_first(play_direction, breakdown.get("PLAY DIR")),
                "FRONT": _analysis_first("" if play.get("front") == "n/a" else play.get("front"), breakdown.get("FRONT")),
                "COVERAGE": _analysis_first("" if play.get("coverage") == "n/a" else play.get("coverage"), breakdown.get("COVERAGE")),
                "BLITZ": _analysis_first("" if play.get("blitz") == "n/a" else play.get("blitz"), breakdown.get("BLITZ")),
                "PRESSURE": _analysis_first("" if play.get("pressure") == "n/a" else play.get("pressure"), breakdown.get("PRESSURE")),
                "SUMMARY": export_summary,
                "CLIP #": play.get("clip_number") or "",
                "GAME": report.title if report.report_type == "self_scout" else play.get("game") or "",
                "FOCUS TEAM": play.get("focus_team") or report.focus_team.name,
                "ANALYSIS MODE": play.get("analysis_mode") or "",
            }
        )
    return rows


def _collect_report_metrics(report):
    plays = _collect_report_plays(report)
    play_types = Counter()
    side_of_ball = Counter()
    formations = Counter()
    personnel = Counter()
    fronts = Counter()
    coverages = Counter()
    blitz = Counter()
    pressure = Counter()
    results = Counter()
    downs = Counter()
    distances = Counter()
    hashes = Counter()
    field_positions = Counter()
    notes = []
    for play in plays:
        _count_bucket(play_types, play["play_type"], "play_type")
        _count_bucket(side_of_ball, play["side_of_ball"], "side_of_ball")
        _count_bucket(formations, play["formation"], "formation")
        _count_bucket(personnel, play["personnel"], "personnel")
        _count_bucket(fronts, play["front"], "front")
        _count_bucket(coverages, play["coverage"], "coverage")
        _count_bucket(blitz, play["blitz"], "blitz")
        _count_bucket(pressure, play["pressure"], "pressure")
        _count_bucket(results, play["result"], "result")
        if play["down"] != "n/a":
            _count_bucket(downs, play["down"], "down")
        if play["distance"] != "n/a":
            _count_bucket(distances, play["distance"], "distance")
        if play["hash"] != "n/a":
            _count_bucket(hashes, play["hash"], "hash")
        if play["field_position"] != "n/a":
            _count_bucket(field_positions, play["field_position"], "yard_line")
        notes.extend(play["notes"])

    return {
        "analyzed_clips": len(plays),
        "top_play_types": play_types.most_common(5),
        "top_sides": side_of_ball.most_common(5),
        "top_formations": formations.most_common(5),
        "top_personnel": personnel.most_common(5),
        "top_fronts": fronts.most_common(5),
        "top_coverages": coverages.most_common(5),
        "top_blitz": blitz.most_common(5),
        "top_pressure": pressure.most_common(5),
        "top_results": results.most_common(5),
        "top_downs": downs.most_common(5),
        "top_distances": distances.most_common(5),
        "top_hashes": hashes.most_common(5),
        "top_field_positions": field_positions.most_common(5),
        "notes": notes[:12],
    }


def _render_report_markdown(text):
    if not text:
        return ""
    text = _normalize_report_text(text)
    return md.markdown(
        text,
        extensions=["extra", "sane_lists", "nl2br"],
    )


def _top_metric_label(rows, fallback="Keine Daten"):
    if not rows:
        return fallback
    return str(rows[0][0])


def _build_report_view_model(report, metrics):
    sections = _split_report_sections(report.summary or "")
    section_map = {title: body for title, body in sections}
    executive_title = "Executive Summary"
    executive_body = section_map.get(executive_title, report.summary or "")
    detail_sections = [
        {
            "title": title,
            "body": body,
            "html": _render_report_markdown(body),
        }
        for title, body in sections
        if title != executive_title and body.strip()
    ]
    executive_html = _render_report_markdown(executive_body)
    if report.report_type == "play_by_play":
        at_a_glance = [
            {
                "title": "Play Flow",
                "value": _top_metric_label(metrics["top_play_types"]),
                "detail": f"Result: {_top_metric_label(metrics['top_results'])}",
            },
            {
                "title": "Defense",
                "value": _top_metric_label(metrics["top_fronts"]),
                "detail": f"Coverage: {_top_metric_label(metrics['top_coverages'])}",
            },
            {
                "title": "Situation",
                "value": _top_metric_label(metrics["top_downs"]),
                "detail": f"Field: {_top_metric_label(metrics['top_field_positions'])}",
            },
        ]
    else:
        at_a_glance = [
            {
                "title": "Offense",
                "value": _top_metric_label(metrics["top_play_types"]),
                "detail": f"Formation: {_top_metric_label(metrics['top_formations'])}",
            },
            {
                "title": "Defense",
                "value": _top_metric_label(metrics["top_fronts"]),
                "detail": f"Coverage: {_top_metric_label(metrics['top_coverages'])}",
            },
            {
                "title": "Situation",
                "value": _top_metric_label(metrics["top_results"]),
                "detail": f"Top Down: {_top_metric_label(metrics['top_downs'])}",
            },
        ]
    return {
        "executive_title": executive_title,
        "executive_html": executive_html,
        "detail_sections": detail_sections,
        "at_a_glance": at_a_glance,
    }


def _build_table_sections(metrics):
    return [
        {"title": "Play Types", "rows": metrics["top_play_types"], "column_title": "Play Type"},
        {"title": "Sides of Ball", "rows": metrics["top_sides"], "column_title": "Side"},
        {"title": "Formations", "rows": metrics["top_formations"], "column_title": "Formation"},
        {"title": "Personnel", "rows": metrics["top_personnel"], "column_title": "Personnel"},
        {"title": "Fronts", "rows": metrics["top_fronts"], "column_title": "Front"},
        {"title": "Coverages", "rows": metrics["top_coverages"], "column_title": "Coverage"},
        {"title": "Blitz Tendencies", "rows": metrics["top_blitz"], "column_title": "Blitz"},
        {"title": "Pressure Tendencies", "rows": metrics["top_pressure"], "column_title": "Pressure"},
        {"title": "Outcomes", "rows": metrics["top_results"], "column_title": "Outcome"},
        {"title": "Down Tendencies", "rows": metrics["top_downs"], "column_title": "Down"},
        {"title": "Distance Tendencies", "rows": metrics["top_distances"], "column_title": "Distance"},
        {"title": "Hash Tendencies", "rows": metrics["top_hashes"], "column_title": "Hash"},
        {"title": "Field Position", "rows": metrics["top_field_positions"], "column_title": "Yard Line"},
    ]


def _build_pdf_response(report, metrics):
    view_model = _build_report_view_model(report, metrics)
    play_view = _build_play_by_play_view(report, _collect_report_plays(report))
    template_name = "report_pdf_play_by_play.html" if report.report_type == "play_by_play" else "report_pdf.html"
    html = render_template(
        template_name,
        report=report,
        metrics=metrics,
        view_model=view_model,
        table_sections=_build_table_sections(metrics),
        play_view=play_view,
        generated_at=datetime.now(),
    )
    pdf_bytes = HTML(string=html, base_url=str(Path(current_app.root_path).parent)).write_pdf()
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", (report.title or f"report_{report.id}").strip()).strip("_")
    filename = f"{safe_title or f'report_{report.id}'}.pdf"

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _build_report_payload(report):
    plays = _collect_report_plays(report)
    completed_play_count = 0
    play_types = Counter()
    sides = Counter()
    formations = Counter()
    personnel = Counter()
    fronts = Counter()
    coverages = Counter()
    blitz = Counter()
    pressure = Counter()
    results = Counter()
    offensive_samples = []
    defensive_samples = []
    situational_samples = []
    down_counts = Counter()
    distance_buckets = Counter()
    hash_counts = Counter()
    field_position_counts = Counter()
    play_by_play_samples = []
    drive_summaries = []
    quarter_summaries = []

    for play in plays:
        completed_play_count += 1
        _count_bucket(play_types, play["play_type"], "play_type")
        _count_bucket(sides, play["side_of_ball"], "side_of_ball")
        _count_bucket(formations, play["formation"], "formation")
        _count_bucket(personnel, play["personnel"], "personnel")
        _count_bucket(fronts, play["front"], "front")
        _count_bucket(coverages, play["coverage"], "coverage")
        _count_bucket(blitz, play["blitz"], "blitz")
        _count_bucket(pressure, play["pressure"], "pressure")
        _count_bucket(results, play["result"], "result")
        if play["down"] != "n/a":
            _count_bucket(down_counts, play["down"], "down")
        if play["distance"] != "n/a":
            _count_bucket(distance_buckets, play["distance"], "distance")
        if play["hash"] != "n/a":
            _count_bucket(hash_counts, play["hash"], "hash")
        if play["field_position"] != "n/a":
            _count_bucket(field_position_counts, play["field_position"], "yard_line")

        sample = {
            "run_id": play["run_id"],
            "game": play["game"],
            "clip_number": play["clip_number"],
            "play_number": play["play_number"],
            "play_type": play["play_type"],
            "side_of_ball": play["side_of_ball"],
            "summary": play["summary"],
            "offense": {
                "formation": play["formation"],
                "personnel": play["personnel"],
                "motion": play["motion"],
                "play_direction": play["play_direction"],
            },
            "defense": {
                "front": play["front"],
                "coverage": play["coverage"],
                "blitz": play["blitz"],
                "pressure": play["pressure"],
            },
            "outcome": {
                "result": play["result"],
                "yards_gained": play["yards_gained"],
                "field_zone": play["field_zone"],
                "situation": play["situation"],
            },
            "breakdown": play["breakdown"],
            "notes": play["notes"],
        }

        side = play["side_of_ball"].lower()
        if "off" in side and len(offensive_samples) < 18:
            offensive_samples.append(sample)
        elif "def" in side and len(defensive_samples) < 18:
            defensive_samples.append(sample)

        if (play["down"] != "n/a" or play["distance"] != "n/a" or play["situation"] != "n/a") and len(situational_samples) < 18:
            situational_samples.append(sample)

        if len(play_by_play_samples) < 80:
            play_by_play_samples.append(
                {
                    "quarter": play["quarter"],
                    "series": play["series"],
                    "play_number": play["play_number"],
                    "down": play["down"],
                    "distance": play["distance"],
                    "field_position": play["field_position"],
                    "play_type": play["play_type"],
                    "side_of_ball": play["side_of_ball"],
                    "result": play["result"],
                    "summary": play["summary"],
                    "explosive": play["explosive"],
                }
            )

    play_view = _build_play_by_play_view(report, plays)
    for summary in play_view["series_summaries"][:20]:
        drive_summaries.append(summary)
    for summary in play_view["quarter_summaries"][:8]:
        quarter_summaries.append(summary)

    return {
        "report_title": report.title,
        "report_type": report.report_type,
        "focus_team": report.focus_team.name,
        "completed_play_count": completed_play_count,
        "top_play_types": play_types.most_common(10),
        "top_sides": sides.most_common(10),
        "top_formations": formations.most_common(10),
        "top_personnel": personnel.most_common(10),
        "top_fronts": fronts.most_common(10),
        "top_coverages": coverages.most_common(10),
        "top_blitz": blitz.most_common(10),
        "top_pressure": pressure.most_common(10),
        "top_results": results.most_common(10),
        "top_downs": down_counts.most_common(10),
        "top_distances": distance_buckets.most_common(10),
        "top_hashes": hash_counts.most_common(10),
        "top_field_positions": field_position_counts.most_common(10),
        "offensive_samples": offensive_samples,
        "defensive_samples": defensive_samples,
        "situational_samples": situational_samples,
        "play_by_play": {
            "completed_play_count": completed_play_count,
            "plays": play_by_play_samples,
            "quarter_summaries": quarter_summaries,
            "series_summaries": drive_summaries,
            "top_play_types": play_types.most_common(10),
            "top_results": results.most_common(10),
            "top_downs": down_counts.most_common(10),
            "top_field_positions": field_position_counts.most_common(10),
        },
    }


@bp.route("/")
def index():
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    stats = {
        "teams": Team.query.count(),
        "games": Game.query.count(),
        "runs": AnalysisRun.query.count(),
        "reports": Report.query.count(),
    }
    recent_games = Game.query.order_by(Game.created_at.desc()).limit(5).all()
    recent_runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).limit(5).all()
    recent_reports = Report.query.order_by(Report.created_at.desc()).limit(5).all()
    return render_template("index.html", stats=stats, recent_games=recent_games, recent_runs=recent_runs, recent_reports=recent_reports)


@bp.route("/health")
def health():
    return {"status": "ok", "service": "tt-analytics"}


def _parse_game_form():
    label = (request.form.get("label") or "").strip()
    season_id = request.form.get("season_id") or None
    own_team_id = request.form.get("own_team_id") or None
    opponent_team_id = request.form.get("opponent_team_id") or None
    source_type = (request.form.get("source_type") or "opponent_film").strip()
    analysis_mode = (request.form.get("analysis_mode") or "opponent_scouting").strip()
    notes = (request.form.get("notes") or "").strip() or None
    game_date_raw = (request.form.get("game_date") or "").strip()

    if not label:
        raise ValueError("Bezeichnung des Spiels ist erforderlich.")

    game_date = None
    if game_date_raw:
        try:
            game_date = datetime.strptime(game_date_raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Ungültiges Datum.") from exc

    return {
        "label": label,
        "season_id": int(season_id) if season_id else None,
        "home_team_id": int(own_team_id) if own_team_id else None,
        "away_team_id": int(opponent_team_id) if opponent_team_id else None,
        "game_date": game_date,
        "source_type": source_type,
        "notes": notes,
    }


def _analyze_clip_for_run(clip, run):
    breakdown = ClipMetadata.query.filter_by(clip_id=clip.id, source_kind="breakdown_excel").first()
    breakdown_payload = breakdown.payload_json if breakdown else None

    analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
    if not analysis:
        analysis = ClipAnalysis(clip_id=clip.id, analysis_run_id=run.id, status="running")
        db.session.add(analysis)
        db.session.commit()
    else:
        analysis.status = "running"
        analysis.error_message = None
        db.session.commit()

    try:
        result = analyze_clip_with_gemini(current_app.config, clip, run, breakdown_payload)
        analysis.provider = result["provider"]
        analysis.model_name = result["model_name"]
        analysis.raw_text = result["raw_text"]
        analysis.result_json = result["result_json"]
        analysis.confidence = result.get("confidence")
        analysis.status = "completed"
        analysis.error_message = None
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        try:
            analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
            if not analysis:
                analysis = ClipAnalysis(clip_id=clip.id, analysis_run_id=run.id)
                db.session.add(analysis)
            analysis.status = "failed"
            analysis.error_message = str(exc)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, str(exc)


def _update_run_counters(run):
    try:
        db.session.rollback()
        run = AnalysisRun.query.get(run.id)
        if not run:
            return
        if run.status == "aborted":
            db.session.commit()
            return
        analyses = ClipAnalysis.query.filter_by(analysis_run_id=run.id).all()
        run.total_clips = len(run.game.clips)
        run.processed_clips = sum(1 for item in analyses if item.status == "completed")
        run.failed_clips = sum(1 for item in analyses if item.status == "failed")
        if run.total_clips and run.processed_clips + run.failed_clips >= run.total_clips:
            run.status = "completed" if run.failed_clips == 0 else "completed_with_errors"
        elif run.processed_clips or run.failed_clips:
            run.status = "running"
        db.session.commit()
    except ObjectDeletedError:
        db.session.rollback()
    except Exception:
        db.session.rollback()
        raise


def _prepare_run_for_restart(run):
    analyses = ClipAnalysis.query.filter_by(analysis_run_id=run.id).all()
    for analysis in analyses:
        if analysis.status != "completed":
            analysis.status = "pending"
            analysis.error_message = None
    db.session.commit()
    _update_run_counters(run)


def _run_analysis_batch(app, run_id):
    with app.app_context():
        try:
            db.session.rollback()
            run = AnalysisRun.query.get(run_id)
            if not run:
                return

            clips = Clip.query.filter_by(game_id=run.game_id).order_by(Clip.clip_number.asc(), Clip.created_at.asc()).all()
            if not clips:
                run.status = "draft"
                db.session.commit()
                return

            concurrency = max(1, int(app.config.get("ANALYSIS_CONCURRENCY", 2)))
            run.status = "running"
            db.session.commit()
            clip_ids = []
            for clip in clips:
                existing_analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
                if existing_analysis and existing_analysis.status == "completed":
                    continue
                clip_ids.append(clip.id)
            _update_run_counters(run)

            def submit_clip(executor, clip_id):
                return executor.submit(_analyze_single_clip_for_run, app, run_id, clip_id)

            with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"analysis-run-{run_id}") as executor:
                in_flight = {}
                clip_iter = iter(clip_ids)

                while True:
                    db.session.rollback()
                    run = AnalysisRun.query.get(run_id)
                    if not run:
                        executor.shutdown(wait=False, cancel_futures=True)
                        return
                    if run.status == "aborted":
                        executor.shutdown(wait=False, cancel_futures=True)
                        return

                    while len(in_flight) < concurrency:
                        try:
                            clip_id = next(clip_iter)
                        except StopIteration:
                            break
                        future = submit_clip(executor, clip_id)
                        in_flight[future] = clip_id

                    if not in_flight:
                        break

                    done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
                    for future in done:
                        in_flight.pop(future, None)
                        try:
                            future.result()
                        except Exception:
                            db.session.rollback()
                    _update_run_counters(run)

            db.session.rollback()
            run = AnalysisRun.query.get(run_id)
            if run and run.status != "aborted":
                _update_run_counters(run)
        except Exception:
            db.session.rollback()
            run = AnalysisRun.query.get(run_id)
            if run:
                run.status = "completed_with_errors"
                db.session.commit()


def _analyze_single_clip_for_run(app, run_id, clip_id):
    with app.app_context():
        try:
            db.session.rollback()
            run = db.session.get(AnalysisRun, run_id)
            clip = db.session.get(Clip, clip_id)
            if not run or not clip or run.status == "aborted":
                return False

            existing_analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
            if existing_analysis and existing_analysis.status == "completed":
                return True

            return _analyze_clip_for_run(clip, run)[0]
        finally:
            db.session.remove()


@bp.route("/teams", methods=["GET", "POST"])
def teams():
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        club_name = (request.form.get("club_name") or "").strip() or None
        is_own_team = request.form.get("is_own_team") == "on"

        if not name:
            flash("Teamname ist erforderlich.", "danger")
            return redirect(url_for("main.teams"))

        existing = Team.query.filter(db.func.lower(Team.name) == name.lower()).first()
        if existing:
            flash("Dieses Team existiert bereits.", "warning")
            return redirect(url_for("main.teams"))

        if is_own_team:
            Team.query.filter_by(is_own_team=True).update({"is_own_team": False})

        db.session.add(Team(name=name, club_name=club_name, is_own_team=is_own_team))
        db.session.commit()
        flash("Team wurde angelegt.", "success")
        return redirect(url_for("main.teams"))

    teams = Team.query.order_by(Team.is_own_team.desc(), Team.name.asc()).all()
    return render_template("teams.html", teams=teams)


@bp.route("/teams/<int:team_id>/edit", methods=["POST"])
def edit_team(team_id):
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    team = Team.query.get_or_404(team_id)
    name = (request.form.get("name") or "").strip()
    club_name = (request.form.get("club_name") or "").strip() or None
    is_own_team = request.form.get("is_own_team") == "on"
    active = request.form.get("active") == "on"

    if not name:
        flash("Teamname ist erforderlich.", "danger")
        return redirect(url_for("main.teams"))

    existing = Team.query.filter(db.func.lower(Team.name) == name.lower(), Team.id != team.id).first()
    if existing:
        flash("Ein anderes Team mit diesem Namen existiert bereits.", "warning")
        return redirect(url_for("main.teams"))

    if is_own_team:
        Team.query.filter(Team.is_own_team.is_(True), Team.id != team.id).update({"is_own_team": False})

    team.name = name
    team.club_name = club_name
    team.is_own_team = is_own_team
    team.active = active
    db.session.commit()
    flash("Team wurde aktualisiert.", "success")
    return redirect(url_for("main.teams"))


@bp.route("/teams/<int:team_id>/delete", methods=["POST"])
def delete_team(team_id):
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    team = Team.query.get_or_404(team_id)
    linked_games = Game.query.filter(
        or_(Game.home_team_id == team.id, Game.away_team_id == team.id)
    ).count()
    linked_runs = AnalysisRun.query.filter_by(focus_team_id=team.id).count()
    if linked_games or linked_runs:
        flash("Dieses Team kann nicht gelöscht werden, weil es noch in Spielen oder Analyse-Runs verwendet wird.", "danger")
        return redirect(url_for("main.teams"))

    db.session.delete(team)
    db.session.commit()
    flash("Team wurde gelöscht.", "success")
    return redirect(url_for("main.teams"))


@bp.route("/games", methods=["GET", "POST"])
def games():
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    teams = Team.query.order_by(Team.is_own_team.desc(), Team.name.asc()).all()
    seasons = Season.query.order_by(Season.year.desc().nullslast(), Season.label.desc()).all()

    if request.method == "POST":
        try:
            game_data = _parse_game_form()
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("main.games"))

        game = Game(**game_data)
        db.session.add(game)
        db.session.commit()
        flash("Spiel wurde angelegt.", "success")
        return redirect(url_for("main.games"))

    games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("games.html", games=games, teams=teams, seasons=seasons)


@bp.route("/games/<int:game_id>/edit", methods=["POST"])
def edit_game(game_id):
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    try:
        game_data = _parse_game_form()
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.games"))

    for key, value in game_data.items():
        setattr(game, key, value)
    db.session.commit()
    flash("Spiel wurde aktualisiert.", "success")
    return redirect(url_for("main.games"))


@bp.route("/games/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    if AnalysisRun.query.filter_by(game_id=game.id).count():
        flash("Dieses Spiel kann nicht gelöscht werden, solange Analyse-Runs dafür existieren.", "danger")
        return redirect(url_for("main.games"))
    if Clip.query.filter_by(game_id=game.id).count():
        flash("Dieses Spiel kann nicht gelöscht werden, solange Clips dafür existieren.", "danger")
        return redirect(url_for("main.games"))
    db.session.delete(game)
    db.session.commit()
    flash("Spiel wurde gelöscht.", "success")
    return redirect(url_for("main.games"))


@bp.route("/runs", methods=["GET", "POST"])
def runs():
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    games = Game.query.order_by(Game.game_date.desc().nullslast(), Game.created_at.desc()).all()

    if request.method == "POST":
        game_id = request.form.get("game_id") or None
        focus_team_id = request.form.get("focus_team_id") or None
        analysis_mode = (request.form.get("analysis_mode") or "opponent_scouting").strip()
        notes = (request.form.get("notes") or "").strip() or None
        start_now = request.form.get("start_now") == "on"

        if not game_id or not focus_team_id:
            flash("Spiel und Fokus-Team sind erforderlich.", "danger")
            return redirect(url_for("main.runs"))

        run = AnalysisRun(
            game_id=int(game_id),
            focus_team_id=int(focus_team_id),
            analysis_mode=analysis_mode,
            status="running" if start_now else "draft",
            notes=notes,
        )
        db.session.add(run)
        db.session.commit()

        if start_now:
            app = current_app._get_current_object()
            worker = threading.Thread(target=_run_analysis_batch, args=(app, run.id), daemon=True)
            worker.start()
            flash("Analyse-Run wurde angelegt und im Hintergrund gestartet.", "success")
        else:
            flash("Analyse-Run wurde angelegt.", "success")
        return redirect(url_for("main.runs"))

    runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).all()
    return render_template("runs.html", runs=runs, games=games)


@bp.route("/runs/<int:run_id>/delete", methods=["POST"])
def delete_run(run_id):
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    run = AnalysisRun.query.get_or_404(run_id)
    linked_report = ReportRun.query.filter_by(analysis_run_id=run.id).first()
    if linked_report:
        flash("Dieser Analyse-Run kann nicht gelöscht werden, weil er bereits in einem Report verwendet wird.", "danger")
        return redirect(url_for("main.runs"))

    db.session.delete(run)
    db.session.commit()
    flash("Analyse-Run wurde gelöscht.", "success")
    return redirect(url_for("main.runs"))


@bp.route("/reports", methods=["GET", "POST"])
def reports():
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    available_runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).all()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        report_type = (request.form.get("report_type") or "multi_game_opponent").strip()
        selected_run_ids = [value for value in request.form.getlist("run_ids") if value]

        if not title:
            flash("Titel ist erforderlich.", "danger")
            return redirect(url_for("main.reports"))
        if not selected_run_ids:
            flash("Mindestens ein Analyse-Run muss gewählt werden.", "danger")
            return redirect(url_for("main.reports"))

        selected_runs = AnalysisRun.query.filter(AnalysisRun.id.in_([int(v) for v in selected_run_ids])).all()
        focus_team_ids = {run.focus_team_id for run in selected_runs}
        if len(focus_team_ids) != 1:
            flash("Alle gewählten Runs müssen dasselbe Fokus-Team haben.", "danger")
            return redirect(url_for("main.reports"))
        if report_type == "play_by_play":
            game_ids = {run.game_id for run in selected_runs}
            if len(selected_runs) != 1 or len(game_ids) != 1:
                flash("Ein Play-by-Play-Report muss genau auf einem Analyse-Run für ein Spiel basieren.", "danger")
                return redirect(url_for("main.reports"))

        focus_team = selected_runs[0].focus_team
        summary_lines = [
            f"Fokus-Team: {focus_team.name}",
            f"Analyse-Runs: {len(selected_runs)}",
            f"Grundlage: " + ", ".join(run.game.label for run in selected_runs),
        ]
        if report_type == "play_by_play":
            summary_lines.append("Format: Chronologische Play-by-Play-Analyse mit Drive-/Situationsfokus")
        report = Report(
            title=title,
            report_type=report_type,
            focus_team_id=focus_team.id,
            status="draft",
            summary="\n".join(summary_lines),
        )
        db.session.add(report)
        db.session.flush()

        for run in selected_runs:
            db.session.add(ReportRun(report_id=report.id, analysis_run_id=run.id))

        db.session.commit()
        flash("Report wurde angelegt.", "success")
        return redirect(url_for("main.reports"))

    filters = {
        "query": (request.args.get("query") or "").strip(),
        "report_type": (request.args.get("report_type") or "").strip(),
        "focus_team_id": (request.args.get("focus_team_id") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "sort": (request.args.get("sort") or "newest").strip(),
    }

    reports_query = Report.query

    if filters["query"]:
        search_term = f"%{filters['query']}%"
        reports_query = reports_query.filter(Report.title.ilike(search_term))
    if filters["report_type"]:
        reports_query = reports_query.filter(Report.report_type == filters["report_type"])
    if filters["focus_team_id"].isdigit():
        reports_query = reports_query.filter(Report.focus_team_id == int(filters["focus_team_id"]))
    if filters["status"]:
        reports_query = reports_query.filter(Report.status == filters["status"])

    sort_key = filters["sort"]
    if sort_key == "oldest":
        reports_query = reports_query.order_by(Report.created_at.asc())
    elif sort_key == "title_asc":
        reports_query = reports_query.order_by(Report.title.asc(), Report.created_at.desc())
    elif sort_key == "title_desc":
        reports_query = reports_query.order_by(Report.title.desc(), Report.created_at.desc())
    else:
        reports_query = reports_query.order_by(Report.created_at.desc())

    reports = reports_query.all()
    focus_teams = Team.query.join(Report, Report.focus_team_id == Team.id).distinct().order_by(Team.name.asc()).all()
    statuses = [value[0] for value in db.session.query(Report.status).distinct().order_by(Report.status.asc()).all() if value[0]]
    return render_template(
        "reports.html",
        reports=reports,
        available_runs=available_runs,
        filters=filters,
        focus_teams=focus_teams,
        statuses=statuses,
        report_type_labels=REPORT_TYPE_LABELS,
    )


@bp.route("/reports/<int:report_id>")
def report_detail(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    metrics = _collect_report_metrics(report)
    view_model = _build_report_view_model(report, metrics)
    play_view = _build_play_by_play_view(report, _collect_report_plays(report), request.args)
    active_tab = (request.args.get("tab") or "").strip().lower()
    if active_tab not in {"overview", "play_by_play"}:
        active_tab = "play_by_play" if report.report_type == "play_by_play" else "overview"
    return render_template(
        "report_detail.html",
        report=report,
        metrics=metrics,
        view_model=view_model,
        play_view=play_view,
        active_tab=active_tab,
        report_type_labels=REPORT_TYPE_LABELS,
    )


@bp.route("/reports/<int:report_id>/pdf")
def report_pdf(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    metrics = _collect_report_metrics(report)
    return _build_pdf_response(report, metrics)


@bp.route("/reports/<int:report_id>/breakdown.xlsx")
def report_breakdown_xlsx(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    plays = _collect_report_plays(report)
    rows = _build_breakdown_export_rows(report, plays)
    workbook = build_breakdown_xlsx_bytes(rows, headers=CANONICAL_BREAKDOWN_COLUMNS)
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "_", (report.title or f"report_{report.id}").strip()).strip("_")
    filename = f"{safe_title or f'report_{report.id}'}_breakdown.xlsx"
    return send_file(
        BytesIO(workbook),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/reports/<int:report_id>/generate", methods=["POST"])
def generate_report(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    payload = _build_report_payload(report)
    play_count = payload["completed_play_count"]
    if play_count == 0:
        flash("Für diesen Report liegen noch keine fertigen Clip-Analysen vor.", "warning")
        return redirect(url_for("main.report_detail", report_id=report.id))

    try:
        report.status = "generating"
        db.session.commit()

        if report.report_type == "play_by_play":
            result = synthesize_play_by_play_report_with_gemini(current_app.config, report, payload["play_by_play"])
        else:
            result = synthesize_report_with_gemini(current_app.config, report, payload)
        report.summary = result["report_text"]
        report.status = "completed"
        db.session.commit()
        flash(f"AI-Report wurde aus {play_count} Play-Analysen generiert.", "success")
    except Exception as exc:
        db.session.rollback()
        report = Report.query.get(report_id)
        if report:
            report.status = "draft"
            db.session.commit()
        flash(f"Report-Generierung fehlgeschlagen: {exc}", "danger")

    return redirect(url_for("main.report_detail", report_id=report_id))


@bp.route("/reports/<int:report_id>/delete", methods=["POST"])
def delete_report(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("Report wurde gelöscht.", "success")
    return redirect(url_for("main.reports"))


@bp.route("/games/<int:game_id>/clips", methods=["GET", "POST"])
def game_clips(game_id):
    login_redirect = require_login("main.game_clips")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)

    if request.method == "POST":
        uploaded_files = request.files.getlist("clips")
        uploaded_files = [file for file in uploaded_files if file and file.filename]
        if not uploaded_files:
            flash("Bitte mindestens eine Clip-Datei auswählen.", "danger")
            return redirect(url_for("main.game_clips", game_id=game.id))

        upload_root = Path(current_app.config["UPLOAD_ROOT"])
        game_dir = upload_root / f"game_{game.id}"
        game_dir.mkdir(parents=True, exist_ok=True)

        max_clip_number = db.session.query(db.func.max(Clip.clip_number)).filter_by(game_id=game.id).scalar() or 0

        created = 0
        for index, file in enumerate(uploaded_files, start=1):
            original_name = secure_filename(file.filename) or f"clip_{uuid4().hex}.mp4"
            unique_name = f"{uuid4().hex}_{original_name}"
            target = game_dir / unique_name
            file.save(target)

            clip = Clip(
                game_id=game.id,
                clip_number=max_clip_number + index,
                original_filename=original_name,
                stored_filename=unique_name,
                storage_path=str(target),
                content_type=file.content_type,
                file_size_bytes=target.stat().st_size if target.exists() else None,
                status="uploaded",
            )
            db.session.add(clip)
            created += 1

        db.session.commit()
        flash(f"{created} Clip(s) wurden hochgeladen.", "success")
        return redirect(url_for("main.game_clips", game_id=game.id))

    clips = Clip.query.filter_by(game_id=game.id).order_by(Clip.clip_number.asc(), Clip.created_at.asc()).all()
    runs = AnalysisRun.query.filter_by(game_id=game.id).order_by(AnalysisRun.created_at.desc()).all()
    return render_template("clips.html", game=game, clips=clips, runs=runs)


@bp.route("/games/<int:game_id>/breakdown", methods=["POST"])
def import_breakdown(game_id):
    login_redirect = require_login("main.game_clips")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    upload = request.files.get("breakdown_file")
    if not upload or not upload.filename:
        flash("Bitte eine Breakdown-Datei auswählen.", "danger")
        return redirect(url_for("main.game_clips", game_id=game.id))

    try:
        rows = parse_xlsx_rows(upload.read())
    except Exception:
        flash("Breakdown-Datei konnte nicht gelesen werden.", "danger")
        return redirect(url_for("main.game_clips", game_id=game.id))

    matched = 0
    unmatched = 0

    for row in rows:
        normalized_row = normalize_breakdown_row(row)
        play_number = str(normalized_row.get("PLAY #", "")).strip()
        if not play_number:
            unmatched += 1
            continue

        clip_number = _safe_int(play_number)
        clip = Clip.query.filter_by(game_id=game.id, clip_number=clip_number if clip_number is not None else None).first()
        if not clip:
            clip = Clip.query.filter_by(game_id=game.id, external_play_number=play_number).first()
        if not clip:
            unmatched += 1
            continue

        clip.external_play_number = play_number
        metadata = ClipMetadata.query.filter_by(clip_id=clip.id, source_kind="breakdown_excel").first()
        if not metadata:
            metadata = ClipMetadata(clip_id=clip.id, source_kind="breakdown_excel", payload_json=normalized_row)
            db.session.add(metadata)
        else:
            metadata.payload_json = normalized_row
        matched += 1

    db.session.commit()
    flash(f"Breakdown importiert: {matched} Play(s) zugeordnet, {unmatched} ohne Zuordnung.", "success" if matched else "warning")
    return redirect(url_for("main.game_clips", game_id=game.id))


@bp.route("/clips/<int:clip_id>/delete", methods=["POST"])
def delete_clip(clip_id):
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    clip = Clip.query.get_or_404(clip_id)
    clip_path = Path(clip.storage_path)
    game_id = clip.game_id
    if clip_path.exists():
        clip_path.unlink()
    db.session.delete(clip)
    db.session.commit()
    flash("Clip wurde gelöscht.", "success")
    return redirect(url_for("main.game_clips", game_id=game_id))


@bp.route("/clips/<int:clip_id>/analyze", methods=["POST"])
def analyze_clip(clip_id):
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    clip = Clip.query.get_or_404(clip_id)
    run_id = request.form.get("run_id")
    if not run_id:
        flash("Bitte einen Analyse-Run auswählen.", "danger")
        return redirect(url_for("main.game_clips", game_id=clip.game_id))

    run = AnalysisRun.query.get_or_404(int(run_id))
    if run.game_id != clip.game_id:
        flash("Der gewählte Analyse-Run gehört nicht zu diesem Spiel.", "danger")
        return redirect(url_for("main.game_clips", game_id=clip.game_id))

    ok, error = _analyze_clip_for_run(clip, run)
    _update_run_counters(run)
    if ok:
        flash("Clip wurde durch Gemini analysiert.", "success")
    else:
        flash(f"Clip-Analyse fehlgeschlagen: {error}", "danger")

    return redirect(url_for("main.game_clips", game_id=clip.game_id))


@bp.route("/runs/<int:run_id>/analyze", methods=["POST"])
def analyze_run(run_id):
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    run = AnalysisRun.query.get_or_404(run_id)
    clips_exist = Clip.query.filter_by(game_id=run.game_id).first()
    if not clips_exist:
        flash("Dieses Spiel hat noch keine Clips.", "warning")
        return redirect(url_for("main.runs"))

    _prepare_run_for_restart(run)
    run.status = "queued"
    db.session.commit()

    app = current_app._get_current_object()
    worker = threading.Thread(target=_run_analysis_batch, args=(app, run.id), daemon=True)
    worker.start()
    flash(f"Run {run.id} wurde im Hintergrund gestartet.", "success")
    return redirect(url_for("main.runs"))
