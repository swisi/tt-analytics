# Decisions

## ADR-001: Mehrere Spiele pro Gegner sind Teil des Kernmodells

Status:

- akzeptiert

Entscheid:

- ein Gegner kann mehrere Spiele enthalten
- Reports koennen ueber ein einzelnes Spiel oder mehrere Spiele laufen

Begruendung:

- ein einzelnes Spiel ist fuer Scouting oft zu schmal
- Multi-Game-Analyse liefert robustere Tendenzen

## ADR-002: Gemini ist der erste Provider fuer den MVP

Status:

- akzeptiert

Entscheid:

- der erste Prototyp nutzt Gemini als ersten angebundenen Provider

Begruendung:

- Gemini dokumentiert Videoverarbeitung offiziell
- fuer Testzwecke gibt es weiterhin ein Free Tier
- fuer euren Use Case ist Gemini der pragmatischste erste Start

## ADR-002a: LiteLLM wird als Gateway von Beginn an eingeplant

Status:

- akzeptiert

Entscheid:

- `tt-analytics` spricht nicht direkt mit Gemini
- `tt-analytics` spricht mit LiteLLM
- LiteLLM routet im MVP zunaechst nur auf Gemini

Begruendung:

- die Anwendung bleibt provider-neutraler
- ein spaeterer Wechsel oder Parallelbetrieb wird einfacher
- der Mehraufwand bleibt klein, solange wir fachlich nur einen Provider aktiv nutzen

## ADR-003: Videos gehen nicht in Postgres

Status:

- akzeptiert

Entscheid:

- Videos und Clips werden in Object Storage gespeichert
- Postgres speichert nur Metadaten und Analyseergebnisse

Begruendung:

- bessere Skalierung
- sauberere Backups
- weniger technische Schulden

## ADR-004: Analyse in zwei Stufen

Status:

- akzeptiert

Entscheid:

- erst Clip-Analyse
- danach Report-Synthese

Begruendung:

- bessere Nachvollziehbarkeit
- einfachere Wiederholbarkeit
- guenstiger als ein einziger sehr grosser Prompt

## ADR-005: `tt-auth` bleibt fuer Rollen fuehrend

Status:

- akzeptiert

Entscheid:

- `tt-auth` bleibt Quelle fuer Plattformrolle und service-spezifische Analytics-Rolle

Begruendung:

- konsistentes Plattformmodell
- kein zweites fuehrendes Benutzerverwaltungssystem in `tt-analytics`

## ADR-006: Analyse ist ein asynchroner Batch-Prozess

Status:

- akzeptiert

Entscheid:

- Clip-Analysen und Report-Synthese laufen asynchron im Hintergrund
- Laufzeiten ueber mehrere Stunden oder ueber Nacht sind fachlich akzeptiert

Begruendung:

- grosse Clip-Mengen pro Gegner sind normal
- AI-Analyse muss nicht in Echtzeit erfolgen
- das Batch-Modell ist robuster und kostenseitig besser kontrollierbar

## ADR-007: Web-MVP wird mit Flask und Jinja2 umgesetzt

Status:

- akzeptiert

Entscheid:

- `tt-analytics` wird im MVP als Flask-Anwendung mit Jinja2-Templates umgesetzt

Begruendung:

- konsistenter zum bestehenden Plattform-Stack
- einfacher fuer SSO, Sessions und gemeinsames Layout
- weniger technologische Streuung im Projekt
- FastAPI ist spaeter weiterhin moeglich, falls API-lastige Anforderungen wachsen
