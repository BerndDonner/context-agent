# context-agent 0.1 — Design, Architektur und Übergabe

**Status:** Implementierter Stand von Version 0.1  
**Zweck:** Dieses Dokument ist die maßgebliche Übergabeunterlage für `context-agent/`. Wird es
in einer späteren Unterhaltung zusammen mit dem Quellcode bereitgestellt, sollen Ziele,
Randbedingungen, Architektur und bewusste Nicht-Ziele ohne den ursprünglichen Gesprächsverlauf
verständlich sein.

Bei Widersprüchen zwischen diesem Dokument und dem Quellcode gilt für das tatsächliche Verhalten
der Quellcode; die Abweichung soll anschließend in diesem Dokument korrigiert werden.

---

## 1. Motivation

Der Anwender erstellt als Lehrkraft regelmäßig ConTeXt-Dokumente, insbesondere:

- Schulaufgaben und Prüfungen,
- Arbeitsblätter,
- Musterlösungen zu bereits vorhandenen Angaben,
- neu gesetzte ConTeXt-Fassungen von als PDF erhaltenen Angaben,
- Dokumente mit Mathematik, MetaPost/MetaFun, Lua, QR-Codes und eigenen Makros.

Eine reine LLM-Textantwort ist dafür unzureichend: Sie kann plausibel aussehenden ConTeXt-Code
liefern, der nicht kompiliert, LaTeX-Gewohnheiten übernimmt oder lokale Konventionen verletzt.
Der entscheidende Mehrwert des Projekts ist deshalb die **geschlossene Werkzeugschleife**:

```text
Auftrag + Template + Quellen
            ↓
Modell arbeitet in einer Linux-Sandbox
            ↓
ConTeXt wirklich ausführen
            ↓
Fehler lesen und selbst reparieren
            ↓
lokale No-go-Prüfer
            ↓
Befunde an denselben Agenten zurückgeben
            ↓
kompilierte Quelle + PDF + Bericht
```

Das Projekt ist zugleich ein überschaubarer Praxistest für einen agentischen Workflow. Es ist
kein allgemeines Agenten-Framework.

---

## 2. Ziel und Größenordnung

`context-agent` ist ein kleines Python-CLI-Programm, das einen modellgesteuerten Agenten für die
Erstellung kompilierter ConTeXt-LMTX-Dokumente orchestriert.

Die ursprünglich genannte Zielgröße von ungefähr 1000 LOC bezeichnet eine Größenordnung, keine
harte Grenze. Der implementierte Python-Anwendungscode liegt bei ungefähr 1360 Zeilen; mit Tests
liegt das Projekt bei ungefähr 1770 Python-Zeilen. Das ist für Version 0.1 akzeptiert. Ein erster
Stand mit etwa 10 000 LOC wäre dagegen zu groß und zu infrastrukturlastig gewesen.

Leitprinzipien:

1. Der gesamte Ablauf soll für eine Person nachvollziehbar bleiben.
2. Deterministische Randaufgaben übernimmt Python; inhaltliche und reparierende Entscheidungen
   trifft das Modell.
3. Es wird nur implementiert, was für den ersten realen Test benötigt wird.
4. Neue Regeln entstehen aus beobachteten Fehlern, nicht aus hypothetischen Anforderungen.

---

## 3. Zentrale Architekturentscheidung

### 3.1 Modellgesteuerter Agent

Version 0.1 verwendet die agentischere Variante:

> Das Modell arbeitet innerhalb einer frischen Hosted-Shell-Sandbox selbstständig. Es liest die
> Dateien, richtet ConTeXt ein, erzeugt `main.tex`, kompiliert, untersucht Fehler und repariert
> das Dokument eigenständig.

Python schreibt nicht jeden ConTeXt-Aufruf als starre interne Pipeline vor.

### 3.2 Aufgabe des Python-Orchestrators

Der lokale Python-Code:

- lädt und validiert das Jobverzeichnis,
- erstellt ein Jobarchiv,
- lädt Jobarchiv, ConTeXt-Archiv und direkte PDF-/Bildquellen hoch,
- erzeugt einen neuen OpenAI-Container,
- startet und begrenzt die Modellrunden,
- lädt Ergebnisartefakte herunter,
- führt alle vorhandenen lokalen No-go-Checker aus,
- sendet konkrete No-go-Befunde an denselben Modellkontext zurück,
- bewahrt den letzten vollständigen kompilierbaren lokalen Stand,
- schreibt Bericht und Transkript,
- löscht Container und Uploads standardmäßig wieder.

### 3.3 Aufgabe des Agenten

Der Agent in der Sandbox:

- entpackt das Jobarchiv,
- bootstrapped das portable ConTeXt-LMTX,
- führt einen echten Smoke-Test aus,
- liest Aufgabe, Template, Eingaben, Includes und Referenzen,
- erzeugt das Ergebnis im festgelegten Verzeichnis,
- führt ConTeXt beliebig oft innerhalb seiner Modellrunde aus,
- behebt Compiler-, Lua-, MetaPost-, Include- und Pfadfehler,
- liefert `main.tex`, `main.pdf` und `context.log`,
- behebt spätere No-go-Befunde, ohne geschützte Inhalte zu verändern.

---

## 4. Bewusste Nicht-Ziele von Version 0.1

Nicht implementiert sind:

- automatische visuelle Bewertung des erzeugten PDFs,
- automatisches Rendern der Ausgabeseiten zur Layoutkritik,
- ästhetische Optimierungsschleifen,
- Multi-Agent-System,
- Langzeitgedächtnis,
- Vektordatenbank oder eigene RAG-Infrastruktur,
- semantische Dokumentauswahl,
- persistente Wiederverwendung eines Containers,
- Weboberfläche,
- Jobs aus nur einer Markdown-Datei und CLI-Optionen,
- eigene Template-Sprache mit Platzhaltern,
- per Job aktivierbare oder deaktivierbare No-go-Regeln,
- Prozessisolation für die lokalen No-go-Skripte,
- pixelgenauer Vergleich mit Referenz-PDFs.

Die visuelle Endkontrolle übernimmt der Anwender. Beobachtete wiederkehrende Fehler können später
als No-go-Checker formalisiert werden.

---

## 5. Jobverzeichnis als verbindlicher Vertrag

Ein Job ist immer ein Verzeichnis:

```text
job/
├── job.yaml
├── task.md
├── template/
│   └── template.tex
├── input/
│   ├── angabe.pdf
│   ├── wortlaut.md
│   └── hinweise.md
├── include/
│   ├── sabel.png
│   ├── MAB.jpg
│   ├── mymacros.mp
│   ├── plotmod.lua
│   └── qrencode.lua
├── references/
│   ├── mathincontext-paper.pdf
│   ├── luametafun.pdf
│   └── plotmod-api.md
├── nogos/                 # optional, joblokale Checker
└── result/
```

### 5.1 `include/`

Bilder und Codepakete liegen absichtlich gemeinsam in `include/`. Eine Trennung in `assets/`
und `include/` wurde für den MVP verworfen.

Das Verzeichnis darf unter anderem enthalten:

- Logos und Abbildungen,
- ConTeXt-Dateien,
- MetaPost-Makros,
- Lua-Module,
- Fonts oder Hilfsdateien,
- eigene öffentliche Pakete.

Da `main.tex` in `job/result/` liegt, sollen relative Verweise normalerweise
`../include/dateiname` verwenden.

### 5.2 `references/`

Alle konfigurierten Referenzen werden bei jedem Job in die Sandbox übertragen. PDF- und
Bilddateien werden zusätzlich direkt an die erste Modellanfrage angehängt, damit das Modell sie
multimodal lesen kann. Textdateien sind im Jobarchiv vorhanden.

Es gibt noch keine Indexierung. Das Modell entscheidet selbst, welche Referenzen es benötigt.

### 5.3 `result/`

Vor einem Lauf wird der Ergebnisordner geleert. Ein erfolgreicher Lauf enthält mindestens:

```text
result/
├── main.tex
├── main.pdf
├── context.log
├── report.json
└── transcript.jsonl
```

---

## 6. Exaktes `job.yaml`-Schema

Beispiel:

```yaml
model: YOUR_MODEL_ID

task: task.md

template:
  path: template/template.tex

inputs:
  - path: input/angabe.pdf
    role: statement
    policy: immutable

  - path: input/loesungshinweise.md
    role: content
    policy: guidance

references:
  - references/mathincontext-paper.pdf
  - references/luametafun.pdf
  - references/plotmod-api.md

runtime:
  context_archive: /absoluter/pfad/context-lmtx-ready.tar.xz
  memory_limit: 4g
  keep_remote: false

limits:
  max_agent_turns: 6
  max_nogo_repairs: 3
  timeout_seconds: 900
  max_output_tokens: 12000

# optional; relativ zum Job oder absolut
# nogo_directory: nogos
```

### 6.1 Felder

`model`  
API-Modell-ID. Kein Modellname ist im Programm hart codiert. Das gewählte Modell muss die im
Backend verwendeten Responses-/Shell-Werkzeuge unterstützen.

`task`  
Pfad zur eigentlichen Arbeitsanweisung, relativ zum Job. Standard: `task.md`.

`template.path`  
Pfad zum vollständigen ConTeXt-Template, relativ zum Job.

`inputs`  
Liste auftragsspezifischer Dateien mit Rolle und Policy.

`references`  
Liste allgemeiner Referenzdateien, relativ zum Job.

`runtime.context_archive`  
Pfad zum portablen ConTeXt-LMTX-Archiv. Relative Pfade werden relativ zum Job aufgelöst; absolute
Pfade sind erlaubt.

`runtime.memory_limit`  
Container-Speicher: `1g`, `4g`, `16g` oder `64g`.

`runtime.keep_remote`  
Bei `true` bleiben Container und Uploads zu Debugzwecken erhalten. Standardmäßig werden sie
bestmöglich gelöscht.

`limits.max_agent_turns`  
Gesamte Zahl äußerer Modellaufrufe einschließlich Erstlauf, Artefakt- und No-go-Reparaturen.

`limits.max_nogo_repairs`  
Maximale Zahl gezielter No-go-Reparaturrunden. Die Gesamtgrenze der Modellrunden gilt zusätzlich.

`limits.timeout_seconds`  
HTTP-/API-Timeout pro SDK-Aufruf. Wertebereich 60 bis 3600 Sekunden.

`limits.max_output_tokens`  
Maximale Textausgabe pro Modellrunde. Shell-Arbeit findet innerhalb derselben Response statt.

`nogo_directory`  
Optionaler expliziter Pfad zum Checker-Verzeichnis.

Unbekannte YAML-Felder sind Fehler. Dies verhindert unbemerkte Tippfehler.

---

## 7. Rollen und Inhalts-Policies

Rolle und Policy sind voneinander unabhängig:

- Die Rolle beschreibt den Zweck einer Datei.
- Die Policy beschreibt den erlaubten Änderungsgrad.

### 7.1 Rollen

`statement`  
Verbindliche Angabe, beispielsweise als fachliche Quelle einer Musterlösung. Sie muss nicht
vollständig im Ergebnis wiederholt werden.

`recreate`  
Eine vorhandene Datei, typischerweise PDF, soll als bearbeitbares ConTeXt-Dokument im
Schul-Template neu gesetzt werden.

`content`  
Inhalt, der unmittelbar in das neue Dokument einfließen soll.

`reference`  
Zusätzliche fachliche oder gestalterische Quelle ohne zwingende Übernahme.

### 7.2 Policies

`verbatim`  
Der Wortlaut darf nicht verändert werden. Nur typografisch notwendige Umsetzung ist erlaubt.

`immutable`  
Fachliche Aussagen, Zahlen, Bedingungen und Randdaten dürfen nicht verändert werden. Der Text
muss nicht zwingend wortgleich wiederholt werden.

`editable`  
Redaktionelle Bearbeitung, Strukturierung und sinnvolle Ergänzung sind erlaubt.

`guidance`  
Die Datei ist eine vage Vorgabe oder Ideensammlung; freie sinnvolle Ausarbeitung ist erlaubt.

### 7.3 Gemischte Vorgaben

Es gibt keine Inline-Syntax für geschützte und freie Textbereiche. Solche Bereiche werden in
getrennte Dateien gelegt und getrennt konfiguriert. Dadurch bleibt der Vertrag einfach und
maschinenlesbar.

---

## 8. Verbindliches vollständiges Template

### 8.1 Template-Form

Das Template ist ein vollständiges, grundsätzlich kompilierbares ConTeXt-Dokument. Es wird nicht
in eine Environment-Datei umgebaut.

Das reale Ausgangsmuster enthält typischerweise:

- Layout- und Schriftdefinitionen,
- Schul- und Fachangaben,
- Logos,
- eigene Makros,
- einen vorhandenen Inhalt,
- hinter dem ersten `\stoptext` eventuell einen Ideenpool oder alte Varianten.

### 8.2 Effektive Dokumentgrenzen

Die Verarbeitung folgt diesem Modell:

1. Der Bereich vor dem ersten **wirksamen** `\starttext` ist die Template-Präambel.
2. Der Bereich bis zum ersten danach folgenden wirksamen `\stoptext` ist der ersetzbare Inhalt.
3. Alles nach diesem ersten `\stoptext` wird für das neue Dokument ignoriert.

Kommentare sowie typische Code-/Verbatim-Bereiche werden bei der Erkennung maskiert, damit dort
vorkommende Zeichenfolgen nicht als Dokumentgrenzen gelten.

Die Zielstruktur lautet:

```tex
% übernommene und gegebenenfalls gezielt angepasste Präambel
\starttext

% neuer Inhalt

\stoptext
```

### 8.3 Veränderbarkeit der Präambel

Die Präambel ist gestalterisch verbindlich, aber nicht byteweise unveränderlich. Der Agent darf
auftragsspezifische Werte ändern, etwa:

- Klasse und Semester,
- Fach,
- Datum,
- Dokumenttitel,
- Punkte und Arbeitszeit,
- technisch notwendige relative Dateipfade.

Er darf nicht:

- den Dokumentkopf durch ein eigenes Layout ersetzen,
- Template-Makros ohne Not umgehen,
- ein anderes schulisches Erscheinungsbild erfinden.

### 8.4 Prioritäten

Bei Konflikten gilt:

1. explizit wörtlich geschützte Nutzervorgaben,
2. verbindliches Template,
3. dokumentierte öffentliche API eigener Pakete,
4. konkrete Jobanweisung,
5. offizielle aktuelle ConTeXt-Dokumentation,
6. allgemeines Modellwissen.

---

## 9. Sandbox- und API-Lebenszyklus

### 9.1 Lokale Vorbereitung

Python erstellt ein temporäres `context-agent-job.tar.gz` mit:

```text
job/                   # Job ohne result/
runtime/               # Bootstrap-Skript
agent-manifest.json     # normalisierte Pfade, Rollen und Policies
```

Zusätzlich werden separat hochgeladen:

- das portable ConTeXt-Archiv,
- alle konfigurierten PDF-Dateien,
- alle konfigurierten Bilder.

### 9.2 Hosted Container

Für jeden Job wird ein neuer Container erzeugt. Er erhält alle Upload-IDs und die konfigurierte
Speichergrenze. Die Dateien erscheinen unter `/mnt/data`.

Die Modellanfrage verwendet das Shell-Werkzeug mit einer Referenz auf genau diesen Container.
Folgerunden verwenden `previous_response_id`, sodass derselbe Agentenkontext und derselbe
Container fortgesetzt werden.

### 9.3 ConTeXt-Bootstrap

`bootstrap-context.sh`:

1. findet oder erhält das `.tar.xz`-Archiv,
2. entpackt es nach `/mnt/data/context-lmtx`,
3. erzeugt kleine `context`- und `mtxrun`-Wrapper um `luametatex --luaonly`,
4. erzeugt den ConTeXt-Dateicache,
5. kompiliert ein minimales reales Dokument,
6. schlägt fehl, wenn kein Smoke-Test-PDF entsteht.

Der Bootstrap wurde lokal mit dem bereitgestellten Archiv getestet. Der Agent soll für spätere
Shell-Aufrufe den absoluten Wrapper `/mnt/data/context-lmtx/bin/context` verwenden oder die
erzeugte `env.sh` einlesen.

### 9.4 Ergebnisposition

Im Container sind verbindlich:

```text
/mnt/data/work/job/result/main.tex
/mnt/data/work/job/result/main.pdf
/mnt/data/work/job/result/context.log
```

Der Agent kompiliert aus `job/result/`. `context.log` soll die relevante Ausgabe des letzten
ConTeXt-Laufs enthalten.

### 9.5 Aufräumen

Standardmäßig werden nach dem Lauf Container und hochgeladene Dateien bestmöglich gelöscht.
Bei `keep_remote: true` wird dies für Debugging unterlassen.

---

## 10. Agentische Ablaufsteuerung

Vereinfachter Ablauf des Python-Codes:

```python
job = validate_job()
container = create_hosted_session(job)
turn = agent_initial_turn()
artifacts = download_result()

while artifacts_missing and turns_available:
    turn = agent_repair_missing_artifacts(previous=turn)
    artifacts = download_result()

if artifacts_complete:
    checkers = load_all_nogo_checkers()
    findings = run_checkers()

    while findings and repair_budget_available:
        turn = agent_repair_nogos(findings, previous=turn)
        artifacts = download_result()
        findings = run_checkers_again()

write_report_and_transcript()
cleanup_remote()
```

Der Agent darf innerhalb eines Modellaufrufs das Shell-Werkzeug mehrfach benutzen. Die in YAML
angegebene Zahl `max_agent_turns` begrenzt die äußeren Responses-Aufrufe, nicht die Zahl einzelner
Shell-Kommandos.

---

## 11. Ergebnisabnahme

Automatisch verlangt werden ausschließlich:

1. `main.tex` ist vorhanden,
2. `main.pdf` ist vorhanden und beginnt mit der PDF-Signatur `%PDF-`,
3. `context.log` ist vorhanden,
4. alle No-go-Checker laufen ohne internen Fehler,
5. alle No-go-Checker liefern keine Befunde mehr.

Es findet **keine automatische visuelle Abnahme** statt.

### 11.1 Letzten kompilierbaren Stand bewahren

Remote-Artefakte werden zunächst in ein lokales Staging-Verzeichnis geladen. Ein neuer Satz
überschreibt den bisherigen vollständigen lokalen Satz nur dann, wenn er selbst vollständig ist.

Damit bleibt nach einer misslungenen No-go-Reparatur das letzte kompilierbare lokale Dokument
verfügbar. Solange noch keine vollständige Fassung existiert, werden vorhandene Teilartefakte
übernommen, damit eine Artefakt-Reparaturrunde darauf aufbauen kann.

---

## 12. No-go-System

### 12.1 Zweck

No-go-Regeln werden nicht vorab erfunden. Das Verzeichnis ist in Version 0.1 absichtlich leer.
Wenn ein erzeugtes Dokument ein wiederkehrendes, objektivierbares Problem zeigt, schreibt der
Anwender einen Python-Checker. Der Checker wird ab dann bei allen Jobs ausgeführt.

Die Regeln sind ausdrücklich nicht auf reguläre Ausdrücke oder Schlüsselwörter beschränkt. Ein
Checker darf komplexer Python-Code sein.

### 12.2 Suche nach Checkern

Ohne explizite Konfiguration sucht das Programm unter anderem:

1. `job/nogos/`,
2. `./nogos/` des aktuellen Projekts,
3. `nogos/` in Elternverzeichnissen,
4. das mitgelieferte projektweite `nogos/`.

Momentan werden immer alle nicht privaten `*.py`-Dateien ausgeführt. Dateien, deren Name mit
`_` beginnt, werden ignoriert. Ein `__init__.py` wird daher nicht als Checker geladen.

### 12.3 Plugin-Vertrag

Jeder Checker exportiert:

```python
from context_agent.models import NogoFinding
from context_agent.nogos import NogoContext


def check(context: NogoContext) -> list[NogoFinding]:
    ...
```

Beispiel:

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
            message="Der manuelle Seitenumbruch ist in diesem Dokument unerwünscht.",
            file="main.tex",
            repair_hint="Verwende die vorhandenen Template-Mechanismen.",
        )
    ]
```

`NogoFinding` enthält:

- `rule_id` — stabile Kennung,
- `message` — verständliche Problembeschreibung,
- optional `file`,
- optional `line`,
- optional `repair_hint`.

### 12.4 `NogoContext`

Der Kontext stellt bereit:

- den aufgelösten Job,
- `main_tex`,
- optional `main_pdf`,
- optional `context_log`,
- `result_dir`,
- `template_path`,
- `include_dir`,
- kontrollierte `read_text`- und `read_bytes`-Hilfen für Jobdateien.

Checker sind vertrauenswürdiger lokaler Python-Code. Sie sind nicht sandboxed und können bei
Bedarf selbst weitere Bibliotheken oder lokale Programme verwenden. Hilfsmodule im selben
Checker-Verzeichnis können importiert werden.

### 12.5 Checkerfehler

Ein Import- oder Laufzeitfehler eines Checkers ist kein bestandener Check. Er wird mit Traceback
in `report.json` festgehalten und führt zum Status `failed`. Solche internen Checkerfehler werden
nicht an das Modell zur Dokumentreparatur gesendet, da sie zunächst im Checker-Code behoben
werden müssen.

### 12.6 Automatische Reparatur

Konkrete Findings werden in eine strukturierte deutschsprachige Reparaturanweisung umgewandelt
und mit `previous_response_id` an denselben Agenten geschickt. Anschließend werden Artefakte neu
geladen und **alle** Checker erneut ausgeführt.

---

## 13. Berichte und Status

### 13.1 `report.json`

Der Bericht enthält unter anderem:

- `status`: `running`, `success` oder `failed`,
- Modell-ID,
- Start- und Endzeit,
- Zahl der Modellrunden,
- Zahl der No-go-Reparaturen,
- Response-IDs,
- Kompilier-/Artefaktstatus,
- verbleibende Findings,
- Checkerfehler und Tracebacks,
- sonstige Fehler,
- summierte Token-Nutzung, soweit von der API geliefert,
- Container-ID,
- lokale Artefaktpfade.

### 13.2 `transcript.jsonl`

Pro Modellrunde wird ein JSON-Objekt geschrieben mit:

- Rundennummer,
- Phase (`initial`, `repair-artifacts`, `repair-nogos-N`),
- Response-ID und Status,
- sichtbarer Modellantwort,
- Nutzungsdaten,
- vollständigem serialisierbarem Response-Dump.

Das Transkript dient vor allem der Fehlersuche und der Auswertung des agentischen Experiments.

### 13.3 Exitcodes

- `0`: Job vollständig erfolgreich,
- `1`: Job wurde ausgeführt, aber nicht abgenommen,
- `2`: Konfiguration oder Aufruf ist ungültig.

Unerwartete Programmierfehler werden nach dem Schreiben eines Fehlerberichts erneut ausgelöst,
damit sie beim Entwickeln sichtbar bleiben.

---

## 14. Quellcodeaufbau

```text
context-agent/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── nogos/
│   └── __init__.py
├── examples/
│   └── minimal-job/
├── src/context_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── errors.py
│   ├── models.py
│   ├── job.py
│   ├── template.py
│   ├── bundling.py
│   ├── prompts.py
│   ├── openai_backend.py
│   ├── nogos.py
│   ├── report.py
│   ├── workflow.py
│   └── resources/
│       ├── prompts/
│       └── runtime/
└── tests/
```

### 14.1 Modulzuständigkeiten

`models.py`  
Pydantic-Konfigurationen und interne Dataclasses.

`job.py`  
YAML laden, Pfade sicher auflösen, Job validieren, Ergebnisverzeichnis vorbereiten.

`template.py`  
Wirksame erste `starttext`-/`stoptext`-Grenze bestimmen und Dokumente zusammensetzen.

`bundling.py`  
Jobarchiv und Agentenmanifest erzeugen; direkte multimodale Dateien bestimmen.

`prompts.py`  
Promptressourcen laden und initiale beziehungsweise technische Reparaturprompts rendern.

`openai_backend.py`  
Uploads, Container, Responses-Shell-Sitzung, Folgerunden, Artefaktdownload und Cleanup.

`nogos.py`  
Checker laden, ausführen und Findings als Modellprompt darstellen.

`report.py`  
Atomaren JSON-Bericht und JSONL-Transkript schreiben.

`workflow.py`  
Gesamten äußeren Ablauf und die Budgets orchestrieren.

`cli.py`  
Kommandos `validate` und `run` sowie Exitcodes.

---

## 15. Abhängigkeiten und Werkzeugwahl

Laufzeit:

- Python 3.13,
- `openai` 2.x,
- Pydantic 2.x,
- PyYAML 6.x.

Entwicklung:

- pytest,
- Ruff,
- mypy im Strict-Modus.

CLI-Parsing verwendet bewusst die Standardbibliothek `argparse`. Für den kleinen MVP ist kein
zusätzliches CLI-Framework erforderlich.

Der OpenAI-Import erfolgt erst beim Erzeugen einer echten Hosted Session. Dadurch können
Validierung, No-go-System und lokale Tests ohne API-Paket oder API-Schlüssel ausgeführt werden.

---

## 16. Tests und nachgewiesener Stand

Der implementierte Stand besitzt lokale Tests für:

- Template-Grenzerkennung,
- Job- und Pfadvalidierung,
- Bundle und Manifest,
- dynamische No-go-Checker,
- Reparatur fehlender Artefakte mit Fake-Agent,
- automatische No-go-Reparatur mit Fake-Agent.

Erfolgreich ausgeführt wurden:

```text
pytest:       10 Tests bestanden
ruff check:  keine Befunde
mypy:        keine Befunde im Strict-Modus
```

Zusätzlich wurde `bootstrap-context.sh` mit dem bereitgestellten
`context-lmtx-ready.tar.xz` real ausgeführt. Cache-Erzeugung und Kompilierung des Smoke-Test-PDFs
waren erfolgreich.

Nicht durchgeführt wurde ein kostenpflichtiger Live-Lauf gegen die OpenAI API, weil in der
Entwicklungsumgebung kein API-Schlüssel verwendet wurde. Der API-Pfad orientiert sich an der
aktuellen Responses-, Hosted-Shell-, Container- und Container-Files-Schnittstelle des offiziellen
Python-SDKs.

---

## 17. Sicherheits- und Vertrauensmodell

- Jobpfade für Aufgabe, Template, Inputs und Referenzen dürfen das Jobverzeichnis nicht verlassen.
- Das ConTeXt-Archiv und ein explizites No-go-Verzeichnis dürfen bewusst externe Pfade sein.
- Symlinks werden beim Job-Bundling nicht übernommen.
- Der Agent wird angewiesen, eingebettete Texte als Daten und nicht als höherrangige Anweisungen
  zu behandeln.
- Der remote Container ist pro Job frisch und wird standardmäßig gelöscht.
- No-go-Checker sind **vertrauenswürdiger lokaler Code** und nicht isoliert.
- API-Schlüssel werden nicht in YAML oder Projektdateien gespeichert; das offizielle SDK liest die
  normale Umgebungsvariable.

Version 0.1 versucht nicht, bösartige eigene Templates oder bösartige eigene No-go-Skripte zu
sandboxen. Der Workflow ist für vom Anwender kontrollierte Jobs ausgelegt.

---

## 18. Bekannte Grenzen und wahrscheinliche nächste Schritte

Erst nach realen Läufen sollen Erweiterungen entschieden werden. Naheliegende, aber noch nicht
beauftragte Schritte sind:

1. erste echte No-go-Checker aus beobachteten Fehlmustern,
2. Auswahl von Checkern nach Dokumenttyp, sobald genügend Checker existieren,
3. Wiederverwendung eines vorbereiteten Containers zur Kosten- und Zeitersparnis,
4. lokale oder API-seitige Dokumentensuche bei zu vielen Referenzen,
5. optionale visuelle Ausgabeprüfung,
6. detailliertere PDF-Validierung,
7. Aufbewahrung benannter Zwischenstände bei schwierigen Reparaturen.

Diese Punkte sind keine Zusagen für Version 0.1.

---

## 19. Übergabe in eine spätere Unterhaltung

Für eine sofortige Fortsetzung sollten mindestens bereitgestellt werden:

1. dieses `DESIGN.md`,
2. der aktuelle Projektordner oder das Projektarchiv,
3. ein konkretes Jobverzeichnis,
4. das portable ConTeXt-Archiv,
5. bei einem Laufproblem `result/report.json` und `result/transcript.jsonl`.

Die wichtigsten unveränderlichen Entscheidungen lauten:

- Modellgesteuerter Agent in der Sandbox, nicht starre Python-Kompilierungspipeline.
- Vollständiges ConTeXt-Dokument als verbindliches Template.
- Präambel vor erstem wirksamen `\starttext`; trailing Material nach erstem wirksamen
  `\stoptext` ignorieren.
- `include/` enthält Bilder und Code gemeinsam.
- Eingaben besitzen getrennte Rollen und Änderungs-Policies.
- Alle Referenzen werden zunächst bei jedem Job übertragen.
- Keine automatische visuelle Endkontrolle in Version 0.1.
- No-go-Regeln sind beliebig komplexe lokale Python-Skripte, zunächst leer und momentan immer
  vollständig aktiv.
- No-go-Befunde werden automatisch durch denselben Agenten zu reparieren versucht.
- Der letzte vollständige kompilierbare lokale Stand wird bewahrt.
