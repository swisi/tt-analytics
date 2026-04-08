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

- [ ] Basisprojekt `tt-analytics` initialisieren
- [ ] SSO mit `tt-auth` integrieren
- [ ] Postgres anbinden
- [ ] Dockerfile und Compose-Integration vorbereiten
- [ ] Healthcheck und Grundlayout bauen
- [ ] LiteLLM-Service lokal im Stack anbinden
- [ ] Basis-Konfiguration fuer Provider-Keys vorbereiten

## Phase 2: Gegner- und Spielverwaltung

- [ ] Gegner anlegen, bearbeiten, archivieren
- [ ] Spiele einem Gegner zuordnen
- [ ] Metadaten fuer Spiel erfassen
- [ ] Upload-Workflow fuer Videos oder Clips
- [ ] Import des minimalen Hudl-Formats
- [ ] Import des erweiterten Hudl-Formats
- [ ] Export in minimales Gegnerformat

## Phase 3: Clip-Ingestion und Jobsystem

- [ ] Upload in Object Storage
- [ ] Clip-Entitaet mit Statusmodell
- [ ] Analyse-Queue aufbauen
- [ ] Retry- und Fehlerbehandlung
- [ ] Resume nach Neustart
- [ ] Batch-Run ueber Nacht unterstuetzen
- [ ] Fortschritt je Spiel und je Gegnerlauf anzeigen
- [ ] klare Fehlercodes fuer einzelne Clips und Runs
- [ ] Rate-Limit-Steuerung fuer Provider-Jobs

## Phase 4: AI-Provider und Analyse

- [ ] LiteLLM-Client in `tt-analytics` einbauen
- [ ] Gemini in LiteLLM konfigurieren
- [ ] Datei-Upload oder Files API anbinden
- [ ] strukturierten JSON-Output erzwingen
- [ ] Ergebnisvalidierung und Speicherung
- [ ] Prompt-Versionierung einbauen
- [ ] Modell- und Provider-Metadaten pro Run speichern

## Phase 5: Review und Qualitaet

- [ ] Einzelansicht fuer Clip und Analyse
- [ ] manuelle Markierung fehlerhafter Analysen
- [ ] Re-Run fuer einzelne Clips
- [ ] Vergleich verschiedener Prompt- oder Modellversionen
- [ ] Diff zwischen AI-Ergebnis und Review-Korrektur
- [ ] Confidence- und Quality-Hinweise im UI

## Phase 6: Report-Synthese

- [ ] Spielreport aus mehreren Clips
- [ ] Multi-Game-Scouting Report pro Gegner
- [ ] Standard-Abschnitte fuer Coaches
- [ ] Export als PDF oder HTML
- [ ] verlinkte Beispielclips im Report
- [ ] Report-Generierung aus mehreren Spielen eines Gegners
- [ ] Report-JSON und HTML strikt trennen

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

- [ ] Login ueber `tt-auth`
- [ ] Gegner anlegen
- [ ] ein oder mehrere Spiele pro Gegner anlegen
- [ ] Clips hochladen
- [ ] Import des erweiterten Mindestschemas aus Hudl
- [ ] pro Clip Analyse ueber `LiteLLM -> Gemini` als JSON speichern
- [ ] Report aus den JSONs erzeugen
- [ ] einfache Webansicht des Reports
- [ ] asynchroner Lauf mit Queue und Statusanzeige
- [ ] Export in minimales Gegnerformat

## Spater

- [ ] weitere Provider hinter LiteLLM
- [ ] RAG mit Playbooks
- [ ] PDF-Export
- [ ] bessere Metriken und Dashboards
- [ ] Modellvergleich
- [ ] Review-Workflow mit Freigabe
- [ ] Auto-Tagging fuer eigene Spiele
