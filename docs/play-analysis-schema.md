# Play Analysis Schema

## Ausgangspunkt

Die Hudl-Excel-Vorlage dient als fachliche Referenz fuer die Struktur eines einzelnen Plays.

Die Datei enthaelt unter anderem diese relevanten Spalten:

- `PLAY #`
- `ODK`
- `QTR`
- `SERIES`
- `DN`
- `DIST`
- `YARD LN`
- `HASH`
- `PLAY TYPE`
- `RESULT`
- `GN/LS`
- `BLITZ`
- `BOX`
- `COVERAGE`
- `DEEP SHOT`
- `DEF FRONT`
- `DEF STR`
- `FLD ZN`
- `GAP`
- `MOTION`
- `MOTION DIR`
- `OFF FORM`
- `OFF PLAY`
- `OFF STR`
- `PASS CATEGORY`
- `PASS PRO`
- `PASS ZONE`
- `PENALTY`
- `PERSONNEL`
- `PLAY DIR`
- `PLAY NAME`
- `PRESSURE`
- `SET`
- `SITUATION`
- `TARGET`
- `TEAM`
- `NOSE GAP`
- `NOSE #`
- `FIB`
- `EFF`
- `COMMENTS`
- `BACKFIELD`
- `B/S CONCEPT`
- `2 MIN`
- `&10`

Zusätzlich gibt es rollen- oder spielerbezogene Felder wie:

- `PASSER_*`
- `RECEIVER_*`
- `RUSHER_*`
- `TACKLER1_*`
- `TACKLER2_*`
- `KICKER_*`
- `RETURNER_*`
- `RECOVERED BY_*`
- `INTERCEPTED BY_*`
- diverse `OPP *`-Felder

## Empfehlung fuer das interne JSON

Nicht jede Hudl-Spalte sollte 1:1 das Primaermodell in `tt-analytics` werden.

Sinnvoll ist ein internes Schema mit vier Ebenen:

1. `play_context`
2. `offense_observation`
3. `defense_observation`
4. `outcome`

## Vorschlag fuer MVP-JSON

```json
{
  "play_number": 12,
  "phase": "defense",
  "quarter": 2,
  "series": 4,
  "down": 3,
  "distance": 6,
  "yard_line": "-21",
  "hash": "R",
  "field_zone": "red_zone",
  "situation": "3rd_medium",
  "two_minute": false,
  "offense": {
    "personnel": "11",
    "formation": "Trips Right",
    "strength": "right",
    "backfield": "gun",
    "motion": true,
    "motion_direction": "left_to_right",
    "play_type": "pass",
    "play_name": "stick",
    "play_direction": "right",
    "concept": "quick_game",
    "pass_category": "quick",
    "pass_zone": "short_right",
    "target": "slot"
  },
  "defense": {
    "front": "odd",
    "box_count": 6,
    "coverage": "cover_3",
    "blitz": false,
    "pressure": true,
    "strength": "field",
    "nose_gap": "A"
  },
  "participants": {
    "passer": null,
    "receiver": null,
    "rusher": null,
    "key_player": null
  },
  "outcome": {
    "result": "complete",
    "yards_gained": 8,
    "penalty": null,
    "penalty_yards": 0,
    "turnover": false,
    "explosive": false,
    "efficiency_flag": true
  },
  "model_metadata": {
    "provider": "gemini",
    "model": "gemini-via-litellm",
    "prompt_version": "v1",
    "confidence": 0.74
  },
  "review": {
    "status": "pending",
    "notes": null
  }
}
```

## Felder fuer den MVP

Diese Felder sind fuer die erste Version besonders wertvoll:

- `play_number`
- `phase` aus `ODK`
- `down`
- `distance`
- `yard_line`
- `hash`
- `play_type`
- `yards_gained`
- `personnel`
- `formation`
- `motion`
- `play_direction`
- `coverage`
- `blitz`
- `pressure`
- `result`
- `field_zone`
- `situation`

## Felder eher fuer spaeter

Diese Felder sind nuetzlich, aber nicht alle muessen im ersten AI-Wurf perfekt erkannt werden:

- konkrete Spielernamen und Trikotnummern
- `NOSE #`
- `FIB`
- `EFF`
- `B/S CONCEPT`
- Spezialteam-spezifische Detailfelder
- alle `OPP *`-Felder in voller Breite

## Wichtig fuer die Produktlogik

Es ist sinnvoll, zwischen drei Quellen zu unterscheiden:

1. `source_manual`
2. `source_ai`
3. `source_derived`

Beispiel:

- `down` kann manuell oder aus Hudl-Metadaten kommen
- `coverage` ist oft eine AI- oder Review-Einschaetzung
- `field_zone` kann aus Yardline abgeleitet werden

## Konsequenz fuer das System

Die Hudl-Vorlage ist kein 1:1-Datenbankmodell.

Sie ist:

- starke fachliche Referenz fuer Terminologie
- Grundlage fuer das Review-UI
- guter Startpunkt fuer das Play-JSON

Das interne Modell sollte aber normalisiert und versionierbar bleiben.
