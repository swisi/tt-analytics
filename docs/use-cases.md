# Use Cases

## UC-01: Gegner fuer naechstes Spiel vorbereiten

Ein Coach legt den naechsten Gegner an und hinterlegt mehrere Spiele dieses Gegners.

Ziel:

- zentrale Sammlung des Gegner-Footage
- Spielkontext fuer Scouting Report

## UC-02: Mehrere Spiele eines Gegners hochladen

Ja, dieses Szenario ist ausdruecklich vorgesehen.

Ein Gegner kann mehrere Spiele haben, zum Beispiel:

- Gegner vs. Team A
- Gegner vs. Team B
- Gegner vs. Team C

Das System soll nicht nur ein Spiel, sondern eine Serie von Spielen analysieren koennen.

Ziel:

- Muster ueber mehrere Spiele statt Einzelfallanalyse
- besseres Sample fuer Tendenzen

## UC-03: Clips oder Plays je Spiel analysieren

Ein Spiel kann aus vielen einzelnen Clips bestehen.

Beispiel:

- 112 kurze Clips
- pro Clip ein Analyse-Job
- pro Clip ein Ergebnis-JSON

Ziel:

- robuste, standardisierte Play-Analyse
- spaetere Aggregation moeglich

## UC-03a: Nachtlauf fuer komplette Analyse

Ein Coach oder Analyst startet einen Analyse-Lauf fuer viele Plays und muss nicht auf eine sofortige Antwort warten.

Beispiel:

- 112 Clips fuer ein Spiel
- 3 Spiele eines Gegners
- Verarbeitung ueber mehrere Stunden oder ueber Nacht

Ziel:

- praktikabler Batch-Betrieb
- kein manueller Dauerbetrieb waehrend der Analyse
- Report ist spaeter gesammelt verfuegbar

## UC-04: Kontext durch Playbooks und Lernmaterial

Coaches laden zusaetzlich Fachmaterial hoch:

- Offense-Playbook
- Defense-Playbook
- Install-Slides
- PDFs
- Praesentationen
- Notizen

Ziel:

- AI kann Begriffe, Regeln und clubinterne Terminologie besser einordnen

## UC-05: Scouting Report generieren

Das System erzeugt aus mehreren Spielen und vielen Play-Analysen einen Report.

Moegliche Report-Inhalte:

- Formations-Tendenzen
- Run/Pass-Ratio
- Down-and-Distance-Verhalten
- Red-Zone-Verhalten
- 3rd-Down-Tendenzen
- Personnel-Tendenzen
- bevorzugte Konzepte
- konkrete Coaching Points

## UC-06: Analyst reviewt Einzelanalysen

Ein Analyst oder Coach kann einzelne Play-Analysen pruefen und bei Bedarf korrigieren oder neu ausloesen.

Ziel:

- bessere Datenqualitaet
- weniger Black-Box-Verhalten

## UC-07: Unterschiedliche Rollen in Analytics

Ein Benutzer kann in `tt-analytics` andere Rechte haben als in anderen Services.

Beispiele:

- Coach A ist `admin` in `agenda`, aber nur `user` in `analytics`
- Coach B ist Plattform-Admin in `tt-auth`, aber in `analytics` nur `user`
- Analyst C ist `admin` in `analytics`

## UC-08: Wiederverwendung von Trainingsmaterial

Bereits hochgeladene Gegnerfilme und Wissensdokumente sollen fuer spaetere Reports erneut nutzbar sein.

Ziel:

- weniger Doppeluploads
- besserer Wissensaufbau ueber Zeit

## UC-09: Report fuer Staff bereitstellen

Coaches und Staff sollen Reports lesen koennen, ohne alle Rohdaten oeffnen zu muessen.

Ausgabeformen:

- Webansicht
- PDF-Export
- spaeter ggf. druckfreundliche Staff-Version

## UC-10: Eigene Spiele automatisch kartieren

Ja, das ist ein sehr naheliegender spaeterer Ausbau.

Eigene Spielvideos koennen mit demselben Grundsystem analysiert und vorgetaggt werden.

Moegliche Ziele:

- eigene Offense-Plays kartieren
- eigene Defense-Plays kartieren
- eigenes Special Teams tagging vorbereiten
- Vorbefuellung fuer Hudl- oder Staff-Workflows

Wichtig:

- fuer eigene Spiele ist die AI nicht nur Scouting-, sondern auch Tagging-Hilfe
- das Ergebnis sollte als Vorbelegung fuer menschliche Review dienen, nicht als unkontrollierte Endwahrheit

## UC-11: Export in Gegner-Mindestformat

Ein intern reichhaltig analysiertes Spiel soll in ein kleineres, extern nutzbares Format exportiert werden koennen.

Ziel:

- Vereinheitlichung interner Analyse und externer Lieferung
- weniger manuelle Doppelarbeit
