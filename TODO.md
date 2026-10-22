# context-agent 0.9 – Stand und verbleibende Prüfungen

Stand: 14. Oktober 2026. Die früheren fünf Qualitätsregeln und die neue Ausführungsarchitektur sind auf Basis des Projekt-Uploads `context-agent20.zip` implementiert. **Die alte TODO-Liste mit falscher Empfehlung `\rm` wurde ersetzt.** Der aktuelle fachliche Standard verlangt vielmehr die High-Level-Befehle `\text` und `\mtext`.

## Implementiert

- [x] Verpflichtende explizite `quality`-Liste für jeden Auftrag, auch leer; keine Profile oder automatisch aktivierten Regeln.
- [x] Quality Rules mit Beschreibung, optionalen lesenden Checkern, optionalen deterministischen Refinements und LLM-Reparaturhinweisen.
- [x] Fünf Regeln: `dollar_math`, `semantic_numbers`, `semantic_math_text`, `number_with_unit`, `coordinate_reuse`.
- [x] Konservative Python-Kandidatenprüfung und dynamischer ConTeXt-Dollar-Linter.
- [x] `\dn`-Makro als technische Ressource der Zahlenregel; technische Mitbenutzung durch Einheitenregel.
- [x] LLM-Konsistenzprüfung inklusive Plan/Bündelung vor jeder Ergebnislöschung; Konflikte stoppen.
- [x] Requirements Validation gegen ursprünglichen Auftrag, auch bei nicht-reproduzierenden Jobs; für Reproduktionen zusätzlich bisheriges Quelleninventar und visueller Review.
- [x] Validierte SHA-256-Snapshots und Regression Gate für Requirements und andere Qualitätsregeln.
- [x] Guarded Autofix (eindeutiges manuelles Dezimalkomma), Backend zur geprüften Ausführung und ConTeXt-Neukompilierung, LLM-Reparatur für semantische Fälle.
- [x] Berichte mit `success`, `needs_review` und `failed`, offener Warnung und Reparaturjournal.
- [x] Alte `nogos/`-Verzeichnisse und `context_agent.nogos` entfernt; Tests migriert.

## Vor produktivem Schulbetrieb noch prüfen

- [ ] **Hosted-Smoke-Test mit echtem LMTX-Archiv und API-Zugang:** Alle fünf Regeln, mehrere hintereinander reparierte Befunde und Include-Übernahme end-to-end prüfen. Der lokale `context`-Befehl im Testcontainer enthält kein lauffähiges ConTeXt-Script.
- [ ] Spezifische ConTeXt-Typografie von `\unit{Degree}`, `\unit{Percent}`, `\unit{Celsius}` sowie `\dn` mit den schulischen Templates tatsächlich rendern und Abstände vergleichen.
- [ ] Schwierige, mehrdeutige Fälle in Mathematiktext, verschachtelten Makros, MetaPost-Beschriftungen und Python-Quelltextbeispielen anhand realer mehrseitiger Aufträge evaluieren. Die statischen Checker sind absichtlich noch kein vollwertiger TeX-Parser.
- [ ] Vollständigen End-to-End-Test des fern ausgeführten guardierten Python-Autofixes (inklusive managed-process-Brücke und Rollback bei Compile-Fehler).
- [ ] Später gegebenenfalls Kosten-/Risiko-Adaption und feinere Fortschrittsplanung ergänzen – erst nach echten Laufdaten.

Die händische Nachbearbeitung ist ausdrücklich Teil des Ziels; verbleibende semantische Unsicherheiten werden berichtet, nicht mit beliebig vielen LLM-Aufrufen versteckt.

## 0.9 (22. Oktober 2026)

- [x] Pflichtfeld `mode` und Migration der bestehenden Jobs auf `create`.
- [x] `improve` mit expliziter, unveränderlicher Ausgangsquelle, separatem
      Initialprompt, Baseline-Compile und geschütztem Snapshot.
- [x] Differenzvergleich und konservativer Zahlen-Guard in Regression Gate.
- [x] Verbesserungsmodus mit bestehenden Requirements-Unsicherheiten und Rollback.
- [x] Lokal lauffähiges ConTeXt LMTX aus mitgeliefertem Archiv, inkl.
      echter Kompilierung des Messtechnik-Blattes.
- [ ] Hosted-End-to-End-Test mit echter Responses API und Remote-LMTX-Runner
      (hier kein API-Zugang konfiguriert). Alle Offline-Fakes laufen lokal.
- [ ] Freigabemechanismus für beabsichtigte fachliche Zahlenänderungen bei
      späteren nicht nur typografischen `improve`-Aufträgen.
- [ ] Überprüfung des textbasierten Diffs bei sehr großen Quelltexten sowie
      Erfassung aller Makro- und Formelsemantiken im Review.
- [ ] Eventuelle vollständige TeX-Quellscanner-Erweiterung – gegenwärtig nur
      konservativ um Lua-Codeblöcke verbessert.
