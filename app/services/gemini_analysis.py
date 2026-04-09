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
        "confidence": {"type": "number"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "play_number",
        "focus_team",
        "side_of_ball",
        "play_type",
        "summary",
        "offense",
        "defense",
        "outcome",
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
""".strip()

    if analysis_run.analysis_mode == "play_by_play":
        prompt += "\n\n" + """

For play_by_play mode:
- Prioritize exact situational context, sequence order and immediate outcome of this specific play.
- Keep the summary factual and event-driven instead of trend-oriented.
- Add notes only for directly relevant coaching or execution details.
""".strip()

    if breakdown_payload:
        prompt += "\n\nAdditional play-by-play context from breakdown.xlsx (may be incomplete or partially wrong):\n"
        for key, value in breakdown_payload.items():
            if value not in ("", None):
                prompt += f"- {key}: {value}\n"

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
