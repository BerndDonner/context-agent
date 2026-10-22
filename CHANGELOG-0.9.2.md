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
