# Backlog

## Status

Stand heute:

- [x] Vision, Architektur und Use Cases dokumentiert
- [x] Hudl-Referenzen analysiert
- [x] Play-Analyse-Schema vorbereitet
- [x] gemeinsames Zielmodell fuer Gegner- und Eigenspiele festgelegt

## Priorisierung

Arbeitsreihenfolge:

1. MVP fuer Gegner-Scouting
2. Review und bessere Report-Qualitaet
3. Self-Scouting und Auto-Tagging
4. Wissensbasis und RAG
5. Multi-Provider und Optimierung

## Phase 0: Discovery und Architektur

- [x] Produktgrenzen und Rollenmodell finalisieren
- [x] JSON-Schema fuer Play-Analyse definieren
- [x] Datenmodell fuer Gegner, Spiele, Clips und Reports festlegen
- [x] Entscheidung fuer Framework und Queue treffen
- [ ] Speicherstrategie fuer Videos im MVP festlegen
- [x] LiteLLM-Topologie fuer den Stack festlegen
- [x] Import-/Export-Mapping fuer die 3 Hudl-Varianten definieren

## Phase 1: MVP-Plattform

- [x] Basisprojekt `tt-analytics` initialisieren
- [x] SSO mit `tt-auth` integrieren
- [x] Postgres anbinden
- [x] Dockerfile und Compose-Integration vorbereiten
- [x] Healthcheck und Grundlayout bauen
- [ ] LiteLLM-Service lokal im Stack anbinden
- [x] Basis-Konfiguration fuer Provider-Keys vorbereiten

## Phase 2: Gegner- und Spielverwaltung

- [x] Gegner anlegen, bearbeiten, archivieren
- [x] Spiele einem Gegner zuordnen
- [x] Metadaten fuer Spiel erfassen
- [x] Upload-Workflow fuer Videos oder Clips
- [ ] Import des minimalen Hudl-Formats
- [x] Import des erweiterten Hudl-Formats
- [ ] Export in minimales Gegnerformat

## Phase 3: Clip-Ingestion und Jobsystem

- [ ] Upload in Object Storage
- [x] Clip-Entitaet mit Statusmodell
- [ ] Analyse-Queue aufbauen
- [x] Retry- und Fehlerbehandlung
- [ ] Resume nach Neustart
- [ ] Batch-Run ueber Nacht unterstuetzen
- [x] Fortschritt je Spiel und je Gegnerlauf anzeigen
- [ ] klare Fehlercodes fuer einzelne Clips und Runs
- [x] Rate-Limit-Steuerung fuer Provider-Jobs

## Phase 4: AI-Provider und Analyse

- [ ] LiteLLM-Client in `tt-analytics` einbauen
- [ ] Gemini in LiteLLM konfigurieren
- [x] Datei-Upload oder Files API anbinden
- [x] strukturierten JSON-Output erzwingen
- [x] Ergebnisvalidierung und Speicherung
- [ ] Prompt-Versionierung einbauen
- [x] Modell- und Provider-Metadaten pro Run speichern

## Phase 5: Review und Qualitaet

- [ ] Einzelansicht fuer Clip und Analyse
- [ ] manuelle Markierung fehlerhafter Analysen
- [x] Re-Run fuer einzelne Clips
- [ ] Vergleich verschiedener Prompt- oder Modellversionen
- [ ] Diff zwischen AI-Ergebnis und Review-Korrektur
- [ ] Confidence- und Quality-Hinweise im UI

## Phase 6: Report-Synthese

- [x] Spielreport aus mehreren Clips
- [ ] Multi-Game-Scouting Report pro Gegner
- [x] Standard-Abschnitte fuer Coaches
- [x] Export als PDF oder HTML
- [ ] verlinkte Beispielclips im Report
- [ ] Report-Generierung aus mehreren Spielen eines Gegners
- [x] Report-JSON und HTML strikt trennen

## Phase 6a: Self-Scouting und Auto-Tagging

- [ ] eigene Spiele hochladen
- [ ] AI-basierte Vorbelegung von Play-Tags
- [ ] Review-Workflow fuer Korrekturen
- [ ] Export in minimales Austauschformat
- [ ] separates Reporting fuer Self-Scout
- [ ] Wiederverwendung derselben Clip-Analyse-Pipeline

## Phase 7: Wissensbasis / RAG

- [ ] Upload fuer PDFs, Playbooks und Praesentationen
- [ ] Dokument-Ingestion
- [ ] Chunking und Embeddings
- [ ] Retrieval fuer Report-Erstellung
- [ ] team- oder staff-spezifische Wissenssammlungen
- [ ] Bezug zwischen Report und verwendeten Wissensquellen

## Phase 8: Betrieb und Sicherheit

- [ ] Audit-Logging fuer Uploads und Reports
- [ ] Backup-Konzept fuer Postgres und Object Storage
- [ ] Aufbewahrungsregeln fuer Videos
- [ ] Kostenkontrolle fuer AI-Requests
- [ ] Secrets-Management fuer Provider-Keys
- [ ] Monitoring fuer Queue, Worker und Fehlerraten

## MVP-Scope Empfehlung

Fuer den ersten nutzbaren Wurf wuerde ich nur das hier bauen:

- [x] Login ueber `tt-auth`
- [x] Gegner anlegen
- [x] ein oder mehrere Spiele pro Gegner anlegen
- [x] Clips hochladen
- [x] Import des erweiterten Mindestschemas aus Hudl
- [ ] pro Clip Analyse ueber `LiteLLM -> Gemini` als JSON speichern
- [x] Report aus den JSONs erzeugen
- [x] einfache Webansicht des Reports
- [ ] asynchroner Lauf mit Queue und Statusanzeige
- [ ] Export in minimales Gegnerformat

## Spater

- [ ] weitere Provider hinter LiteLLM
- [ ] RAG mit Playbooks
- [x] PDF-Export
- [ ] bessere Metriken und Dashboards
- [ ] Modellvergleich
- [ ] Review-Workflow mit Freigabe
- [ ] Auto-Tagging fuer eigene Spiele
