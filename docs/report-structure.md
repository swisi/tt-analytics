# Report Structure

## Ziel

Ein Report soll nicht nur ein Sammelbecken freier AI-Texte sein.

Er soll fuer Coaches schnell lesbar und wiederholbar aufgebaut sein.

## Report-Typen

- `single_game`
- `multi_game_opponent`
- `self_scout`

## Empfohlene Standardstruktur fuer Gegner-Scouting

### 1. Executive Summary

Kurze Zusammenfassung fuer Coordinator oder Head Coach:

- wichtigste Tendenzen
- groesste Stärken des Gegners
- groesste Angriffs- oder Verteidigungsrisiken
- 5 bis 10 konkrete Coaching Points

### 2. Sample und Datenbasis

- wie viele Spiele analysiert wurden
- wie viele Clips eingeflossen sind
- welche Spiele betrachtet wurden
- welche Datenluecken oder Unsicherheiten existieren

### 3. Personnel und Formations

- haeufigste Personnel-Gruppen
- haeufigste Formationen
- Tendenzen nach Hash, Down oder Field Zone

### 4. Play-Type Tendencies

- Run/Pass-Verteilung
- Screen, Quick Game, Shot Plays
- Special Situations

### 5. Situational Football

- 1st Down
- 2nd and long
- 3rd and short / medium / long
- Red Zone
- Goal Line
- Two-Minute

### 6. Directional Tendencies

- Run Left / Middle / Right
- Pass Short / Intermediate / Deep
- Target-Tendenzen
- Motion-Richtungen

### 7. Protection / Pressure / Coverage Hinweise

Je nach Analysemodus:

- Pass Protection Tendenzen
- erkennbare Blitz- oder Pressure-Muster
- Coverage-Vermutungen

### 8. Top Plays / Example Clips

- auffaellige oder repräsentative Clips
- Links auf Beispiele
- kurze Erklaerung, warum diese Plays wichtig sind

### 9. Coaching Recommendations

- konkrete Vorbereitung fuer Training
- welche Checks, Calls oder Alerts relevant sind
- was im Meeting betont werden sollte

## Standardstruktur fuer Self-Scout

- Run/Pass-Verteilung
- Formation- und Personnel-Tendenzen
- Situational Tendencies
- explosive Plays
- negative Plays
- Tendenzen, die fuer Gegner leicht lesbar sind
- Coaching Points fuer Korrekturen

## Struktur fuer Report-JSON

Empfohlene Grundstruktur:

```json
{
  "report_type": "multi_game_opponent",
  "title": "Scouting Report vs. Opponent X",
  "sample": {
    "games_analyzed": 3,
    "clips_analyzed": 284
  },
  "sections": [
    {
      "key": "executive_summary",
      "title": "Executive Summary",
      "content": []
    },
    {
      "key": "personnel_formations",
      "title": "Personnel and Formations",
      "content": []
    }
  ],
  "key_points": [],
  "risks": [],
  "generated_from_run_id": 42
}
```

## MVP-Schnitt

Fuer den ersten Report genuegen:

- Executive Summary
- Sample
- Personnel / Formations
- Run/Pass Tendencies
- Situational Football
- Coaching Points
