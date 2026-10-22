# context-agent – Architektur 0.9 (Create / Improve + Quality Rules)

Stand: 22. Oktober 2026. Diese Datei beschreibt das **aktuelle** System. Die vorangegangene Designfassung ist als historische Referenz unter `docs/history/DESIGN_v0.7.md` archiviert und **nicht** mehr als Implementierungsvertrag gültig.

## Ziel

`context-agent` erstellt mit der OpenAI Responses API und einem flüchtigen ConTeXt-LMTX-Runner ein möglichst gutes, kompilierbares ConTeXt-Dokument, das der Benutzer bei Bedarf manuell weiterbearbeitet. Die inhaltlich verbindliche Referenz ist **immer der Originalauftrag** mit Template und Eingaben, nicht eine später entstandene Zwischenfassung.

## Konfiguration und Auswahl

Jeder Auftrag enthält zwingend eine explizite Liste `quality`, auch wenn sie leer ist:

```yaml
quality:
  - dollar_math
  - semantic_numbers
  - semantic_math_text
  - number_with_unit
  - coordinate_reuse
limits:
  max_quality_repairs: 3
```

Kein Profil, keine impliziten Regeln. Weder Dokumenttyp noch Inhaltsanalyse dürfen zusätzliche Regeln aktivieren. `quality: []` bedeutet, dass ausschließlich die technischen Pflichtprüfungen und die Requirements Validation stattfinden. Für eigene Regeln kann `quality_directory` ein Verzeichnis mit Unterordnern nach Regel-ID angeben. Unbekannte, doppelte oder ungültige Regel-IDs sind Fehler.

Die fünf eingebauten Regeln liegen jeweils unter `src/context_agent/resources/quality_rules/<id>/`. Eine Qualitätsregel setzt sich zusammen aus:

- `rule.yaml`: stabile ID; Beschreibung; Geltungsbereich; Ausnahmen; Generierungs-, Reparatur- und Verifikationshinweise; optionale technische Ressourcen.
- `checker.py` (optional): `check(QualityContext) -> list[QualityFinding]`, lesend. Meldungen können bestätigte Fehler, Kandidaten oder Warnungen sein.
- `refinement.py` (optional): `propose_edits(QualityContext, findings) -> list[Edit]`. Eine Regel darf stattdessen oder zusätzlich über ihren Reparaturtext LLM-gestützt arbeiten. Sie benötigt **keinen** deterministischen Fixer.
- `resources/` (optional): vom Refinement verantwortete Hilfsmakros und weitere Ressourcen.

**Checker und Refinement sind getrennte Rollen.** Eine Qualitätsregel verbindet beides und besitzt ein fachliches Ziel. Eine Regel darf mehrere Informationen liefern, eine Reparatur kann iterativ stattfinden und eine Regel kann ohne Codefix nur warnen. Python-Checker sind vertrauenswürdiger, lokal ausgeführter Code, keine isolierten Sicherheits-Sandboxes.

### Technische Ressourcen

Ausgewählte Regeln können in `rule.yaml` Ressourcen deklarieren. `semantic_numbers` und `number_with_unit` beziehen beispielsweise beide die Definition von `\dn` vom Regelverzeichnis `semantic_numbers`; die **Qualitätsregel** `semantic_numbers` wird bei Auswahl von `number_with_unit` dadurch nicht automatisch aktiviert. Der Bundler fügt Ressourcen dem Hosted-Job unter `job/include/quality-rules/` hinzu. Die Generierungsanweisung erklärt dem LLM die nötige einmalige Einbindung. Existierende Makrodefinitionen werden nicht überschrieben. Die Ressourcen kommen beim Kompilieren in den Include-Snapshot und werden bei erfolgreichem Ergebnis gemeinsam mit anderen Include-Dateien übernommen.

## Ablauf

1. **Preflight vor jeglicher Ergebnislöschung**: Job, Template, Originalauftrag, Quellen und ausschließlich die ausgewählten Regelbeschreibungen analysieren. Ein unabhängiger, werkzeugloser LLM-Aufruf liefert ein strukturiertes Konsistenzurteil sowie einen Ausführungsplan mit **genau** den ausgewählten IDs. Nachgewiesene und plausible relevante Konflikte blockieren die Ausführung mit Begründung; kleine Unsicherheiten werden dokumentiert. Ein blockierter Lauf verändert ein vorhandenes `result/` nicht.
2. **Generierung**: Der Generator erhält die tatsächlich ausgewählten Regeln als Anweisungen; nicht ausgewählte Regeln erscheinen nicht im Systemprompt. Quell- und Template-Policies bleiben verbindlich. Der Hosted-Runner erzeugt `main.tex`, `main.pdf`, `context.log` und `include-snapshot.tar.gz`.
3. **Requirements Validation**: Eine unabhängige Prüfung gegen den ursprünglichen Auftrag. Für Reproduktionen bleibt die ursprüngliche eigenständige Inhalts- und Sichtprüfung mit Quellinventar aktiv. Für sonstige Jobs werden der Originalauftrag, Template, relevante Texteingaben, ausgegebener TeX-Quelltext und gerenderte Ausgabeseiten geprüft. Das Ergebnis unterscheidet `passed`, `failed`, `uncertain`; offene Unklarheiten können nicht als Erfolg zählen.
4. **Validierter Snapshot**: Die zusammengehörigen vier Ergebnisartefakte werden mit SHA-256-Prüfsummen in `result/.validated/` abgelegt. Der Resume-Checkpoint `result/checkpoint.json` ist eine **andere** Funktion: Er speichert Ausführungszustand und Fingerprints, nicht den geprüften Satz an Artefakten.
5. **Quality Check**: Die ausgewählten Checker untersuchen `main.tex` und einen aus demselben Include-Snapshot rekonstruierten Include-Bestand. Dynamischer Dollar-Check: instrumentierter, tatsächlich ausgeführter ConTeXt-Lauf im Hosted-Container. Statische Python-Prüfungen melden konservative Kandidaten. Ein zusätzlicher unabhängiger, read-only LLM-Check kann Kandidaten verwerfen oder semantische Befunde ergänzen.
6. **Refinement Repair**: Das LLM hat im Preflight Reihenfolge und Bündelung der ausgewählten Regeln geplant. Eindeutige lokale Ersetzungen können als SHA-256- und Offset-gesicherte, nicht überlappende Edits angewendet werden. Die Hosted-Ausführung prüft vor Übernahme nochmals Hashes und Quelltext, kompiliert und aktualisiert den Include-Snapshot. Sonstige Reparaturen erfolgen via LLM-Prompt nach Batch, nicht durch ein starres globales Ersetzungsskript. Der Orchestrator kann die Strategie angesichts neuer Befunde anpassen.
7. **Regression Gate**: Die ursprünglichen Requirements werden **erneut** unabhängig geprüft. Anschließend werden die anderen ausgewählten Regeln auf Verschlechterungen geprüft. Erst dann wird die neue Fassung als validierter Snapshot gespeichert. Bei einem Fehler oder unzureichender Evidenz bleibt der bisherige validierte Snapshot erhalten und wird wiederhergestellt.
8. **Abschluss**: `success` nur bei erfüllten Requirements und ausgewählten Qualitätsregeln; `needs_review` bei offenen Qualitätswarnungen oder unsicherem Requirements-Nachweis; `failed` bei nicht reparierbaren nachgewiesenen Requirements- oder technischen Fehlern. Offene Befunde, Unsicherheiten, Versuche und Rollbacks stehen im JSON-Bericht. Include-Dateien werden erst bei `success` in den lokalen Job übernommen.

### Risiken und Grenzen

Die heuristischen Quellscanner sind **keine vollständigen TeX- oder MetaPost-Parser**. Fehlende Makroaufrufe können von ConTeXt selbst nicht generell als Verstöße nachgewiesen werden. Wiederholte MetaPost-Zahlenpaare sind keine Garantie für identische logische Punkte. Auch der LLM-Review ist ein risikobehaftetes, nicht formal beweisendes Qualitätsurteil. Ein kompilierbares PDF oder eine gleiche Seitenzahl genügt niemals als alleinige Requirements Validation.

Wenn die Reparatur die Quelldateien nicht effektiv ändert, eine andere Regel verschlechtert oder die Requirements verletzt, wird zum letzten Snapshot zurückgerollt. Ein offener Qualitätsverdacht beendet den Job gegebenenfalls mit `needs_review`, statt beliebig viele neue LLM-Aufrufe auszulösen. Transkript, Review-Historie und `quality_journal` liefern Informationen für die spätere Verbesserung zu strenger oder zu schwacher Regeln.

## Fünf implementierte Regeln

| ID | Prüfer | Refinement | Status |
|---|---|---|---|
| `dollar_math` | Dynamischer ConTeXt-Lint für ausgeführte Dollar-Mathematik | Kontextspezifische LLM-Reparatur mit `\m`, `\math`, `\startformula` | Vorhandenen dynamischen Linter integriert |
| `semantic_numbers` | Konservative Python-Kandidaten für Dezimalzahlen und Zahlgrößen ab 1000 | Guarded Autofix `1{,}5` → `\dn{1.5}`; sonst LLM; Makro `\dn` mitgeliefert | Implementiert, heuristisch |
| `semantic_math_text` | Kandidaten für Low-Level-Schriftumschaltung in mathematischem Kontext; LLM-Semantikprüfung | **`\text` und `\mtext` bevorzugen, nicht `\rm`**; LLM-Reparatur | Implementiert, heuristisch |
| `number_with_unit` | Kandidaten für manuelle Einheiten, Prozent, Grad und `\mathrm` | LLM konvertiert zu `\unit`, z. B. `30\unit{Degree}`, `\dn{12.5}\unit{Percent}` | Implementiert, heuristisch |
| `coordinate_reuse` | Wiederholte numerische Paare in MetaPost-Blöcken als **Warnkandidaten** | LLM entscheidet semantische Identität und benutzt ggf. definierte `pair`-Punkte | Implementiert, heuristisch |

`\dn{1234}` ist korrekt; es gibt **keine** zusätzliche Pflicht zur automatischen Dreiergruppierung. Für Jahreszahlen und Kennzeichnungen wird `\dn` nicht erzwungen. `\unit` und `\dn` bleiben fachlich getrennte Makros.

## Technische Grenzen der Prüfungen und Wirtschaftlichkeit

Alle Prüfschritte laufen mit konfigurierten Rundenbudgets. Die dynamischen ConTeXt-Läufe werden dort ausgeführt, wo sie beweiskräftig sind. Mehrere unabhängig meldende Checker teilen einen Quell-Snapshot; aufeinander aufbauende Reparaturen werden sequenziell validiert. Eine grundlegende Kostenoptimierung erfolgt durch Batch-Planung und einen begrenzten Reparaturzähler; eine statistisch adaptive Kostenstrategie ist ausdrücklich **nicht** Teil von 0.8.

### Dokumentationskonventionen

Die Datei `README.md` ist die Benutzerdokumentation; `TODO.md` nennt bewusst noch verbleibende Verifikationsaufgaben. Die historical Design-Datei dokumentiert ältere, inzwischen entfernte No-go-Strukturen und darf nicht als aktuelle API-Beschreibung interpretiert werden.

## Erweiterung 0.9: verbindliche Jobmodi und Protected Baseline

Jeder Job hat verpflichtend `mode: create|improve`. Keine Defaultauswahl.
Historische Jobs und Tests sind auf `mode: create` migriert. Der ursprüngliche
Create-/Reproduktionspfad wird nicht durch Improve ersetzt.

`mode: improve` benötigt `source.path` (geschützte `.tex` im Job), ein Template
und den Originalauftrag. `references` kann ein gescanntes PDF enthalten,
welches ausschließlich sekundäre Kontrollquelle ist. `review.reproduction`
ist dafür deaktiviert; es bleibt eine unabhängige Requirements Validation.

Der Bundler setzt `result/main.tex` anfangs bytegenau aus `source.path`.
Der erste LLM/Hosted-Schritt darf ausschließlich kompilieren und Includes
sichern. `.baseline/` ist ein gesonderter **kompilierbarer**, SHA-256-validierter
Snapshot, noch kein semantisch validiertes Ergebnis. `.protected/` sichert den letzten qualitätsgeprüften Zwischenstand, auch
bei verbleibender Unsicherheit. `.validated/` bleibt dem semantisch
überprüften Abschlussergebnis vorbehalten.
Dies ist bewusst keine Missdeutung von `resume`.

Die Requirementsprüfung bekommt Quelltext und Unified-Diff von Original zu
Ergebnis. Fehler/Unsicherheiten der Ausgangsfassung werden getrennt von neuen
Fehlern dokumentiert. Neue Befunde oder nachweislich geänderte Zahl-Literal-
Inventare werden zurückgesetzt. Die Ausgangsdatei und Referenzen werden
per Fingerprint gegen lokale Veränderungen geschützt. Im `changes.diff`
bleibt die Änderung nachprüfbar. Offene Altfälle bleiben `needs_review`.

**Grenzen:** Der numerische Inventarvergleich ist konservativ und verhindert
auch gewollte Wertänderungen. Eine umfassende semantische Erhaltung ist nicht
formal beweisbar; Format-, Index-, Vorzeichen- und Einheitentreue erfordern
weiterhin unabhängige Reviewer. Hosted-End-to-End braucht API-Zugang.
