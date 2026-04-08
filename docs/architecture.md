# Architektur

## Zielarchitektur

`tt-analytics` wird als eigenstaendiger Microservice innerhalb des Tigers-Stacks betrieben.

Bausteine:

- `tt-auth` fuer Login, Plattformrollen und Servicefreigaben
- `tt-analytics` fuer Upload, Analyse, Review und Reporting
- `tt-postgres-analytics` fuer Metadaten, Analyse-JSONs und Reports
- Object Storage fuer Rohvideos, Clips und Report-Artefakte
- Background Worker fuer asynchrone AI-Jobs
- LiteLLM als schlankes Provider-Gateway
- Gemini als erster angebundener AI-Provider

## Web-Stack fuer den MVP

Der MVP von `tt-analytics` wird als server-rendered Web-Anwendung umgesetzt.

Empfohlener Stack:

- Flask
- Jinja2
- SQLAlchemy
- Flask-Migrate

Begruendung:

- konformer zum bestehenden Tigers-Stack
- naeher an `tt-auth` und `tt-agenda`
- einfachere Wiederverwendung von Layout- und Session-Mustern
- die eigentliche technische Komplexitaet liegt in Jobs, AI-Pipeline und Reporting, nicht im HTTP-Framework

## Warum nicht alles direkt in einem Prompt

Ein gesamtes Spiel mit sehr vielen Clips sollte nicht als ein einziger Riesen-Request verarbeitet werden.

Stattdessen:

1. pro Clip eine standardisierte Analyse
2. Speicherung als validiertes JSON
3. Aggregation zu Spiel- und Gegnerberichten

Das ist stabiler, nachvollziehbarer und billiger.

## Datenfluss

1. Coach legt Gegner und Spielserie an
2. Coach laedt ein oder mehrere Spiele hoch
3. Jedes `game` bleibt als neutrales Heim/Gast-Spiel gespeichert
4. Pro Spiel und Fokus-Team werden ein oder mehrere `analysis_run` angelegt
5. Die Spiele bestehen aus vielen einzelnen Clips oder Plays und werden so gespeichert
6. Ein Worker verarbeitet jeden Clip asynchron
7. Gemini liefert pro Clip ein JSON nach vorgegebenem Schema
8. Die Ergebnisse werden gespeichert und koennen manuell reviewed werden
9. Ein Synthese-Schritt erstellt einen Spielbericht oder Multi-Game-Scouting Report aus mehreren passenden Runs
10. Coaches lesen oder exportieren den Report

## Domänenmodell

Vorgeschlagene Kernobjekte:

- `team`
- `season`
- `game`
- `video_asset`
- `clip`
- `clip_metadata`
- `analysis_run`
- `clip_analysis`
- `clip_review`
- `knowledge_document`
- `knowledge_chunk`
- `report`

Die detailliertere Modellierung steht in:

- `docs/data-model.md`

Wichtige fachliche Regel:

- `game` ist neutral mit `home_team` und `away_team`
- der Analysefokus liegt nicht am Spiel, sondern am `analysis_run`
- dadurch kann dasselbe Spiel mehrfach aus verschiedenen Team-Perspektiven ausgewertet werden

## Speicherstrategie

Postgres speichert:

- Gegner, Spiele, Tags und Metadaten
- Analyse-Jobs und Stati
- strukturierte JSON-Ergebnisse
- generierte Reports
- Referenzen auf Wissensdokumente

Object Storage speichert:

- hochgeladene Videos
- erzeugte Clips
- Vorschaubilder
- exportierte Reports

Begruendung:

- Videos sind fuer relationale Datenbanken unpassend
- Object Storage ist einfacher zu skalieren und zu sichern

## Auth und Rollen

`tt-auth` bleibt die fuehrende Quelle.

Empfohlen fuer `tt-analytics`:

- Plattformrolle aus `tt-auth`
- service-spezifische Rolle fuer `analytics`
- lokale Schattenbenutzer in `tt-analytics` nur fuer Session, Referenzen und ggf. lokale Praeferenzen

Service-Rollen in `analytics`:

- `user`
- `admin`

Moegliche Berechtigungen:

- `user`: Uploads ansehen, Reports lesen, eigene Runs starten
- `admin`: Dokumente verwalten, Prompt-Sets pflegen, Reports freigeben, Benutzerzugriffe fachlich organisieren

## AI-Layer

Empfohlener Start:

- `tt-analytics` spricht mit LiteLLM
- LiteLLM routet im MVP nur auf Gemini

Warum das jetzt sinnvoll ist:

- einheitliche API ueber mehrere Modelle
- `tt-analytics` wird nicht direkt an einen einzelnen Provider gekoppelt
- spaeterer Wechsel zu OpenAI, xAI oder anderen Anbietern einfacher
- Routing und Fallbacks zentraler steuerbar

Wichtig:

- im MVP bleibt die fachliche Zielsetzung trotzdem einfach
- ein Gateway bedeutet nicht, dass wir gleich ein komplexes Multi-Provider-Routing bauen muessen
- anfangs reicht `LiteLLM -> Gemini`

## RAG / Wissenskontext

Playbooks, PDFs, Praesentationen und Notizen sollen nicht einfach als freie Dateianhaenge in jeden Prompt gepackt werden.

Sinnvoller ist:

- Dokumente ingestieren
- in Chunks zerlegen
- Embeddings erzeugen
- bei Bedarf relevante Ausschnitte pro Analyse oder Report beiziehen

Wichtig:

- Play-Analyse und Wissenskontext bleiben getrennte Ebenen
- Primärdaten sind Video plus strukturiertes Analyse-JSON
- Kontext verbessert Interpretation, ersetzt aber nicht das Spielmaterial

## Verarbeitungspipeline

### Stufe 1: Ingestion

- Spiel anlegen
- Videos hochladen
- Metadaten erfassen
- Clips registrieren

### Stufe 2: Clip-Analyse

- Job pro Clip
- Upload oder Referenz zum Clip an Gemini
- erzwungenes JSON-Schema
- Validierung und Speicherung
- Verarbeitung darf bewusst lange dauern, z. B. ueber mehrere Stunden oder ueber Nacht
- der Ablauf muss deshalb queue-basiert, restart-faehig und idempotent sein

### Stufe 3: Review

- unklare oder schwache Analysen markieren
- manuelle Korrekturen oder erneute Analyse erlauben

### Stufe 4: Report-Synthese

- Aggregation ueber ein oder mehrere Spiele
- Erstellung eines Reports nach Coaching-Sicht

## Betriebsmodell fuer lange Analysen

Die Analyse ist kein interaktiver Sekunden-Workflow.

Fuer den MVP ist ein asynchrones Batch-Modell sinnvoll:

- Upload am Nachmittag oder Abend
- Analyse laeuft ueber Stunden oder nachts
- Report steht am naechsten Morgen oder nach Abschluss bereit

Daraus folgen technische Anforderungen:

- persistente Job-Queue
- Status pro Clip und pro Lauf
- Retry-Mechanismus
- saubere Fehlerlisten statt stiller Abbrueche
- moegliche Wiederaufnahme nach Neustart
- Kosten- und Rate-Limit-Kontrolle pro Run

## Deployment im Stack

Lokal:

- `tt-auth` ueber `localhost:8085`
- `tt-agenda` ueber `localhost:8086`
- `tt-analytics` spaeter z. B. ueber `localhost:8087`

Intern im Docker-Netz:

- `tt-auth`
- `tt-agenda`
- `tt-analytics`
- `tt-postgres-analytics`
- optional `tt-litellm`
- optional `tt-redis`

## MVP-Technologieempfehlung

- Python
- Flask
- Jinja2
- SQLAlchemy
- Flask-Migrate
- Postgres
- Redis fuer Queue empfohlen
- RQ, Celery oder Dramatiq fuer Background Jobs
- Gemini API fuer Videoanalyse
- spaeter pgvector oder ein externer Vector Store fuer RAG

## Offene Architekturentscheide

- welches Queue-System fuer Jobs
- lokales Dateisystem vs. S3-kompatibler Object Storage im MVP
- ob Redis im MVP direkt gesetzt wird oder erst mit dem ersten Worker-Ausbau
