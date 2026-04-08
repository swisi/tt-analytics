# Datenmodell

## Modellziel

`tt-analytics` soll Gegner-Scouting und Self-Scouting mit demselben Kernmodell abbilden.

Die zentrale Idee ist:

- ein gemeinsames `game`
- ein gemeinsames `clip`
- ein gemeinsames `play_analysis`
- unterschiedliche Modi fuer Gegner- und Eigenspielanalyse

## Kernobjekte

### `team`

Repraesentiert ein Team im System.

Beispiele:

- Tigers
- Gegner A
- Gegner B

Felder:

- `id`
- `name`
- `club_name`
- `is_own_team`
- `active`

### `season`

Ordnet Spiele einem zeitlichen Kontext zu.

Felder:

- `id`
- `label`
- `year`
- `active`

### `game`

Repraesentiert ein einzelnes Spiel.

Felder:

- `id`
- `season_id`
- `home_team_id`
- `away_team_id`
- `game_date`
- `source_type`
- `label`
- `notes`

Empfohlene Werte:

- `source_type`: `opponent_film`, `own_game`, `practice_cutup`

Wichtig:

- `game` ist neutral
- das Spiel selbst hat noch keinen festen Analysefokus
- derselbe `game` kann spaeter mehrfach mit verschiedenen Fokus-Teams ausgewertet werden

### `video_asset`

Repraesentiert die hochgeladene Datei.

Felder:

- `id`
- `game_id`
- `storage_key`
- `original_filename`
- `content_type`
- `duration_seconds`
- `checksum`
- `status`

### `clip`

Repraesentiert einen einzelnen Spielzug oder eine kleine Videoeinheit.

Felder:

- `id`
- `game_id`
- `video_asset_id`
- `clip_number`
- `start_ms`
- `end_ms`
- `storage_key`
- `import_source`
- `external_play_number`
- `status`

`external_play_number` mappt z. B. auf Hudl `PLAY #`.

### `clip_metadata`

Speichert importierte oder manuell gepflegte fachliche Felder, noch vor oder unabhaengig von der AI-Analyse.

Felder:

- `id`
- `clip_id`
- `schema_version`
- `source_kind`
- `payload_json`

`source_kind`:

- `hudl_minimum`
- `hudl_extended`
- `manual_entry`
- `derived`

### `analysis_run`

Repraesentiert einen kompletten Lauf ueber viele Clips.

Felder:

- `id`
- `game_id`
- `focus_team_id`
- `analysis_mode`
- `provider`
- `model_name`
- `prompt_version`
- `status`
- `started_by_user_id`
- `started_at`
- `finished_at`
- `total_clips`
- `processed_clips`
- `failed_clips`

Beispiel:

- `Genf vs. Bern` als `game`
- Run A mit Fokus `Genf`
- Run B mit Fokus `Bern`

### `clip_analysis`

Repraesentiert das Ergebnis einer AI-Analyse fuer einen Clip.

Felder:

- `id`
- `clip_id`
- `analysis_run_id`
- `provider`
- `model_name`
- `prompt_version`
- `schema_version`
- `status`
- `confidence`
- `result_json`
- `error_message`

### `clip_review`

Repraesentiert menschliche Nachbearbeitung.

Felder:

- `id`
- `clip_analysis_id`
- `reviewed_by_user_id`
- `review_status`
- `review_notes`
- `corrected_json`
- `reviewed_at`

### `knowledge_document`

Repraesentiert Playbooks, PDFs, Slides oder Notizen.

Felder:

- `id`
- `team_id`
- `title`
- `document_type`
- `storage_key`
- `status`

### `knowledge_chunk`

Repraesentiert RAG-faehige Dokumentabschnitte.

Felder:

- `id`
- `knowledge_document_id`
- `chunk_index`
- `text_content`
- `embedding_ref`

### `report`

Repraesentiert einen generierten Bericht.

Felder:

- `id`
- `report_type`
- `title`
- `focus_team_id`
- `status`
- `summary`
- `report_json`
- `rendered_html`
- `rendered_pdf_key`

`report_type`:

- `single_game`
- `multi_game_opponent`
- `self_scout`

### `report_run`

Ordnet mehrere Analyse-Runs einem Report zu.

Dadurch kann ein Multi-Game-Scouting-Report aus mehreren Spielen desselben Fokus-Teams entstehen.

## Beziehungen

- ein `season` hat viele `game`
- ein `game` hat viele `video_asset`
- ein `game` hat viele `clip`
- ein `game` hat viele `analysis_run`
- ein `clip` hat viele `clip_analysis`
- ein `clip_analysis` kann eine `clip_review` haben
- ein `analysis_run` gehoert genau zu einem `focus_team`
- ein `report` gehoert genau zu einem `focus_team`
- ein `report` hat viele `report_run`
- ein `team` kann viele `knowledge_document` haben

## Modellprinzipien

- Videodateien bleiben ausserhalb von Postgres
- AI-Ergebnis und menschliche Korrektur bleiben getrennt
- Importdaten und Analyseergebnisse werden nicht vermischt
- das Modell funktioniert fuer Gegner- und Eigenspiele

## MVP-Schnitt

Fuer den ersten Wurf genuegen:

- `team`
- `season`
- `game`
- `video_asset`
- `clip`
- `analysis_run`
- `clip_analysis`
- `report`

`clip_review`, `knowledge_document` und `knowledge_chunk` koennen direkt vorbereitet, aber funktional spaeter aktiviert werden.
