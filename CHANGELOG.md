# Changelog – context-agent

Änderungen in umgekehrter Versionsreihenfolge. Die historischen Abschnitte
sind inhaltlich unverändert übernommen; sie dokumentieren jeweils den damaligen Stand.

## 0.9.6 – Kontextbezogener Zahlen-/Einheitenschutz (22.10.2026)

- Numerische und physikalische Angaben in tatsächlichen Änderungen positionsbezogen
  statt über globale ungeordnete Häufigkeitszählungen prüfen.
- TeX-Schreibweisen und Einheitenaliase normalisieren, einschließlich `\m{\mu}V`,
  `\mathrm{k}\Omega`, `\unit{microvolt}`, Vorzeichen und direkt angeschlossener Einheiten.
  Unbekannte Ausdrücke bleiben konservativ geschützt; keine stillschweigenden
  Größenumrechnungen oder fachlichen Wertänderungen.
- Mehrdeutige Zahlenschreibweisen bleiben gesperrt, solange keine im `job.yaml`
  ausdrücklich genehmigte Auflösung mit Originalreferenz, PDF-Seite und Quellzeile
  vorliegt. Eine solche Freigabe ersetzt keine unabhängige Requirements-Prüfung.
- Zurückgewiesene Kandidaten vor dem Rollback unter `result/rejected/` sichern,
  mit Diff, Artefakten, Prüfsummen und dem Status `REJECTED_NOT_VALIDATED`.
- Das unabhängige `improve`-Requirements-Audit erhält das vollständige
  Änderungs-Diff und kompakte verifizierte Evidenz anstelle wiederholt
  übermittelter kompletter Original- und Ergebnisquellen. Der `create`-Pfad
  und die unabhängige Seitensichtprüfung bleiben unverändert.
- Offline-Regressionstest mit den 89 Ersetzungen des realen Hosted-Laufs
  vom 22.10.2026, einschließlich absichtlich falscher Werte/Einheiten.
- Bisherige `CHANGELOG-*.md` in dieser Datei zusammengeführt.


---

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

---

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

---

# 0.9.3 – Präflight-Plan robust und diagnostizierbar

- Ein ungültiger oder unvollständiger **Modell-Plan** wird ausschließlich hinsichtlich
  seiner Reihenfolge/Batches durch Einzelregel-Batches in der expliziten YAML-Reihenfolge
  ersetzt. Es werden keine Regeln ergänzt oder ausgelassen.
- Ein `blocked`-Urteil, nachgewiesene blockierende Konflikte sowie ungültige
  Status-/Konfliktangaben werden weiterhin **nicht** durch einen Fallback umgangen.
- Der Präflight schreibt schon **vor** jeder Änderung an `result/` dauerhaft
  `.context-agent/preflight-events.jsonl` (einschließlich Response-ID, Antwortstatus,
  Bytezahl/SHA-256 der Antwort, Plan-Struktur, Fallback-Grund und Fehlerklasse).
- Modellantworten, Prompts, Datei-Inhalte und Credentials werden nicht protokolliert.
- Echte Hosted-API-Tests erfordern weiterhin einen API-Schlüssel.

---

# 0.9.2 – Qualitäts-Payload und Diagnoseprotokoll

## Direkter Upload statt Base64-Shell-Argument

- Die vollständige Edit-Liste wird als kompakte JSON-Datei über
  `containers.files.create(container_id, file=...)` direkt in den **bereits
  laufenden Hosted-Container** hochgeladen. Es gibt keine Modell-Übertragung
  des JSON- oder Base64-Inhalts mehr.
- Das API-Upload-Ergebnis wird auf gültigen Containerpfad und erwartete Bytezahl
  geprüft. Das lokale SHA-256 der Datei wird als kurzer Shell-Parameter
  übergeben. Der Container prüft den Hash, bevor er eine Änderung vornimmt.
- Optimistic-Locking gegen den ursprünglichen SHA-256 von `main.tex`, alte
  Quellfragmente und überlappende Bereiche bleiben zwingend.
- Die vorhandene at-most-once-Prozesssteuerung bleibt für Apply, Compile
  und Include-Snapshot erhalten.

## Fehlerdiagnose

- Neue `result/execution-events.jsonl`: append-only mit `fsync`, damit auch bei
  abgebrochenen Remote-Aufrufen Zustandsübergänge erhalten bleiben.
- Protokolliert API-Status, Response-/Request-ID, `incomplete_details.reason`,
  Laufzeit, Tokenzahlen soweit verfügbar, Shell-Call-/Output-Status,
  Prozess-ID, Start-/Polling-/Retry-Versuche, Endzustände, Fehlerklassen,
  Upload-Größe und SHA-256, sowie Qualitäts-Schritte und Rollback-Ereignisse.
- Bewusst **nicht** protokolliert: Shell-Befehle, Edit-Inhalte, Prompts,
  stdout/stderr, Environment-Variablen, API-Schlüssel und Exception-Meldungen.
  Für die detaillierte Modellausgabe bleibt `transcript.jsonl` separat.
- Eine ungeklärte START-Bestätigung wird weiterhin konservativ mit Rollback
  behandelt; das Log unterscheidet erstmals gescheiterte API-Calls,
  unvollständige Responses, fehlende Shell-Calls und fehlende Prozessmarker.

## Tests und Grenzen

- Regressionstests mit großen Edit-Payloads, manipulierten Upload-Antworten,
  SHA-256-Fehlern, stale edits und Secret-Redaction.
- Ein echter OpenAI-Hosted-End-to-End-Test erfordert einen API-Schlüssel;
  mit Offline-Fakes kann keine erfolgreiche Live-Ausführung garantiert werden.

---

# 0.9.1 – Hosted-Improve-Robustheit (A/B/C)

## A: Hosted-Shell-Response

- Laufende Response mit derselben ID begrenzt nachfragen statt sofortigem Abbruch.
- Unvollständige oder nicht quittierte Shell-Aufrufe nach demselben Prozess-ID-Token wiederholen.
- Supervisor `start` ist idempotent nur bei identischen argv/cwd; anderer Auftrag ist Fehler.
- Read-only Polling kann transportbedingt wiederholt werden; beim unbekannten START-Ergebnis gibt es eine Statussondierung.

## B: Requirements-Delta für Improve

- Keine mehrfachen Requirements-Rezensionen der unveränderten Baseline.
- LLM benennt neue Regressionen samt zwei überprüfbaren Original-/Zieltextbelegen.
- Programmatisch belegte Änderungen derselben Diff-Region können ein Rollback auslösen.
- Nicht belegte Beanstandungen bleiben offen (`needs_review`) statt ungeprüft akzeptiert/rollback.
- Vorhandene Quellunsicherheiten bleiben sichtbar und erhalten ihren Abschlussstatus.

## C: Original-PDF beim unabhängigen Review

- Original-PDFs und Referenzbilder werden bei Improve-Review-Aufrufen explizit mitgeschickt.
- Reviewer bleibt stateless und erhält keinen Generator-/Shell-Zugriff.

## Tests und Einschränkungen

- Neue Offline-Tests für idempotenten Start, nicht abgeschlossene Responses, Quellenbelege und PDF-Anhänge.
- Archivierte Beispiel-PDFs werden auf gültige Unicode-Pfade korrigiert.
- Echter Hosted-Responses-API-Abnahmelauf noch ausstehend.

---

# context-agent 0.9 – Überarbeitungsmodus

Stand: 22.10.2026

## Änderungen

- `mode` ist für alle Jobs Pflicht: `create` oder `improve`, ohne Default.
- Alle vier vorhandenen Beispieljobs verwenden jetzt ausdrücklich `mode: create`.
- Neuer Modus `improve` mit `source.path` (separat von Template und Referenzen).
- Der Bundler liefert die Originalquelle unverändert als `job/result/main.tex`.
- Neuer Compile-only-Initialprompt; eine Abweichung von der Quelle im ersten Lauf ist ein Fehler.
- Eigener, Hash-geprüfter `.baseline`-Snapshot; `.protected` hält einen geprüften,
  auch bei verbleibenden Unsicherheiten rücksetzbaren Zwischenstand; `.validated`
  wird erst bei erfolgreicher vollständiger Validierung geschrieben.
- Diff `result/changes.diff` und Vergleich des Zahlenliteral-Inventars vor
  und nach Reparaturen. Veränderung geschützter Werte führt zum Rollback.
- Bestehende Scanmarker bleiben als offene Befunde erhalten und erlauben
  trotzdem ausgewählte Formatrefinements; `needs_review` bleibt möglich.
- Lua-Codebereiche werden vom konservativen Zahlenchecker ausgeklammert.
- Der Einheitenchecker erkennt weitere Schreibweisen (u. a. kΩ und mV).
- Neuer vollständig angelegter Job `examples/ca-messtechnik-improve/` mit
  unveränderlicher ConTeXt-Quelle und Scan-PDF nur als Referenz.
- `scripts/local-lmtx.sh` bietet einen reproduzierbaren lokalen Testlauf
  mit dem separat gelieferten LMTX-Archiv.

## Hier ausgeführte Prüfungen

- Lokales LMTX aus `context-lmtx-ready.tar.xz` entpackt, Linux-x86-64 lauffähig.
- Minimaler Compile-Test: erfolgreich, PDF erzeugt.
- Originales `main(4).tex` mit Messtechnik-Includes und Logo: erfolgreich kompiliert.
- Test `\dn{1.25}\unit{Volt}`, `\unit{Percent}`, `\unit{Degree}`: erfolgreich.
- Dynamischer Dollar-Checker: sieben echte LMTX-Fälle + Fake-Test bestanden.
- `test_improve.py`, `test_workflow.py`, `test_job.py`, `test_bundling.py`,
  `test_quality_rules.py`, `test_resume_and_progress.py`: vollständig bestanden.
- `test_content_audit.py`, `test_openai_backend.py`, `test_reproduction.py`,
  `test_template.py`, `test_context_math.py`: vollständig bestanden.
- `test_include_sync.py`, `test_runtime_script.py`: vollständig bestanden.
- Der monolithische Testlauf hat eine auffällige Laufzeit im bestehenden
  `test_managed_process.py` gezeigt; die übrigen Tests wurden deshalb
  separat ausgeführt. Keine Aussage über uneingeschränkten Gesamttest.

## Nicht durchgeführt / bekannte Grenzen

- Kein echter OpenAI-Responses-Hosted-End-to-End-Aufruf: kein entsprechend
  konfigurierter API-Schlüssel in dieser Testumgebung verwendet.
- Keine automatische LLM-Überarbeitung des ganzen Messtechnik-Dokuments;
  getestet wurden das Ausgangsdokument, das überarbeitende Agentenschema,
  Offline-Reparaturabläufe und die echten LMTX-Makros.
- Der Zahlenliteral-Guard ist konservativ und kein vollständiger
  TeX-Semantik-Beweis. Beabsichtigte fachliche Wertänderungen sind im aktuellen
  `improve`-Modus noch nicht freigeschaltet.
