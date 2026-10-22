# context-agent 0.9 – ConTeXt-Dokumente erstellen und verbessern

`context-agent` erzeugt oder überarbeitet mit zwingend gewähltem `mode` aus Aufgabe, verbindlichem Template und Eingabedokumenten eine kompilierte ConTeXt-LMTX-Fassung über die OpenAI Responses API mit Hosted Shell. Ziel ist eine möglichst hochwertige Ausgangsbasis für die manuelle Nachbearbeitung. Der Originalauftrag bleibt während aller Reparaturen der entscheidende Maßstab.

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
Die Requirements Validation prüft weiter Originalauftrag, Referenzen, Quellcode,
Ausgabeseiten und Diff. Neu eingeführte Requirements-Verstöße oder veränderte
numerische Literal-Mengen führen zum Rollback auf den letzten überprüften Stand.
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
