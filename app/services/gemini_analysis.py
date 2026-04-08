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


def analyze_clip_with_gemini(config, clip, analysis_run, breakdown_payload):
    api_key = (config.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY ist nicht gesetzt.")

    clip_path = Path(clip.storage_path)
    if not clip_path.exists():
        raise RuntimeError("Clip-Datei wurde im Upload-Speicher nicht gefunden.")

    client = genai.Client(api_key=api_key)
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
    max_retries = int(config.get("GEMINI_MAX_RETRIES", 8))
    response = None

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=config.get("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=[uploaded, prompt],
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": ANALYSIS_SCHEMA,
                },
            )
            break
        except Exception as exc:
            error_text = str(exc)
            if attempt >= max_retries or not _is_retryable_rate_limit(error_text):
                raise
            time.sleep(_parse_retry_seconds(error_text, config))

    text = response.text or "{}"
    result = json.loads(text)
    return {
        "provider": "gemini",
        "model_name": config.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "raw_text": text,
        "result_json": result,
        "confidence": result.get("confidence"),
    }
