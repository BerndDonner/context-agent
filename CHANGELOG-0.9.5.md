# 0.9.5 – Qualitätsgruppen sicher fortsetzen

- Erfüllte Gruppen im geplanten Reihenfolgelauf ohne Reparaturaufruf überspringen.
  `dollar_math` mit leerem dynamischem Linter blockiert die nachfolgenden Regeln nicht.
- No-op-Refinements gruppenbezogen statt quellenweit verfolgen; bei gleichem
  Quellenhash andere Gruppen erlauben, dieselbe Gruppe nicht endlos wiederholen.
- Semantische Modellfindings nur mit konkreter Zeile und exakt verifizierbarem
  `evidence`-Ausschnitt in die Reparaturwarteschlange aufnehmen. Der dynamische
  Dollar-Linter bleibt für `dollar_math` maßgeblich.
- Semantische Unsicherheiten ohne erfundene Regelzuordnung in
  `quality_uncertainties` und `uncertainties.md` festhalten.
- Regressionstests für saubere Erstgruppe, falsch zugeordnete Unsicherheit,
  No-op-Weiterlauf und einen kompletten Fake-Improve-Lauf mit `\dn` und `\unit`.
- Echte Hosted-End-to-End-Abnahme über die OpenAI-API steht noch aus.
