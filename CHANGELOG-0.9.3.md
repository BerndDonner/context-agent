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
