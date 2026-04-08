# Hudl Reference

## Eingesehene Vorlage

Quelle:

- `PlaylistData_2026-04-08.xlsx`
- `PlaylistData_2026-04-08 (1).xlsx`
- `PlaylistData_2026-04-08 (2).xlsx`

Die Vorlage enthaelt eine einzelne Tabelle mit einer breiten, scouting-orientierten Playliste.

## Was daran hilfreich ist

Die Datei ist sehr nuetzlich fuer `tt-analytics`, weil sie zeigt:

- welche Begriffe Coaches real verwenden
- welche Play-Felder fuer Review und Reporting relevant sind
- welche Ausgabestruktur spaeter nachvollziehbar und praktisch ist

## Erste Beobachtung

Die Vorlage ist kein reines Rohdatenformat, sondern bereits eine Mischung aus:

- objektiven Spielkontext-Feldern
- fachlicher Einordnung
- Spielerzuordnung
- Review-/Kommentar-Feldern

Das ist gut, denn genau diese Mischung braucht spaeter auch die Anwendung.

## Vergleich der drei Vorlagen

### Vollformat

`PlaylistData_2026-04-08.xlsx`

Enthaelt ein breites Scouting- und Review-Format mit Kontext, Scheme-Feldern, Personenbezug und Kommentaren.

Das ist eine gute Referenz fuer:

- internes Analyse-JSON
- Review-UI
- Report-Synthese

### Erweitertes Minimum

`PlaylistData_2026-04-08 (1).xlsx`

Enthaelt unter anderem:

- `PLAY #`
- `ODK`
- `DN`
- `DIST`
- `YARD LN`
- `HASH`
- `PERSONNEL`
- `OFF FORM`
- `OFF STR`
- `BACKFIELD`
- `OFF PLAY`
- `B/S CONCEPT`
- `PLAY DIR`
- `PLAY TYPE`
- `PASS CATEGORY`
- `TARGET`
- `DEEP SHOT`
- `MOTION`
- `MOTION DIR`

Das ist aus fachlicher Sicht sehr nah an einem sinnvollen Mindestschema fuer eure gegnerbezogene Analyse.

### Externes Mindestformat

`PlaylistData_2026-04-08 (2).xlsx`

Enthaelt nur:

- `PLAY #`
- `ODK`
- `QTR`
- `DN`
- `DIST`
- `YARD LN`
- `HASH`
- `PLAY TYPE`
- `RESULT`

Das wirkt wie ein minimales Austausch- oder Lieferformat.

Das ist hilfreich fuer:

- externen Austausch mit Gegnern
- minimale Import- und Exportfaehigkeit
- Baseline fuer Pflichtfelder

## Produktableitung aus dem Vergleich

Fuer `tt-analytics` sind damit drei Ebenen sinnvoll:

1. `external_minimum_schema`
2. `analysis_mvp_schema`
3. `internal_extended_schema`

### External Minimum

Soll importieren und exportieren koennen:

- `PLAY #`
- `ODK`
- `QTR`
- `DN`
- `DIST`
- `YARD LN`
- `HASH`
- `PLAY TYPE`
- `RESULT`

### Analysis MVP

Soll mindestens zusaetzlich tragen:

- `PERSONNEL`
- `OFF FORM`
- `OFF STR`
- `BACKFIELD`
- `OFF PLAY`
- `B/S CONCEPT`
- `PLAY DIR`
- `PASS CATEGORY`
- `TARGET`
- `DEEP SHOT`
- `MOTION`
- `MOTION DIR`

### Internal Extended

Kann spaeter zusaetzlich aufnehmen:

- Coverage
- Blitz
- Pressure
- Front
- Box count
- Spielerbezug
- Kommentare
- Review-Status

## Konsequenz fuer Importe und Exporte

`tt-analytics` sollte langfristig mehrere Mappings unterstuetzen:

- Import eines sehr kleinen Gegnerformats
- Import eines erweiterten Analyseformats
- Export in das von euch geforderte Mindestformat
- internes reichhaltigeres JSON fuer AI und Reporting

## Spaltengruppen

### Spielkontext

- `PLAY #`
- `QTR`
- `SERIES`
- `DN`
- `DIST`
- `YARD LN`
- `HASH`
- `FLD ZN`
- `SITUATION`
- `2 MIN`

### Rollen-/Phasenbezug

- `ODK`
- `TEAM`
- `OPP TEAM`

### Offense / Defense Beobachtung

- `PLAY TYPE`
- `OFF FORM`
- `OFF PLAY`
- `OFF STR`
- `PLAY DIR`
- `PERSONNEL`
- `MOTION`
- `MOTION DIR`
- `PASS CATEGORY`
- `PASS PRO`
- `PASS ZONE`
- `DEF FRONT`
- `DEF STR`
- `COVERAGE`
- `BOX`
- `BLITZ`
- `PRESSURE`

### Ergebnis

- `RESULT`
- `GN/LS`
- `PENALTY`
- `PEN YARDS`
- `RET YARDS`

### Personenbezug

- `PASSER_*`
- `RECEIVER_*`
- `RUSHER_*`
- `TACKLER*`
- `KICKER_*`
- `RETURNER_*`
- `INTERCEPTED BY_*`
- `RECOVERED BY_*`
- `KEY PLAYER_*`

### Freitext / Coaching

- `COMMENTS`

## Produktableitung

Die Vorlage bestaetigt drei wichtige Produktentscheide:

1. Ein Play braucht strukturierte Felder und nicht nur Freitext.
2. Nicht alle Felder sind vollautomatisch aus Video erkennbar.
3. Ein Review-Schritt durch Coaches oder Analysten bleibt wertvoll.

## Empfehlung

Die Hudl-Spalten sollten als Referenz fuer das erste JSON-Schema und spaeter fuer die UI-Felder verwendet werden.

Sie sollten aber nicht unreflektiert 1:1 als Datenbanktabellenspalten uebernommen werden.
