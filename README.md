# context-agent 0.1

`context-agent` ist ein kleiner Python-Orchestrator für einen modellgesteuerten Workflow zur
Erstellung von **kompilierten ConTeXt-LMTX-Dokumenten**.

Das Modell arbeitet in einem frischen, von der OpenAI Responses API bereitgestellten
Shell-Container. Es erhält einen vollständigen Job, ein portables ConTeXt-Archiv und die
zugehörigen PDFs/Bilder. Es richtet ConTeXt ein, erzeugt `main.tex`, kompiliert, liest Fehler und
repariert das Dokument selbstständig. Der lokale Python-Code übernimmt anschließend die
No-go-Prüfung und sendet konkrete Befunde zur Reparatur an denselben Agenten zurück.

Die verbindlichen Designentscheidungen stehen in [`DESIGN.md`](DESIGN.md).

## Umfang von Version 0.1

Enthalten sind:

- vollständige Jobs als Verzeichnisse,
- ein vollständiges ConTeXt-Dokument als Template,
- Eingaben mit Rollen und Änderungsregeln,
- direkte Übergabe aller konfigurierten Referenz-PDFs,
- eine frische Hosted-Shell-Sandbox pro Lauf,
- echtes ConTeXt-LMTX-Bootstrapping samt Smoke-Test,
- agentische Compiler-Reparaturen,
- beliebig komplexe lokale Python-No-go-Checker,
- automatische No-go-Reparaturrunden,
- `main.tex`, `main.pdf`, `context.log`, `report.json` und `transcript.jsonl`.

Nicht enthalten sind automatische visuelle PDF-Bewertung, RAG, Vektordatenbank,
Multi-Agent-System und eine Weboberfläche.

## Installation

Python 3.13 wird vorausgesetzt.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Für Entwicklung und Tests:

```bash
python -m pip install -e '.[dev]'
```

Der API-Schlüssel wird ausschließlich über die normale OpenAI-Konfiguration gesetzt:

```bash
export OPENAI_API_KEY='...'
```

## Jobstruktur

```text
mein-job/
├── job.yaml
├── task.md
├── template/
│   └── template.tex
├── input/
│   └── angabe.pdf
├── include/
│   ├── sabel.png
│   ├── mymacros.mp
│   └── plotmod.lua
├── references/
│   └── mathincontext-paper.pdf
└── result/
```

`include/` enthält bewusst sowohl Bilder als auch Codepakete.

## Minimales `job.yaml`

```yaml
model: YOUR_MODEL_ID

task: task.md

template:
  path: template/template.tex

inputs:
  - path: input/angabe.pdf
    role: statement
    policy: immutable

references:
  - references/mathincontext-paper.pdf

runtime:
  context_archive: /absoluter/pfad/context-lmtx-ready.tar.xz
  memory_limit: 4g
  keep_remote: false

limits:
  max_agent_turns: 6
  max_nogo_repairs: 3
  timeout_seconds: 900
  max_output_tokens: 12000
```

### Rollen

- `statement`: verbindliche Angabe, etwa als Quelle einer Musterlösung
- `recreate`: als ConTeXt-Dokument neu zu setzende Vorlage
- `content`: unmittelbar zu verwendender Inhalt
- `reference`: zusätzliche fachliche oder gestalterische Quelle

### Policies

- `verbatim`: Wortlaut muss erhalten bleiben
- `immutable`: fachliche Aussagen, Zahlen und Bedingungen bleiben unverändert
- `editable`: redaktionelle Bearbeitung ist erlaubt
- `guidance`: freie sinnvolle Ausarbeitung ist erlaubt

## Ausführen

```bash
context-agent validate /pfad/zum/mein-job
context-agent run /pfad/zum/mein-job
```

Ein erfolgreicher Lauf schreibt nach `result/`:

```text
main.tex
main.pdf
context.log
report.json
transcript.jsonl
```

Der Exitcode ist `0` bei vollständigem Erfolg, `1` bei einem ausgeführten, aber nicht
abgenommenen Job und `2` bei ungültiger Konfiguration.

## No-go-Checker

Version 0.1 führt immer alle Python-Dateien im konfigurierten No-go-Verzeichnis aus. Ohne
`nogo_directory` wird zuerst `job/nogos/` und anschließend ein projektweites `nogos/`
gesucht. Das mitgelieferte Verzeichnis ist absichtlich leer.

Ein Checker exportiert eine Funktion:

```python
from context_agent.models import NogoFinding
from context_agent.nogos import NogoContext


def check(context: NogoContext) -> list[NogoFinding]:
    source = context.main_tex.read_text(encoding="utf-8")
    if "\\page[yes]" not in source:
        return []
    return [
        NogoFinding(
            rule_id="no-manual-pagebreak",
            message="Manueller Seitenumbruch ist in diesem Dokument unerwünscht.",
            file="main.tex",
            repair_hint="Löse den Umbruch über die vorhandenen Template-Mechanismen.",
        )
    ]
```

Checker sind vertrauenswürdiger lokaler Python-Code. Sie dürfen komplexe Analysen durchführen,
weitere Dateien des Jobs lesen oder externe lokale Werkzeuge aufrufen. Ein Checkerfehler wird
nicht als bestandene Prüfung behandelt, sondern im Bericht als Fehler ausgewiesen.

## Entwicklungsprüfungen

```bash
pytest
ruff check .
mypy
```

Der OpenAI-Livepfad benötigt einen API-Schlüssel und ein Konto mit Zugriff auf Hosted Shell und
Container. Die lokalen Tests verwenden einen Fake-Agenten und verursachen keine API-Kosten.
