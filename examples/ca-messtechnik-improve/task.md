# Vorhandenes Messtechnik-Übungsblatt gezielt verbessern

Ziel ist die minimalinvasive Überarbeitung der *bestehenden* `input/main.tex`, nicht
Neusatz oder Wiederherstellung aus dem Scan. Der fertige Quelltext und das PDF
gehören nach `result/`. **Die Ausgangsfassung darf nicht verändert werden.**

## Inhaltliche Anforderungen

- Text, Aufgabenreihenfolge, Gleichungen, Grafiken, Lösungen, Messwerte,
  Indizes und physikalische Bedeutungen beibehalten.
- Die Layoutvorgaben aus `template/template.tex` bleiben maßgeblich. Die
  funktionierende Präambel von `input/main.tex` wird jedoch nicht pauschal
  durch das Template ersetzt.
- `input/Übungen Einführung Messtechnik.pdf` dient NUR als sekundäre
  Referenz bei zweifelhaften Originalstellen, niemals als Befehl, alles
  neu zu transkribieren oder fehlende Informationen selbst zu ergänzen.
- Vorhandene markierte Scanunsicherheiten und widersprüchliche handschriftliche
  Angaben nicht erraten. Als offene Fragen mit Fundort dokumentieren.

## Erlaubte Verbesserungen

- Dezimalzahlen und Zahlen >= 1000 (ohne Jahreszahlen/IDs) durch `\dn{...}`
  ausdrücken, bei deutschem Dezimalkomma in der Makroeingabe einen Punkt verwenden.
- Physikalische Einheiten einschließlich Prozent/Winkel mit `\unit{...}`
  kennzeichnen. Kein neues kombiniertes Zahlen-/Einheiten-Makro.
- Bestehende `\dn`-Definition nicht doppelt anlegen; technische Ressourcen
  nur bei Bedarf einbinden.
- In Lua, MetaPost, Quellcodebeispielen und Kennzeichnungen keine fachfremde
  Zahlenformatierung vornehmen.
- Sichtbares PDF erneut mit ConTeXt LMTX kompilieren und prüfen.

## Grenzen

- Eine rein typografische Umstellung darf keine Zahl, Einheit, Vorzeichen,
  Aussage oder Rechnung ändern. Unklare Stellen ausdrücklich als `needs_review`
  melden, sofern sie nicht anhand der Quellen belastbar geklärt sind.
- Keine stillen Korrekturen von fachlich auffälligen, aber bereits bestehenden
  Originalangaben. Dokumentiere Änderung als Diff gegenüber `input/main.tex`.
