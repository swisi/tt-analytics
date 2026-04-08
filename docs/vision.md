# Vision

## Produktidee

`tt-analytics` soll Coaches des American-Football-Clubs bei der Spielvorbereitung unterstuetzen.

Der Kernnutzen ist:

- gegnerische Spiele hochladen
- Plays strukturiert analysieren
- Muster und Tendenzen ueber mehrere Spiele erkennen
- daraus einen kompakten, coaching-tauglichen Report generieren

## Hauptszenario

Vor einem Spiel gegen Gegner X werden ein oder mehrere Spiele dieses Gegners hochgeladen.

Beispiel:

- 3 Spiele des Gegners
- pro Spiel 80 bis 120 Clips
- pro Clip eine AI-Analyse als JSON
- aus allen Play-Analysen ein Scouting Report fuer das naechste Spiel

Die Spiele liegen dabei bereits in einzelne Spielzuege bzw. Clips zerlegt vor.

Das System arbeitet daher nicht mit vollstaendigen Rohspielen als Primaereinheit, sondern mit einer Sammlung einzelner Plays pro Spiel.

## Warum mehrere Spiele wichtig sind

Ein einzelnes Spiel ist oft zu schmal als Grundlage.

Mehrere Spiele erlauben:

- Tendenzen ueber groessere Samples
- Erkennung situativer Muster
- Abgleich gegen verschiedene Gegner
- robustere Aussagen fuer 1st down, 3rd down, red zone, short yardage oder personnel-Gruppen

## Zielgruppen

- Head Coach
- Coordinator
- Position Coaches
- Quality Control / Analyst Staff

## Ergebnisarten

- Play-by-Play-Analyse
- Serien- oder Drive-Auswertung
- Spielauswertung
- Multi-Game-Scouting Report
- Export als PDF oder Web-Ansicht

## Nicht-Ziele fuer MVP 1

- vollautomatisches Video-Tagging ohne menschliche Kontrolle
- Live-Analyse waehrend eines Spiels
- komplexe Diagramm-/Telestration-Features
- automatische Erkennung aller Football-Schemes mit hoher Verlaesslichkeit

## Produktprinzipien

- strukturierte Outputs statt freie Fliesstexte als Primärdaten
- jeder Analyse-Schritt soll nachvollziehbar und versionierbar sein
- menschliche Review bleibt moeglich
- guenstiger Testbetrieb vor teurem Produktionsbetrieb
- lange Laufzeiten fuer Analysejobs sind akzeptabel, solange der Ablauf robust und nachvollziehbar bleibt
