import json
import re
import time
from pathlib import Path

from google import genai


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "play_number": {"type": ["integer", "null"]},
        "focus_team": {"type": "string"},
        "side_of_ball": {"type": "string"},
        "play_type": {"type": "string"},
        "summary": {"type": "string"},
        "game_state": {
            "type": "object",
            "properties": {
                "quarter": {"type": ["integer", "null"]},
                "series": {"type": ["integer", "null"]},
                "down": {"type": ["integer", "null"]},
                "distance": {"type": ["integer", "null"]},
                "yard_line": {"type": ["string", "null"]},
                "hash": {"type": ["string", "null"]},
                "situation": {"type": ["string", "null"]},
                "two_minute": {"type": ["boolean", "null"]},
            },
            "required": ["quarter", "series", "down", "distance", "yard_line", "hash", "situation", "two_minute"],
        },
        "offense": {
            "type": "object",
            "properties": {
                "personnel": {"type": ["string", "null"]},
                "formation": {"type": ["string", "null"]},
                "motion": {"type": ["string", "null"]},
                "play_direction": {"type": ["string", "null"]},
            },
            "required": ["personnel", "formation", "motion", "play_direction"],
        },
        "defense": {
            "type": "object",
            "properties": {
                "front": {"type": ["string", "null"]},
                "coverage": {"type": ["string", "null"]},
                "blitz": {"type": ["boolean", "null"]},
                "pressure": {"type": ["boolean", "null"]},
            },
            "required": ["front", "coverage", "blitz", "pressure"],
        },
        "outcome": {
            "type": "object",
            "properties": {
                "result": {"type": ["string", "null"]},
                "yards_gained": {"type": ["integer", "null"]},
                "field_zone": {"type": ["string", "null"]},
                "situation": {"type": ["string", "null"]},
            },
            "required": ["result", "yards_gained", "field_zone", "situation"],
        },
        "hudl_fields": {
            "type": "object",
            "properties": {
                "odk": {"type": ["string", "null"]},
                "off_form": {"type": ["string", "null"]},
                "def_front": {"type": ["string", "null"]},
                "gain_loss": {"type": ["integer", "null"]},
                "motion_dir": {"type": ["string", "null"]},
                "result_label": {"type": ["string", "null"]},
            },
            "required": ["odk", "off_form", "def_front", "gain_loss", "motion_dir", "result_label"],
        },
        "confidence": {"type": "number"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "play_number",
        "focus_team",
        "side_of_ball",
        "play_type",
        "summary",
        "game_state",
        "offense",
        "defense",
        "outcome",
        "hudl_fields",
        "confidence",
        "notes",
    ],
}


def _get_client_and_model(config):
    api_key = (config.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt.")
    return genai.Client(api_key=api_key), config.get("GEMINI_MODEL", "gemini-2.5-flash")


def _build_prompt(clip, analysis_run, breakdown_payload):
    game = analysis_run.game
    focus_team = analysis_run.focus_team.name
    home_team = game.home_team.name if game.home_team else "Unknown"
    away_team = game.away_team.name if game.away_team else "Unknown"

    prompt = f"""
You are an American Football video analyst.

Analyze the attached clip as one play from the game "{game.label}".
Game teams:
- Home team: {home_team}
- Away team: {away_team}

Focus team for this analysis:
- {focus_team}

Analysis mode:
- {analysis_run.analysis_mode}

Important rules:
- Return only JSON that matches the provided schema.
- If something is unclear from the video, set the field to null and mention uncertainty in notes.
- Prefer observations from the video over spreadsheet context if they conflict.
- Keep the summary short and coach-friendly.
- Prioritize a practical tagging output that can later be exported into a Hudl-style playlist sheet.
- QTR and outcome.result are especially important. Fill them when they are visible or directly inferable from the clip context; otherwise leave them null.
""".strip()

    if analysis_run.analysis_mode == "play_by_play":
        prompt += "\n\n" + """

For play_by_play mode:
- Prioritize exact situational context, sequence order and immediate outcome of this specific play.
- Keep the summary factual and event-driven instead of trend-oriented.
- Add notes only for directly relevant coaching or execution details.
- Populate game_state as completely as the video allows without guessing.
- Use hudl_fields as export-ready aliases for the most useful playlist columns.
""".strip()

    if breakdown_payload:
        prompt += "\n\nAdditional play-by-play context from breakdown.xlsx (may be incomplete or partially wrong):\n"
        for key, value in breakdown_payload.items():
            if value not in ("", None):
                prompt += f"- {key}: {value}\n"

    prompt += "\n\n" + """
Field guidance:
- game_state.quarter: integer quarter number, or null if not visible.
- game_state.series: possession/drive number only if you can determine it with confidence.
- game_state.down: integer down, or null.
- game_state.distance: yards to gain as integer, or null.
- game_state.yard_line: preserve the broadcast/charting style if visible, for example "-15", "45", "Own 25", or null.
- game_state.hash: use "L", "M", "R" when visible; otherwise null.
- side_of_ball: "Offense", "Defense", or "Special Teams".
- play_type: short coach-friendly tag such as "Run", "Pass", "Punt", "Kickoff Return", "Punt Return", "Field Goal".
- outcome.result: concise football result such as "Completion", "Incomplete", "Touchdown", "First Down", "Short Gain", "Tackle For Loss", "Sack", "Kickoff Return".
- outcome.yards_gained: signed integer when visible or directly inferable, else null.
- offense.formation and hudl_fields.off_form should usually match.
- defense.front and hudl_fields.def_front should usually match.
- hudl_fields.odk: use Hudl-style one-letter code where possible: "O" offense, "D" defense, "K" kicking game / special teams.
- hudl_fields.gain_loss: signed integer mirror of outcome.yards_gained when known.
- hudl_fields.result_label: short export label aligned with outcome.result.
- Never invent player names, jersey numbers, or drive numbers.
""".strip()

    return prompt


def _is_retryable_rate_limit(error_text):
    normalized = (error_text or "").upper()
    return "429" in normalized or "RESOURCE_EXHAUSTED" in normalized


def _parse_retry_seconds(error_text, config):
    match = re.search(r"retry in ([0-9.]+)s", error_text or "", re.IGNORECASE)
    base_wait = float(config.get("GEMINI_RETRY_DEFAULT_SECONDS", 60))
    if match:
        base_wait = float(match.group(1))
    buffer_seconds = float(config.get("GEMINI_RETRY_BUFFER_SECONDS", 5))
    return max(1.0, base_wait + buffer_seconds)


def _generate_with_retry(client, model_name, contents, config, generation_config=None):
    max_retries = int(config.get("GEMINI_MAX_RETRIES", 8))
    for attempt in range(max_retries + 1):
        try:
            return client.models.generate_content(
                model=model_name,
                contents=contents,
                config=generation_config,
            )
        except Exception as exc:
            error_text = str(exc)
            if attempt >= max_retries or not _is_retryable_rate_limit(error_text):
                raise
            time.sleep(_parse_retry_seconds(error_text, config))
    raise RuntimeError("Gemini-Generierung konnte nicht abgeschlossen werden.")


def _first_breakdown_value(payload, keys):
    for key in keys:
        value = (payload or {}).get(key)
        if value not in ("", None):
            return value
    return None


def _get_nested(mapping, path):
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _set_nested(mapping, path, value):
    current = mapping
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _is_missing_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"", "null", "none", "n/a", "na", "unknown", "-", "tbd"}
    return False


def _coerce_int(value):
    if _is_missing_value(value):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def _coerce_bool(value):
    if _is_missing_value(value):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    truthy = {"true", "yes", "y", "1", "blitz", "pressure"}
    falsy = {"false", "no", "n", "0", "no blitz", "no pressure"}
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    return None


def _coerce_string(value):
    if _is_missing_value(value):
        return None
    text = str(value).strip()
    return text or None


def _coerce_value(value, kind):
    if kind == "int":
        return _coerce_int(value)
    if kind == "bool":
        return _coerce_bool(value)
    return _coerce_string(value)


def _normalize_for_compare(value, kind):
    coerced = _coerce_value(value, kind)
    if coerced is None:
        return None
    if kind == "string":
        return str(coerced).strip().casefold()
    return coerced


def _breakdown_odk_to_focus_value(raw_odk, analysis_run, output_kind="odk"):
    odk = _coerce_string(raw_odk)
    if not odk:
        return None

    normalized = odk.strip().upper()
    if normalized.startswith("K"):
        return "K" if output_kind == "odk" else "Special Teams"

    game = analysis_run.game if analysis_run else None
    focus_team = analysis_run.focus_team if analysis_run else None
    home_team = game.home_team if game else None
    focus_is_home = bool(focus_team and home_team and focus_team.id == home_team.id)

    if normalized.startswith("O"):
        if output_kind == "odk":
            return "O" if focus_is_home else "D"
        return "Offense" if focus_is_home else "Defense"

    if normalized.startswith("D"):
        if output_kind == "odk":
            return "D" if focus_is_home else "O"
        return "Defense" if focus_is_home else "Offense"

    return None


def _resolve_breakdown_value(spec, breakdown_payload, analysis_run):
    if spec["name"] == "side_of_ball":
        explicit_side = _first_breakdown_value(breakdown_payload, ("SIDE",))
        if explicit_side not in ("", None):
            return _coerce_value(explicit_side, spec["kind"])
        return _breakdown_odk_to_focus_value(
            _first_breakdown_value(breakdown_payload, ("ODK",)),
            analysis_run,
            output_kind="side_of_ball",
        )

    if spec["name"] == "odk":
        return _breakdown_odk_to_focus_value(
            _first_breakdown_value(breakdown_payload, ("ODK",)),
            analysis_run,
            output_kind="odk",
        )

    breakdown_raw = _first_breakdown_value(breakdown_payload, spec["keys"])
    return _coerce_value(breakdown_raw, spec["kind"])


def _apply_breakdown_fallbacks(result, breakdown_payload, analysis_run=None):
    breakdown_payload = breakdown_payload or {}
    field_specs = [
        {"name": "play_type", "path": ("play_type",), "keys": ("PLAY TYPE",), "kind": "string"},
        {"name": "side_of_ball", "path": ("side_of_ball",), "keys": ("SIDE",), "kind": "string"},
        {"name": "summary", "path": ("summary",), "keys": ("SUMMARY",), "kind": "string"},
        {"name": "quarter", "path": ("game_state", "quarter"), "keys": ("QTR",), "kind": "int"},
        {"name": "series", "path": ("game_state", "series"), "keys": ("SERIES",), "kind": "int"},
        {"name": "down", "path": ("game_state", "down"), "keys": ("DN",), "kind": "int"},
        {"name": "distance", "path": ("game_state", "distance"), "keys": ("DIST",), "kind": "int"},
        {"name": "yard_line", "path": ("game_state", "yard_line"), "keys": ("YARD LN",), "kind": "string"},
        {"name": "hash", "path": ("game_state", "hash"), "keys": ("HASH",), "kind": "string"},
        {"name": "situation", "path": ("game_state", "situation"), "keys": ("SITUATION",), "kind": "string"},
        {"name": "odk", "path": ("hudl_fields", "odk"), "keys": ("ODK",), "kind": "string"},
        {"name": "formation", "path": ("offense", "formation"), "keys": ("FORMATION", "OFF FORM"), "kind": "string"},
        {"name": "personnel", "path": ("offense", "personnel"), "keys": ("PERSONNEL",), "kind": "string"},
        {"name": "motion", "path": ("offense", "motion"), "keys": ("MOTION",), "kind": "string"},
        {"name": "play_direction", "path": ("offense", "play_direction"), "keys": ("PLAY DIR",), "kind": "string"},
        {"name": "front", "path": ("defense", "front"), "keys": ("FRONT", "DEF FRONT"), "kind": "string"},
        {"name": "coverage", "path": ("defense", "coverage"), "keys": ("COVERAGE",), "kind": "string"},
        {"name": "blitz", "path": ("defense", "blitz"), "keys": ("BLITZ",), "kind": "bool"},
        {"name": "pressure", "path": ("defense", "pressure"), "keys": ("PRESSURE",), "kind": "bool"},
        {"name": "result", "path": ("outcome", "result"), "keys": ("RESULT",), "kind": "string"},
        {"name": "yards_gained", "path": ("outcome", "yards_gained"), "keys": ("YDS", "GN/LS"), "kind": "int"},
        {"name": "field_zone", "path": ("outcome", "field_zone"), "keys": ("FLD ZN",), "kind": "string"},
        {"name": "hudl_off_form", "path": ("hudl_fields", "off_form"), "keys": ("OFF FORM", "FORMATION"), "kind": "string"},
        {"name": "hudl_def_front", "path": ("hudl_fields", "def_front"), "keys": ("DEF FRONT", "FRONT"), "kind": "string"},
        {"name": "hudl_gain_loss", "path": ("hudl_fields", "gain_loss"), "keys": ("GN/LS", "YDS"), "kind": "int"},
        {"name": "hudl_motion_dir", "path": ("hudl_fields", "motion_dir"), "keys": ("MOTION DIR",), "kind": "string"},
        {"name": "hudl_result_label", "path": ("hudl_fields", "result_label"), "keys": ("RESULT",), "kind": "string"},
    ]

    comparison_fields = {}
    matched_count = 0
    conflict_count = 0
    fallback_count = 0

    for spec in field_specs:
        analysis_value = _get_nested(result, spec["path"])
        breakdown_value = _resolve_breakdown_value(spec, breakdown_payload, analysis_run)
        analysis_missing = _is_missing_value(analysis_value)
        used_fallback = analysis_missing and breakdown_value is not None

        if used_fallback:
            _set_nested(result, spec["path"], breakdown_value)

        resolved_value = _get_nested(result, spec["path"])
        analysis_normalized = _normalize_for_compare(analysis_value, spec["kind"])
        breakdown_normalized = _normalize_for_compare(breakdown_value, spec["kind"])
        matches = (
            analysis_normalized is not None
            and breakdown_normalized is not None
            and analysis_normalized == breakdown_normalized
        )
        conflict = (
            analysis_normalized is not None
            and breakdown_normalized is not None
            and analysis_normalized != breakdown_normalized
        )

        if matches:
            matched_count += 1
        if conflict:
            conflict_count += 1
        if used_fallback:
            fallback_count += 1

        comparison_fields[spec["name"]] = {
            "analysis": analysis_value,
            "breakdown": breakdown_value,
            "resolved": resolved_value,
            "matches": matches,
            "conflict": conflict,
            "used_fallback": used_fallback,
        }

    result["breakdown_comparison"] = {
        "fields": comparison_fields,
        "summary": {
            "matched_count": matched_count,
            "conflict_count": conflict_count,
            "fallback_count": fallback_count,
        },
    }
    return result


def analyze_clip_with_gemini(config, clip, analysis_run, breakdown_payload):
    clip_path = Path(clip.storage_path)
    if not clip_path.exists():
        raise RuntimeError("Clip-Datei wurde im Upload-Speicher nicht gefunden.")

    client, model_name = _get_client_and_model(config)
    uploaded = client.files.upload(file=str(clip_path))

    deadline = time.time() + int(config.get("GEMINI_FILE_POLL_TIMEOUT_SECONDS", 300))
    poll_seconds = int(config.get("GEMINI_FILE_POLL_SECONDS", 5))

    while not uploaded.state or uploaded.state.name != "ACTIVE":
        if uploaded.state and uploaded.state.name == "FAILED":
            raise RuntimeError("Gemini Files API konnte den Clip nicht verarbeiten.")
        if time.time() >= deadline:
            raise RuntimeError("Timeout beim Warten auf die Verarbeitung des Clips durch Gemini.")
        time.sleep(poll_seconds)
        uploaded = client.files.get(name=uploaded.name)

    prompt = _build_prompt(clip, analysis_run, breakdown_payload)
    response = _generate_with_retry(
        client,
        model_name,
        [uploaded, prompt],
        config,
        generation_config={
            "response_mime_type": "application/json",
            "response_json_schema": ANALYSIS_SCHEMA,
        },
    )

    text = response.text or "{}"
    result = json.loads(text)
    result = _apply_breakdown_fallbacks(result, breakdown_payload, analysis_run=analysis_run)
    return {
        "provider": "gemini",
        "model_name": model_name,
        "raw_text": text,
        "result_json": result,
        "confidence": result.get("confidence"),
    }


def synthesize_report_with_gemini(config, report, analyses_payload):
    client, model_name = _get_client_and_model(config)

    runs_text = "\n".join(
        f"- Run {entry.analysis_run.id}: {entry.analysis_run.game.label} | "
        f"Fokus {entry.analysis_run.focus_team.name} | "
        f"Modus {entry.analysis_run.analysis_mode} | "
        f"Clips {entry.analysis_run.processed_clips}/{entry.analysis_run.total_clips}"
        for entry in report.runs
    )

    def build_section_prompt(title, instructions, section_payload):
        payload_text = json.dumps(section_payload, ensure_ascii=True)
        return f"""
You are an expert American Football scouting analyst.

Section:
- {title}

Report title:
- {report.title}

Focus team:
- {report.focus_team.name}

Included analysis runs:
{runs_text}

Task:
- Write this report section in German.
- Use Markdown headings and bullet points.
- Keep it practical for coaches.
- Only state tendencies that are supported by the provided data.
- If evidence is thin or incomplete, say so clearly.

Section instructions:
{instructions}

Structured data:
{payload_text}
""".strip()

    offense_prompt = build_section_prompt(
        "Offense Summary",
        """
- Focus on offensive tendencies of the focus team.
- Highlight formations, motions, run/pass indicators, direction, concepts and recurring outcomes.
- End with 3-5 actionable coaching takeaways for defending this offense.
""".strip(),
        {
            "completed_play_count": analyses_payload["completed_play_count"],
            "top_play_types": analyses_payload["top_play_types"],
            "top_formations": analyses_payload["top_formations"],
            "top_results": analyses_payload["top_results"],
            "offensive_samples": analyses_payload["offensive_samples"],
        },
    )
    defense_prompt = build_section_prompt(
        "Defense Summary",
        """
- Focus on defensive tendencies of the focus team.
- Highlight fronts, coverage, blitz, pressure, alignment patterns and recurring reactions.
- End with 3-5 actionable coaching takeaways for attacking this defense.
""".strip(),
        {
            "completed_play_count": analyses_payload["completed_play_count"],
            "top_coverages": analyses_payload["top_coverages"],
            "top_results": analyses_payload["top_results"],
            "defensive_samples": analyses_payload["defensive_samples"],
        },
    )
    situational_prompt = build_section_prompt(
        "Situational Summary",
        """
- Focus on situational tendencies.
- Analyze down, distance, field position, hash, special or notable situations if available.
- Identify any specific tendencies that appear in those situations.
- End with 3-5 situation-based coaching points.
""".strip(),
        {
            "completed_play_count": analyses_payload["completed_play_count"],
            "top_downs": analyses_payload["top_downs"],
            "top_distances": analyses_payload["top_distances"],
            "top_hashes": analyses_payload["top_hashes"],
            "top_field_positions": analyses_payload["top_field_positions"],
            "situational_samples": analyses_payload["situational_samples"],
        },
    )

    offense_text = (_generate_with_retry(client, model_name, offense_prompt, config).text or "").strip()
    defense_text = (_generate_with_retry(client, model_name, defense_prompt, config).text or "").strip()
    situational_text = (_generate_with_retry(client, model_name, situational_prompt, config).text or "").strip()

    final_prompt = f"""
You are an expert American Football scouting analyst preparing the final coach-facing scouting report.

Report title:
- {report.title}

Focus team:
- {report.focus_team.name}

Included analysis runs:
{runs_text}

Use the following three prepared section summaries and merge them into one cohesive German scouting report.

Requirements:
- Write in German.
- Use Markdown headings and bullet points.
- Keep the tone compact, clear and coach-oriented.
- Include these sections:
  1. Executive Summary
  2. Offense
  3. Defense
  4. Situational Tendencies
  5. Top Coaching Points
  6. Data Gaps / Confidence
- Do not invent facts beyond the summaries.

Offense Summary:
{offense_text}

Defense Summary:
{defense_text}

Situational Summary:
{situational_text}
""".strip()

    text = (_generate_with_retry(client, model_name, final_prompt, config).text or "").strip()
    if not text:
        raise RuntimeError("Gemini hat keinen Report-Text zurückgegeben.")
    return {
        "provider": "gemini",
        "model_name": model_name,
        "report_text": text,
        "sections": {
            "offense": offense_text,
            "defense": defense_text,
            "situational": situational_text,
        },
    }


def synthesize_play_by_play_report_with_gemini(config, report, play_by_play_payload):
    client, model_name = _get_client_and_model(config)

    runs_text = "\n".join(
        f"- Run {entry.analysis_run.id}: {entry.analysis_run.game.label} | "
        f"Fokus {entry.analysis_run.focus_team.name} | "
        f"Modus {entry.analysis_run.analysis_mode}"
        for entry in report.runs
    )

    def build_section_prompt(title, instructions, section_payload):
        payload_text = json.dumps(section_payload, ensure_ascii=True)
        return f"""
You are an expert American Football analyst creating a German play-by-play report for coaches.

Section:
- {title}

Report title:
- {report.title}

Focus team:
- {report.focus_team.name}

Included analysis runs:
{runs_text}

Task:
- Write this section in German.
- Use Markdown headings and bullet points.
- Keep it factual, chronological and coach-friendly.
- Only describe patterns and sequence notes that are supported by the provided data.
- If evidence is incomplete, say so clearly.

Section instructions:
{instructions}

Structured data:
{payload_text}
""".strip()

    flow_prompt = build_section_prompt(
        "Game Flow",
        """
- Summarize the overall flow of the game from the play sequence.
- Highlight how the game evolved quarter by quarter.
- Mention the most common play types and outcomes only if they matter for the flow.
""".strip(),
        {
            "completed_play_count": play_by_play_payload["completed_play_count"],
            "quarter_summaries": play_by_play_payload["quarter_summaries"],
            "top_play_types": play_by_play_payload["top_play_types"],
            "top_results": play_by_play_payload["top_results"],
        },
    )
    series_prompt = build_section_prompt(
        "Drive And Series Notes",
        """
- Focus on the most relevant series or drives in chronological order.
- Point out explosive or momentum-shifting sequences.
- End with 3-5 concise notes on recurring drive-level behavior.
""".strip(),
        {
            "series_summaries": play_by_play_payload["series_summaries"],
            "plays": play_by_play_payload["plays"][:40],
        },
    )
    situational_prompt = build_section_prompt(
        "Situational Notes",
        """
- Focus on down-and-distance, field position and notable situations.
- Highlight where the focus team repeatedly succeeded or stalled.
- End with 3-5 practical coaching takeaways.
""".strip(),
        {
            "top_downs": play_by_play_payload["top_downs"],
            "top_field_positions": play_by_play_payload["top_field_positions"],
            "top_results": play_by_play_payload["top_results"],
            "plays": play_by_play_payload["plays"][:30],
        },
    )

    flow_text = (_generate_with_retry(client, model_name, flow_prompt, config).text or "").strip()
    series_text = (_generate_with_retry(client, model_name, series_prompt, config).text or "").strip()
    situational_text = (_generate_with_retry(client, model_name, situational_prompt, config).text or "").strip()

    final_prompt = f"""
You are an expert American Football analyst preparing the final German play-by-play report for coaches.

Report title:
- {report.title}

Focus team:
- {report.focus_team.name}

Included analysis runs:
{runs_text}

Create one coherent Markdown report from the prepared summaries below.

Requirements:
- Write in German.
- Use Markdown headings and bullet points.
- Keep the tone compact, clear and coach-oriented.
- Include these sections:
  1. Executive Summary
  2. Quarter Flow
  3. Drive / Series Notes
  4. Situational Tendencies
  5. Top Coaching Points
  6. Data Gaps / Confidence
- Do not invent facts beyond the summaries.

Game Flow:
{flow_text}

Drive And Series Notes:
{series_text}

Situational Notes:
{situational_text}
""".strip()

    text = (_generate_with_retry(client, model_name, final_prompt, config).text or "").strip()
    if not text:
        raise RuntimeError("Gemini hat keinen Play-by-Play-Report zurückgegeben.")
    return {
        "provider": "gemini",
        "model_name": model_name,
        "report_text": text,
        "sections": {
            "flow": flow_text,
            "series": series_text,
            "situational": situational_text,
        },
    }
