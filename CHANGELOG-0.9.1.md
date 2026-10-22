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
