# context-agent 0.5.0

`context-agent` ist ein kleiner Python-Orchestrator für einen modellgesteuerten Workflow zur
Erstellung von **kompilierten ConTeXt-LMTX-Dokumenten**.

Das Modell arbeitet in einem frischen, von der OpenAI Responses API bereitgestellten
Shell-Container. Es erhält einen vollständigen Job, ein portables ConTeXt-Archiv und die
zugehörigen PDFs/Bilder. Es richtet ConTeXt ein, erzeugt `main.tex`, kompiliert, liest Fehler und
repariert das Dokument selbstständig. Der lokale Python-Code übernimmt anschließend die
No-go-Prüfung und sendet konkrete Befunde zur Reparatur an denselben Agenten zurück.

Die verbindlichen Designentscheidungen stehen in [`DESIGN.md`](DESIGN.md).

## Umfang von Version 0.4

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
- optional aktivierbare **quellenbasierte Inhaltsinventarisierung und unabhängige
  Vollständigkeitsprüfung** sowie getrennte visuelle Reproduktionsprüfung,
  jeweils mit automatischer Reparaturschleife bei sicher belegten Fehlern,
- `needs_review` statt uneingeschränktem Erfolg bei verbleibenden Unsicherheiten,
- detaillierte Token-/Cache-/Shell-Metriken pro Runde und eine Prüf-Historie,
- Git-kompatibler **Include-Roundtrip**: neue/geänderte Dateien in `include/` werden erst
  nach erfolgreicher Abnahme zurückgeschrieben, ohne Commit oder Push,
- `main.tex`, `main.pdf`, `context.log`, `include-snapshot.tar.gz`,
  `report.json` und `transcript.jsonl`.

Nicht enthalten sind typografische Optimierung, RAG, Vektordatenbank,
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

Der Agent erwartet den API-Schlüssel ausschließlich in der Umgebungsvariable
`OPENAI_API_KEY`. In der Nix-DevShell wird sie über das zentrale Secret-Handling aus der
gepinnten `NixOS-Config` geladen:

```nix
secretSets = [ "openai" ];
```

Damit reicht im normalen Entwicklungsworkflow:

```bash
nix develop
```

Außerhalb der DevShell muss `OPENAI_API_KEY` vor dem Start auf anderem Weg in der
Umgebung gesetzt werden. Der Agent liest keine Schlüsseldatei aus dem Repository.

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
model: gpt-6.1-sol

# Optional: omitting this uses the model's default reasoning effort.
reasoning:
  effort: high

# auto (default), standard, or flex. True Batch is not supported
# by this short-lived, multi-turn Hosted-Shell workflow.
processing:
  mode: flex

task: task.md

template:
  path: template/template.tex

inputs:
  - path: input/angabe.pdf
    role: recreate
    policy: verbatim

references:
  - references/mathincontext-paper.pdf

runtime:
  context_archive: /absoluter/pfad/context-lmtx-ready.tar.xz
  memory_limit: 4g
  keep_remote: false

limits:
  max_agent_turns: 24  # bei längeren Scans Platz für Inventar + Inhalt + Sichtprüfung
  max_nogo_repairs: 3
  timeout_seconds: 900
  max_output_tokens: 12000

# Nur für originalgetreue Reproduktionsaufträge einschalten.
review:
  reproduction: true
  max_repairs: 2
  max_pages: 40
  pages_per_batch: 4
```

### Modell, Reasoning und Verarbeitungstarif

`model` bleibt frei konfigurierbar (z. B. `gpt-6.1-sol`). Neue optionale Felder:

```yaml
model: gpt-6.1-sol
reasoning:
  effort: high
processing:
  mode: flex
```

- `reasoning.effort`: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
  Welche Stufen erlaubt sind, hängt vom Modell ab: **GPT-6.1 Sol akzeptiert
  `low`, `medium`, `high`, `xhigh`, `max`.** Der Agent sendet nur dann den
  `reasoning`-Parameter, wenn er ausdrücklich gesetzt ist. Er gilt für
  Generierung, Reparatur und Reproduktionsreview gleichermaßen.
- `processing.mode: auto` (Standard): wie bisher wird der API-/Projektstandard
  verwendet. `standard` erzwingt `service_tier: default`;
  `flex` setzt `service_tier: flex` für **Batch-Tarife (50 % weniger
  Tokenkosten)** bei normaler, synchroner Responses-API-Orchestrierung.
  Flex kann deutlich langsamer sein oder wegen Kapazitätsmangels fehlschlagen.
  Der Agent wechselt **nicht automatisch** auf einen teureren Tarif.
- `processing.mode: batch` wird bewusst mit einem klaren Validierungsfehler
  abgewiesen: Die echte Batch API ist asynchron (bis 24 h) und passt nicht
  zum kurzlebigen Hosted-Shell-Container und zur sequentiellen Reparatur- und
  Review-Schleife. Das wäre eine eigene persistente Job-/Wiederaufnahme-Architektur.
  **Flex ist keine Batch API**, bietet aber dieselben reduzierten Tokenpreise.

Die tatsächlichen Verarbeitungspreise gelten laut aktueller OpenAI-Dokumentation
modell- und tarifabhängig; Hosted-Container- und sonstige Toolkosten sind nicht
notwendigerweise um 50 % reduziert. Ohne `reasoning`/`processing` funktionieren
alte `job.yaml`-Dateien unverändert. `report.json` protokolliert beide Einstellungen sowie von der API
beobachtete Service-Tiers, sofern diese in der Antwort stehen.

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

### Verbindliche ConTeXt-Mathematik-Konvention (seit 0.3.1)

`main.tex` muss für Inline-Mathematik `\m{...}` und für abgesetzte Formeln
`\startformula ... \stopformula` verwenden. TeX-/LaTeX-typische
`$...$` und `$$...$$` sind in generiertem ConTeXt-Quelltext verboten.
Der **eingebaute** No-go-Checker `context-dollar-math` läuft bei **jedem Job**,
unabhängig von `nogo_directory`, nach dem Compile und **vor** der
Reproduktionsprüfung und der Übernahme von `include/`. Er meldet genaue
Zeilennummern und löst über `limits.max_nogo_repairs` die bereits vorhandene
automatische Reparaturschleife aus. Bleiben Verstöße bestehen, schlägt
der Job fehl. Literalbeispiele (`\type{...}`, `\starttyping`), Kommentare
und MetaPost-/Lua-Code werden nicht fälschlich als Formeltext geprüft.
Der Check kontrolliert die Syntax von `main.tex`, **nicht** die fachliche
Richtigkeit mathematischer Ausdrücke.

Bei MetaPost-Grafiken sollen relevante Punkte und Ereignisse einmal definiert,
und bei Linien, Beschriftungen und Hilfskonstruktionen **wiederverwendet** werden.
Das ist bewusst eine allgemeine **Generierungsvorgabe**, kein pauschales
Verbot fester Zahlen: Maße, Abstände und unabhängige Koordinaten bleiben erlaubt.

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
include-snapshot.tar.gz
report.json
transcript.jsonl
```

`review.reproduction` ist standardmäßig **ausgeschaltet**. Ohne diese Option bleibt
auch für andere Arten von Jobs (z. B. neue Übungsaufgaben erstellen) der bisherige
Ablauf erhalten. Mit `review.reproduction: true` laufen drei getrennte Schritte:

1. **Quelleninventar VOR der Erzeugung:** Der schreibende Agent wird erst gestartet,
   nachdem ein read-only Modellaufruf alle maßgeblichen Quellen inventarisiert hat.
   Das Inventar wird als überprüfbare Checkliste an die Erzeugung übergeben.
   Der prüfende Modellaufruf erhält dabei keinen vorherigen Erzeugungsverlauf.
   Der Agent prüft die maßgeblichen Eingaben (`role: recreate`
   sowie verbindliche `content`-/`statement`-Quellen) anhand der tatsächlichen
   Quellseiten. Auch Scan-PDFs **ohne Textebene** werden seitenweise als Bilder
   bereitgestellt. Das Modell inventarisiert nur den in `task.md` beauftragten
   Inhalt: Aufgaben, Zahlen, Formeln, Diagramme, Beschriftungen und vorhandene
   Lösungen. Bewusst ausgeschlossene Quellteile gehören nicht zum Inventar.
2. **Unabhängiger Inhaltsabgleich:** Die gerenderten Ausgabeseiten werden
   inventarbezogen überprüft. Sichere Abweichungen führen zu einer automatischen
   Reparatur. Nicht zuordenbare Einträge werden nach Sichtung aller Seiten noch
   einmal geprüft. Kann der Agent sie weder bestätigen noch sicher als fehlend
   belegen, bleiben sie als Unsicherheit offen – **nicht als bestanden**.
3. **Getrennte visuelle Prüfung:** Diese kontrolliert Wiedergabefehler wie
   abgeschnittene Grafiken und überlappende Beschriftungen. Sie soll ausdrücklich
   **keine** typografischen, sprachlichen oder fachlichen Verbesserungen vornehmen.

Die Aufgabenbeschreibung und die Quellen-Policies gelten in allen Schritten.
**Strikte Trennung der Modellkontexte:** Jedes Inventar, jeder Inhaltsabgleich
und jede visuelle Begutachtung wird als neuer Responses-Aufruf **ohne
`previous_response_id`** ausgeführt, mit separaten Reviewer-Instruktionen und
**ohne Shell-Tools**. Es werden ausschließlich die für diesen Check erforderlichen
Original- beziehungsweise Ausgabeseiten und der konkrete Auftrag mitgegeben.
Die visuelle Prüfung erhält die Originalseiten erneut (zuerst Originale, danach
Ausgabeseiten). Für eine globale Fehlstellenprüfung werden alle Ausgabeseiten
in einem neuen Aufruf vorgelegt. Frühere Review-Antworten gelten nicht als Beweis.

Reparaturen bleiben dagegen mit `previous_response_id` im **Erzeugungsverlauf**;
nach jeder Reparatur laufen die unabhängigen Prüfungen erneut. Das einmal vor
Beginn erstellte Quelleninventar bleibt dabei unverändert. Der Upload der
Originalseiten wird innerhalb eines Runs wiederverwendet. Dies kann trotz
Caching bei langen Scans erhebliche zusätzliche Bild-Tokenkosten verursachen.

Das Ergebnis `result/report.json` unterscheidet:

- `success`: keine bestätigten Fehler oder offenen Unsicherheiten; Include-Änderungen
  dürfen übernommen werden.
- `needs_review`: PDF wurde erstellt, aber mindestens eine Unsicherheit bleibt;
  **kein** uneingeschränkter Erfolg, Exitcode 1, **keine** Include-Übernahme.
- `failed`: Fehler, offene bestätigte Befunde oder nicht abgeschlossene Prüfung;
  Exitcode 1, keine Include-Übernahme.

Der Bericht enthält `source_inventory`, `content_findings`, `content_uncertainties`,
`review_findings`, `review_uncertainties` und eine `review_history` aller
Prüfdurchgänge. `usage_by_phase` weist Input-/Output-Tokens, Cache-Hits,
Reasoning-Tokens sowie Shell-Aufrufe/-Befehle getrennt je Phase aus.

**Kostenoptimierung ohne Qualitätsverlust:** Der Systemprompt fordert das
Zusammenfassen zusammengehöriger Shell-Aktionen und vermeidet leere
Statuskommandos. Es wird **kein neues verpflichtendes Token- oder Shell-Limit**
eingeführt. Bestehende konfigurierbare Job-Grenzen gelten weiterhin, darunter
`limits.max_agent_turns`. Da die unabhängige Inhaltsprüfung mehr Modellrunden
benötigt, ist für mehrseitige Reproduktionen eine ausreichend hohe Einstellung
(z. B. 24 statt 6 Runden) wichtig. Der zulässige Wertebereich wurde dafür
auf 1–100 erweitert. Die Bilderstellung und Prüfungen verursachen zusätzliche
API-Tokens, die sich nicht durch spätere Einsparungen garantiert ausgleichen.

Die Prüfung ist ein **best-effort Modellvergleich, kein formaler Beweis** einer
100-prozentigen Reproduktion. Besonders bei schlecht lesbaren Scans bleibt die
abschließende menschliche Kontrolle wichtig.

### Include-Roundtrip und Git

Der Container erstellt nach jedem erfolgreichen Compile/Repair mit
`runtime/collect-includes.sh` einen `include-snapshot.tar.gz`. Der Orchestrator
validiert den Inhalt und verwendet zunächst ausschließlich die Sandbox-Dateien.
Erst nach erfolgreicher No-go- und Reproduktionsprüfung werden Ergänzungen und
Änderungen in `job/include/` übertragen. Der Bericht listet sie unter
`include_changes`. Vorhandene Dateien dürfen nicht stillschweigend gelöscht werden;
Links und unsichere Archivpfade werden abgewiesen. Beim Schreiben werden
Git-Verschmutzung vor dem Start und zwischenzeitliche Änderungen erkannt.
Bestehende uncommittete Include-Dateien werden **nicht überschrieben**. Es gibt
weder automatische Git-Commits noch Pushes; danach selbst `git diff` und
`git status` prüfen. Bei fehlgeschlagenen Prüfungen bleibt `job/include/` unverändert.

`result/` enthält weiterhin auch bei gescheiterten Checks das letzte vollständige
Artefaktset zur Diagnose. Das heißt nicht, dass dieses Ergebnis abgenommen wurde.

Der Exitcode ist `0` bei vollständigem Erfolg, `1` bei einem ausgeführten, aber nicht
abgenommenen Job und `2` bei ungültiger Konfiguration.

## No-go-Checker

Version 0.3 führt weiterhin alle alle Python-Dateien im konfigurierten No-go-Verzeichnis aus. Ohne
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


### Dateigrenze des Hosted Containers

Das portable ConTeXt-Archiv wird als undurchsichtiges `.ctxbundle` hochgeladen und nicht als
erkennbares Archiv. Erkannte Archive werden beim Bereitstellen für den Container aufgefächert;
der vollständige ConTeXt-Baum enthält mehr als 6.000 Dateien. Der Runtime-Helper entfernt den
privaten Header, entpackt ConTeXt nur für genau einen Übersetzungslauf und löscht den temporären
Baum auch nach einem Compilerfehler wieder.
