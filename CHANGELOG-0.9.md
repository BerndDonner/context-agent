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
