# 0.9.4 – Sicheres Zahlen-/Einheiten-Regression-Gate und Diagnose

- Erfasst vollständige Dezimal- und Ganzzahlen auch direkt vor einer Einheit
  (z. B. `200Ω`, `0,152kΩ`, `7,5V`) und normalisiert `\dn`, `\mathrm`,
  `\unit`, Prozent und häufige SI-Schreibweisen vor einem **exakten** Vergleich.
- Schützt Zahlenwerte, Vorzeichen und erkannte Einheiten unabhängig. Bei
  unbekannten Konstruktionen ersetzt dies keine unabhängige semantische Prüfung.
- Schreibt alle Rollback-Ursachen als stabile, datensparsame `regression_rollback`-
  Ereignisse ins Host-Log und erfasst abgelehnte Quell-Prüfsummen.
- Erfasst Generator-Shell-Calls, Befehls-Prüfsummen/-Längen und Shell-Ergebnisse
  (keine Shell-Befehlsinhalte, stdout/stderr oder Credentials).
- Ersetzt nur **nachweislich überholte** statische Verfügbarkeitswarnungen
  durch Laufzeitevidenz; ursprüngliche Scanunsicherheiten bleiben erhalten.
- Zusätzliche Tests mit Originalschreibweisen aus dem Messtechnikbeispiel,
  manipulierten Zahlen/Einheiten, Rollback-Ereignissen und Log-Redaktion.
- Kein vollständiger Hosted-Live-Test ohne OpenAI-Zugang.
