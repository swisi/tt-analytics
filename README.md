# tt-analytics

`tt-analytics` ist der Analyse-Microservice der Tigers-Plattform.

Ziel ist eine AI-gestuetzte Spielanalyse fuer American Football:

- Upload von mehreren Spielvideos bzw. vielen einzelnen Clips pro Gegner
- strukturierte Play-by-Play-Analyse per LLM
- Aggregation der Analysen zu Scouting Reports fuer Coaches
- zusaetzlicher Wissenskontext durch Playbooks, PDFs, Praesentationen und Notizen
- zentrale Anmeldung ueber `tt-auth`

Die Doku fuer den ersten Architektur- und Produktentwurf liegt unter:

- `docs/vision.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/use-cases.md`
- `docs/backlog.md`
- `docs/decisions.md`
- `docs/hudl-reference.md`
- `docs/play-analysis-schema.md`
- `docs/report-structure.md`

## Zielbild

Ein Coach kann vor einem Spiel mehrere gegnerische Spiele hochladen, diese in einzelne Plays oder Clips aufteilen lassen, Play-Analysen erzeugen und daraus einen Scouting Report erstellen lassen.

## Technische Leitplanken

- zentrale Authentifizierung ueber `tt-auth`
- eigene Postgres-Datenbank
- Videos nicht in Postgres speichern, sondern in Object Storage
- AI-Zugriff im aktuellen MVP direkt ueber Gemini
- LiteLLM bleibt als naechste Abstraktionsschicht geplant
- asynchrone Verarbeitung statt synchroner Monster-Requests

## Status

Der aktuelle Stand umfasst:

- Produkt- und Architekturplanung fuer den MVP
- analysierte Hudl-Referenzen und Breakdown-Import
- Flask- und Jinja2-Webanwendung mit SSO ueber `tt-auth`
- Postgres-faehige Service-Konfiguration fuer lokalen Docker-Betrieb
- Team-, Spiel-, Run- und Report-Verwaltung
- Clip-Upload und Gemini-basierte Play-Analyse mit Retry-Logik
- mehrstufige Report-Synthese mit Executive Overview, Tendency Tables und Full Report
- HTML-basierter PDF-Export, damit Web- und PDF-Darstellung dieselbe Report-Struktur nutzen
