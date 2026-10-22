# improve: Messtechnik-Zahlen und Einheiten

Ein neuer Auftrag mit `mode: improve`: `input/main.tex` ist die unveränderliche
Ausgangsfassung, das Original-PDF ist nur Referenz. `quality` legt die
Checker explizit fest. Keine automatische Abschrift des PDFs.

`context-agent validate examples/ca-messtechnik-improve` überprüft die Struktur.
`context-agent run examples/ca-messtechnik-improve` nutzt die konfigurierte
Responses API und Hosted Shell (API-Schlüssel erforderlich).

Die erste Runde kompiliert die unveränderte Vorlage. Bei späteren Korrekturen
werden Änderungsschutz, Requirements Gate und Qualitätsregeln verwendet.
