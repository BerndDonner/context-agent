# context-agent 0.9 – ConTeXt-Dokumente erstellen und verbessern

`context-agent` erzeugt oder überarbeitet mit zwingend gewähltem `mode` aus Aufgabe, verbindlichem Template und Eingabedokumenten eine kompilierte ConTeXt-LMTX-Fassung über die OpenAI Responses API mit Hosted Shell. Ziel ist eine möglichst hochwertige Ausgangsbasis für die manuelle Nachbearbeitung. Der Originalauftrag bleibt während aller Reparaturen der entscheidende Maßstab.


### Präflight-Diagnose und ungültige Modell-Pläne

Bereits **vor** einem Hosted-Containerlauf schreibt der Agent
`<job>/.context-agent/preflight-events.jsonl`. Dieses Protokoll bleibt auch bei
Präflight-Fehlern erhalten, ohne ein bestehendes `result/` zu überschreiben.
Es enthält API-Status und Response-ID sowie eine redigierte Strukturbeschreibung
von `plan`, aber keine Modellantwort, Prompts oder Dokumentinhalte.

Fehlt der vom Modell vorgeschlagene Ausführungsplan, ist er unvollständig oder
enthält er unbekannte Regeln, wird **nur** die optionale Batch-Planung durch
Einzelregel-Batches in der Reihenfolge der expliziten `quality`-Liste ersetzt.
Der vorangestellte Konsistenzentscheid bleibt verbindlich: `blocked`,
blockierende Requirements-Konflikte oder fehlerhafte Präflight-Urteile
stoppen den Auftrag weiterhin. Der Fallback ist unter
`report.json` → `consistency.plan_fallback_reason` nachvollziehbar.

## Anforderungen

Python ab 3.13, die in `pyproject.toml` genannten Abhängigkeiten, ein OpenAI-API-Key in `OPENAI_API_KEY` und ein für den Job angegebenes ConTeXt-LMTX-Archiv. Für lokale PDF-Prüfungen wird PyMuPDF verwendet. Der Hosted-Container führt den eigentlichen Satzlauf mit dem mitgelieferten flüchtigen Runner aus.

```bash
python -m pip install -e '.[dev]'
context-agent validate /pfad/zum/job
context-agent run /pfad/zum/job
context-agent resume /pfad/zum/job
```

`validate` prüft Struktur und YAML; die semantische Konsistenzprüfung findet erst bei `run` **vor** der Containererstellung und Ergebnislöschung statt. `resume` setzt einen unvollständigen Lauf in `.resume-work` fort. Bereits erfolgreich beendete Jobs sind nicht für `resume` vorgesehen.

## Aufbau eines Jobs

```text
mein-job/
├── job.yaml
├── task.md
├── template/template.tex
├── input/                # optionale unveränderliche Eingaben
├── include/              # mitgelieferte Helfer
└── result/               # PDF, TeX, Logs, Berichte, Checkpoints
```

Minimalbeispiel (`runtime.context_archive` muss auf deinem System existieren):

```yaml
mode: create
model: gpt-6
reasoning:
  effort: medium
processing:
  mode: standard
task: task.md
template:
  path: template/template.tex
inputs: []
references: []
runtime:
  context_archive: /pfad/context-lmtx-ready.tar.xz
limits:
  max_agent_turns: 24
  max_quality_repairs: 3
  max_output_tokens: 12000
  timeout_seconds: 900
review:
  reproduction: false
  max_content_repairs: 2
  max_visual_repairs: 2
quality:
  - dollar_math
  - semantic_numbers
  - semantic_math_text
  - number_with_unit
  - coordinate_reuse
```

**`mode` und `quality` sind in jedem Job Pflicht.** `mode: create` beginnt bei Template und Quellen; `mode: improve` verwendet `source.path` als unveränderliche Ausgangsfassung. Ein fehlender Modus ist ein Konfigurationsfehler.

**`quality` ist in jedem Job Pflicht**, auch `quality: []` ist zulässig. Es gibt keine Profile und keine automatische Auswahl anhand des Fachs oder Inhalts. Nur die von dir explizit angegebenen Regeln werden ausgeführt. `quality_directory` erlaubt ein zusätzliches Verzeichnis mit eigenen Regeln (nicht erforderlich für eingebaute Regeln).

Ein Beispieljob für einen Mathematikauftrag darf `syntax-highlighting` natürlich weglassen. Die fünf gegenwärtig ausgelieferten IDs sind exakt die oben gezeigten. Zusätzliche Regeln können später in der gleichen Struktur erstellt und explizit ausgewählt werden.

## Quality Rules

Eine Regel besteht aus `rule.yaml`, einem optionalen lesenden `checker.py`, einem optionalen deterministischen `refinement.py` und möglichen Ressourcen. Existiert kein deterministischer Fixer, kann das Refinement mit den aus `rule.yaml` bereitgestellten Reparaturhinweisen durch das LLM ausgeführt werden. Checker-Meldungen sind `confirmed`, `candidate` oder `warning`; Warnkandidaten werden nicht als Beweis behandelt.

Verzeichnisbeispiel:

```text
src/context_agent/resources/quality_rules/
  semantic_numbers/
    rule.yaml
    checker.py
    refinement.py
    resources/digits.tex
```

Die fünf Regeln sind:

| ID | Konvention |
|---|---|
| `dollar_math` | Keine ausgeführte Mathematik mit `$...$`; ConTeXt-Mathematikmakros verwenden |
| `semantic_numbers` | Dezimalzahlen und numerische Größen ab 1000 mit `\dn`, Jahreszahlen ausgenommen |
| `semantic_math_text` | Sprachliche Formelteile mit `\text` bzw. `\mtext` statt `\rm` |
| `number_with_unit` | `10\unit{km/h}`, `\dn{5}\unit{Meter}`, `30\unit{Degree}`, `\dn{12.5}\unit{Percent}` |
| `coordinate_reuse` | Logisch identische MetaPost-Punkte benennen; identische Zahlenpaare zunächst nur als Kandidaten melden |

Die Definition des Zahlenmakros `\dn` gehört zur Regel `semantic_numbers`, nicht ins globale Schul-Template. Das Einheiten-Refinement kann diese Ressource technisch mitverwenden, ohne die Zahlenregel zu aktivieren. Der Bundler liefert die Makrodatei im Hosted-Job mit, der Generator bindet sie bei Bedarf ein, und der Include-Snapshot bewahrt sie für eine spätere unabhängige Kompilierung.

## Pipeline und Qualitätssicherung

1. **Konsistenzprüfung** gegen Originalauftrag, Template und ausgewählte Qualitätsregeln, bevor vorhandene Ergebnisse gelöscht werden. Bei einem relevanten Konflikt: Abbruch mit Ursache. Der LLM-Preflight plant außerdem Batches und Reihenfolge **ausschließlich** für die ausgewählten IDs.
2. **Erstellung und echte Kompilierung** im Hosted-Container. Output: `main.tex`, `main.pdf`, `context.log` und `include-snapshot.tar.gz`.
3. **Unabhängige Requirements Validation** vor der Refinement-Phase; bei Reproduktionsaufträgen mit Quellinventar, Inhalts- und visueller Prüfung.
4. **Validierter Dokument-Snapshot** in `result/.validated/` mit SHA-256-Hashes der zusammengehörigen Artefakte.
5. **Checker und Refinements**: Regeln prüfen denselben Dokument-/Include-Zustand. Python-Autofixes sind gegen den Ausgangshash geschützt und dürfen sich nicht überlappen. Komplexere Fälle bearbeitet das LLM.
6. **Regression Gate** nach jeder Reparatur: Requirements erneut gegen Originalauftrag prüfen, anschließend Verschlechterungen anderer ausgewählter Qualitätsregeln erkennen. Bei Regression: Rollback.
7. **Ergebnis**: `success` / `needs_review` / `failed` sowie `report.json`, `transcript.jsonl`, ggf. `uncertainties.md` und Validierungs-/Reparaturjournal.

Ein ConTeXt-Build allein ist **kein** Korrektheitsbeweis. Wer einen Validierungsstatus `uncertain` erhält, bekommt deshalb keinen falschen `success`. `needs_review` lässt einen besten überprüften Zwischenstand erhalten. Für die Wiederaufnahme ist `result/checkpoint.json` vorgesehen, nicht das transaktionale Verzeichnis `.validated`.

**Wichtig:** Die LLM-Checker und Requirements-Audits sind probabilistisch und keine formalen Beweise. Die statischen Zahlen-/Einheiten- und Koordinatenscanner sind absichtlich konservative Kandidatenerkenner. Der dynamische Dollar-Linter dagegen untersucht die tatsächlich ausgeführte ConTeXt-Syntax. Ein echter Hosted-LMTX-/API-Abnahmetest ist weiterhin erforderlich; die Testsuite enthält Offline-Fakes.

Weitere technische Details, Abhängigkeiten und Grenzen stehen in [DESIGN.md](DESIGN.md). Geplante Ergänzungen und offene Testfälle stehen in [TODO.md](TODO.md).

## Überarbeitungsaufträge (`mode: improve`)

Im Beispiel [`examples/ca-messtechnik-improve`](examples/ca-messtechnik-improve)
wird ein vorhandenes Messtechnikblatt überarbeitet. Das Original-PDF ist
Referenz, **keine** Aufforderung zur Rekonstruktion. Konfiguration:

```yaml
mode: improve
source:
  path: input/main.tex
task: task.md
template:
  path: template/template.tex
inputs: []
references:
  - input/Übungen Einführung Messtechnik.pdf
review:
  reproduction: false
quality:
  - semantic_numbers
  - number_with_unit
```

`mode: improve` erfordert `source.path` (eine vorhandene `.tex` **außerhalb**
von `result/`), `review.reproduction: false`; `mode: create` verbietet
`source`. Ein Implizit-Modus ist nicht zulässig. Alle bisherigen Beispieljobs
wurden auf `mode: create` migriert.

Ablauf: Der Bundler legt eine **bytegenaue** Kopie von `source.path` als
`result/main.tex` bei. Die erste Hosted-Runde ist nur ein Baseline-Compile:
es darf keine Quelltextänderung stattfinden. Ein SHA-256-validierter
`result/.baseline/`-Snapshot sichert auch dann den kompilierbaren Ursprungsstand,
wenn bereits Inhaltshinweise oder Scanunsicherheiten existieren. Weitere Änderungen
werden gegenüber der Originaldatei mit `result/changes.diff` protokolliert.
Die erste unveränderte Baseline wird nicht wiederholt als unerfüllter
Verbesserungsauftrag begutachtet. Nach Änderungen prüft die unabhängige
Requirements Validation weiterhin Originalauftrag, Quellcode, Ausgabeseiten,
Diff und die **tatsächlich angehängten** Original-PDFs. Nur durch Quelländerungen
belegte neue Requirements-Regressionen sowie geänderte numerische Literal-Mengen
führen zum Rollback; schwach belegte Verdachtsfälle werden als Unsicherheit
protokolliert.
Vorhandene Unsicherheiten bleiben erhalten und können `needs_review` auslösen,
blockieren aber nicht mehr zwingend jede reine Qualitätsverbesserung.

**Grenze:** Die konservative numerische Inventarprüfung erkennt Zahländerungen,
aber **keine** vollständige TeX-Semantik. Insbesondere Vorzeichen-Neuordnung,
Änderungen an Indizes, Bedeutungen von Einheiten und Formelstruktur benötigen
zusätzlich den unabhängigen LLM-Requirements-Review. Der Guard sperrt momentan
auch ausdrücklich gewünschte Zahlenwertänderungen: Ein allgemeiner
Inhaltskorrektur-Modus mit nachweisbarer Änderungsfreigabe ist noch nicht vorhanden.

### Lokaler ConTeXt-Test (kein API-Key)

Die Bereitstellung enthält `scripts/local-lmtx.sh`. Ein bestehendes `.tex`
mit funktionierenden relativen Include-Pfaden kann so geprüft werden:

```bash
bash scripts/local-lmtx.sh /pfad/context-lmtx-ready.tar.xz /pfad/job/result/main.tex
```

Der Runner entpackt die mitgelieferte Linux-x86-64-LMTX-Distribution
in ein temporäres Verzeichnis, erstellt einen Schreibcache, kompiliert in
Quelltext-Nähe und räumt anschließend seine Installation auf.
Die API-gestützte `run`-Pipeline wird dadurch nicht ersetzt.

### Zuverlässigkeit der Hosted Shell (0.9.1)

Unvollständige Responses oder vorzeitig fehlende Shell-Tool-Ausgaben werden
begrenzt erneut abgefragt. Eine neue Ausführungsanfrage verwendet stets dieselbe
Prozess-ID; der containerseitige Supervisor erkennt identische Starts als
idempotent, lehnt aber abweichende Befehle mit derselben ID ab. Das verhindert
doppelte Seiteneffekte bei verlorenen API-Bestätigungen.

Die Original-PDF-Referenz wird unabhängigen Improve-Reviewern als `input_file`
mitgeschickt. Das erhöht den Preis der unabhängigen Reviews, liefert ihnen aber
die Scaninformation tatsächlich. Noch kein erneuter Hosted-End-to-End-Test
mit Produktions-API-Key durchgeführt.

### Diagnose bei Hosted-Fehlern (0.9.2)

Bei jedem Lauf des OpenAI-Backends entsteht `result/execution-events.jsonl`.
Die Ereignisse enthalten nur technische Metadaten (Zeitstempel, IDs, Status,
Prozessschritte, Upload-Prüfsumme und -Größe, Retry, Fehlerklassen und
Tokenverbrauch), **keine** Shell-Befehle, Quelldatei- oder Edit-Inhalte.
Auch fehlgeschlagene Starts/Statusabfragen und Rollbacks sind erfasst.
Zum Debugging nach einem `needs_review` bitte neben `report.json`,
`checkpoint.json`, `changes.diff` und `transcript.jsonl` dieses Log mitgeben.
`transcript.jsonl` kann dagegen vollständige Modell- und Toolausgaben
enthalten und sollte vor einer Weitergabe auf sensitive Inhalte geprüft werden.

Große deterministische Qualitätskorrekturen werden nicht mehr als Base64-
Shell-Argument gesendet. Der Host lädt sie direkt über die Container-Files-API
als JSON hoch und übergibt nur Pfad und SHA-256 an den Prozess-Supervisor.
Die Original-Quellhashes werden zusätzlich im Remote-Apply-Skript geprüft.

### Improve-Regression und Diagnose (0.9.4)

`improvement_guard` vergleicht Dezimalzahlen nun unabhängig von angrenzenden
Einheiten, beispielsweise `0,152kΩ` versus `\dn{0.152}\unit{kOhm}`.
Er prüft zusätzlich die Identität erkannter physikalischer Einheiten und blockiert
Umstellungen wie `200Ω` zu `200\unit{Volt}` ebenso wie Zahl- oder
Vorzeichenänderungen. Für unbekannte Makros und semantische Kontexte bleibt
der unabhängige Requirements-Review notwendig; der Guard ist kein vollständiger
ConTeXt-Interpreter.

`execution-events.jsonl` enthält nun die Gründe **aller** Workflow-Rollbacks
mit stabilen Fehlercodes, Anzahl der Abweichungen und dem SHA-256 der
abgelehnten Ausgangsfassung (soweit vorhanden). Generator-Shell-Aktionen
werden über Befehlshash/-länge, Ausführungsstatus sowie optional Exitcode
und Outputlängen sichtbar, aber ohne Befehlstext und Outputdaten.

Der Qualitätsbericht nimmt statische Aussagen über fehlende Lint- und
ConTeXt-Läufe bzw. fehlende Include-Ressourcen aus der aktiven Fundliste,
**nur wenn** die entsprechende Laufzeitevidenz tatsächlich vorliegt.
Der historische Präflight-Befund bleibt nachvollziehbar und erhält
`consistency.runtime_evidence`; offene Scanstellen bleiben ausdrücklich offen.
Der gesamte Hosted-End-to-End-Prozess braucht weiterhin einen realen API-Test.

### Qualitätsgruppen-Fortschritt und semantische Evidenz (0.9.5)

Eine Qualitätsgruppe ohne reparierbare Befunde gilt sofort als erfüllt. Insbesondere
führt ein erfolgreicher dynamischer `dollar_math`-Checker **nicht** mehr zu einem
Refinement, nur weil das Modell eine unklare Einheit gemeldet hat. Der Präflight-
Plan wird gruppenweise abgearbeitet; ein wirkungsloser Reparaturversuch wird nur
für die aktuelle `(Quellrevision, Regelgruppe)` als bearbeitet markiert und hindert
andere ausgewählte Gruppen nicht. Ein neuer Quellstand wird neu geprüft.

Zusätzliche LLM-Findings müssen eine gültige Quellzeile und einen wörtlich in
dieser Zeile vorkommenden `evidence`-Text angeben. Für `dollar_math` ist nach
ausgeführtem dynamischen Linter dessen Befund maßgeblich. Unverifizierte oder
falsch zugeordnete Modellmeldungen kommen nach `quality_uncertainties`,
**nicht** in die Reparatur-Queue. Sie bleiben in `report.json` und gegebenenfalls
`uncertainties.md` überprüfbar und können weiterhin `needs_review` bewirken.

Der `quality_journal` enthält `quality_group_satisfied`,
`quality_group_no_progress` und `quality_groups_exhausted`; für No-ops gibt es
auch ein datensparsames `execution-events.jsonl`-Ereignis. Die alten Prüfungen
und `mode: create` werden weiterhin unterstützt.
