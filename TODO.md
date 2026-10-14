# TODO – Requirements & Refinements für `context-agent`

Stand: 2026-10-14. **Architektur und Aufgaben sammeln; noch nichts davon implementieren.**

Aktueller Bestand: **5 ConTeXt-Qualitätsregeln** (bisher „No-gos“), davon **1 implementiert** und **4 offen**. Die bestehende Implementierung verwendet weiterhin Namen wie `nogos/` und `NogoFinding`; die Umbenennung zu *Refinements* ist ein geplanter Umbau, kein bereits erfolgter Schritt.

## Leitbild: Erst den Auftrag erfüllen, dann das Dokument verfeinern

- **Requirements (primäre Anforderungen):** Alles, was aus dem konkreten Auftrag hervorgeht: vollständiger und korrekter Inhalt, verlangte Darstellungen, Zahlen/Formeln, fachliche Semantik, Struktur sowie textuelle und visuelle Vorgaben. Diese Anforderungen haben **immer Vorrang**.
- **Refinements (Qualitätsstandards):** Darüber hinaus geltende Konventionen für ein gutes, wartbares ConTeXt-Dokument, z. B. `\digits`, `\unit`, mathematische Schriftumschaltung und wiederverwendbare MetaPost-Punkte. Sie betreffen nicht nur verbotene Syntax, sondern auch Stil, Struktur und Wartbarkeit. „No-go“ ist dafür als Oberbegriff zu eng.
- Die Erfüllung der Requirements ist **keine einmalige Eingangskontrolle**, sondern bleibt eine Invariante über sämtliche Refinement-Schritte hinweg. Ein besserer ConTeXt-Stil rechtfertigt niemals falsche Inhalte oder verletzte Layoutvorgaben.
- Ein erfolgreicher ConTeXt-Build bzw. eine unveränderte Zahl von Seiten ist **kein** Beleg dafür, dass der ursprüngliche Auftrag noch erfüllt ist.
- Prüfungen können insbesondere bei visuellen oder semantischen Requirements unsicher sein. **„Nicht als Fehler erkannt“ ist nicht dasselbe wie „nachgewiesen erfüllt“.** Unklarheiten sichtbar ausweisen und nicht stillschweigend als bestanden behandeln.

### Zielworkflow

1. **Generation:** Eine erste ConTeXt-Fassung nach den ursprünglichen Vorgaben erstellen.
2. **Requirements Validation:** Inhalt, Vollständigkeit, Fachlichkeit und visuelle Vorgaben prüfen; Probleme mit dem Auftrag zunächst dort reparieren.
3. **Validierter Checkpoint:** Nach erfolgreicher Prüfung die zusammengehörigen Quellen, Includes, Assets, PDF und Prüfresultate als konsistenten Ausgangszustand festhalten.
4. **Refinement Check:** Alle für den Job aktiven Qualitätsregeln prüfen, Befunde erfassen und priorisieren.
5. **Refinement Repair:** Sichere Autofixes transaktional anwenden; mehrdeutige oder semantische Änderungen bei Bedarf gebündelt vom LLM bearbeiten lassen.
6. **Regression Gate:** Neu kompilieren und kontrollieren, dass die ursprünglichen Requirements **weiterhin erfüllt** sind und keine anderen verbindlichen Refinements verschlechtert wurden. Bei bestätigter Regression Änderungen verwerfen bzw. aus dem Checkpoint wiederherstellen.
7. **Commit/Checkpoint:** Nur eine erfolgreich überprüfte Verbesserung zur neuen gültigen Fassung erklären; anschließend verbleibende Befunde prüfen. Der Endzustand benötigt **erneut eine vollständige Requirements Validation**, auch wenn zwischendurch risikobasierte Teilprüfungen aus Kostengründen genügen.
8. **Abschluss:** Primäre Anforderungen, offene Refinement-Befunde, nicht überprüfbare Punkte und abgelehnte Änderungen **getrennt** dokumentieren. Bei ausgeschöpftem Budget lieber die beste überprüfte Fassung erhalten als eine ungesicherte „schönere“ ausliefern.

```text
Generation → Requirements Validation → validierter Checkpoint
                                           │
                                           ▼
                                   Refinement Check
                                           │
                                           ▼
                             Autofix / gezielte LLM-Reparatur
                                           │
                                           ▼
                                  Regression Gate
                                    │          │
                               bestanden   Regression/unklar
                                    │          │
                                übernehmen   zurückrollen / prüfen
                                    │
                                    └──→ weitere Refinements
                                           │
                                           ▼
                               finale Requirements Validation
```

## Offene Refinements (4)

- [ ] **MetaPost: definierte Punkte wiederverwenden** (`coordinate-reuse`)
  - Wichtige Punkte und Knoten einmal benennen und bei späteren Verwendungen auf diese Namen Bezug nehmen; abhängige Positionen daraus ableiten.
  - Vermeiden, dass bereits definierte *logisch identische* Punkte erneut als Zahlenkoordinaten ausgeschrieben werden.
  - Keine pauschale Verbotsregel für numerische Koordinaten: unabhängig voneinander definierte Punkte dürfen identische Werte besitzen.
  - Prüfen, inwieweit eine verlässliche automatische Erkennung möglich ist; falsch-positive Befunde vermeiden.
  - Gegenwärtig als Generierungsanweisung in `resources/prompts/system.md`, noch kein eigener Checker. Voraussichtlich zunächst semantische Prüfung ohne generischen Autofix.

- [ ] **Deutsche Dezimalzahlen mit `\digits` setzen** (`german-decimal-digits`)
  - In deutschsprachigem gesetztem Text keine handgebauten Dezimalkommas wie `5{,}35`, sondern die passende ConTeXt-Notation mit `\digits` verwenden.
  - Vor Implementierung die genaue Eingabesyntax und Ausnahmen festlegen (z. B. mathematische Formeln, Codebeispiele, wörtliche Zitate).
  - Positive und negative Testfälle aufnehmen; nur tatsächlich gesetzten Text beanstanden.
  - Autofix-Kandidat bei eindeutig lokalisierten Literalen; Wechselwirkung mit `number-with-unit` beachten.

- [ ] **Text in Formeln über `\rm`, nicht `\text{...}`** (`math-roman-text`)
  - Für Textbestandteile in mathematischen Ausdrücken die gewünschte ConTeXt-Schreibweise benutzen, z. B. `f_{\rm max}` statt `f_{\text{max}}`.
  - Prüfung auf mathematischen Kontext beschränken; `\text` außerhalb von Formeln nicht pauschal verbieten.
  - Inline- und Display-Formeln sowie Mathematik in MetaPost-Beschriftungen berücksichtigen.
  - Testfälle für gültige Formeln, falsche Schreibweisen und nicht ausgeführten Quelltext vorsehen.
  - Nur bei eindeutig gleicher Bedeutung automatisiert korrigieren, sonst als Befund melden.

- [ ] **Zahlen mit Einheiten über `\unit` setzen** (`number-with-unit`)
  - Zahlen mit physikalischen Einheiten nicht aus einzelnen Zahlen, Leerzeichen und Einheitenzeichen zusammensetzen, sondern mit dem passenden ConTeXt-Mechanismus `\unit` setzen.
  - Vor Implementierung exakte ConTeXt-LMTX-Syntax und Zusammenspiel mit `\digits` prüfen; noch keinen pauschalen Ersatztext festlegen.
  - Geltungsbereich klären: Fließtext, Formeln, MetaPost-/TeX-Beschriftungen, Tabellen und Achsenbeschriftungen; Codebeispiele und wörtliche Quellen ausnehmen.
  - Zwischen echten Messgrößen und ähnlichen Zeichenfolgen ohne Einheit unterscheiden (z. B. Prozentangaben, Abkürzungen, Variablennamen).
  - Sichere Fälle von mehrdeutigen Fällen unterscheiden; automatische Reparatur nur bei semantisch eindeutiger Zuordnung von Zahl und Einheit.

## Architekturaufgaben

### A. Begriffe und Plugin-Struktur

- [ ] **`nogo` → `refinement` umbenennen:** Bestehende `resources/nogos/`, Python-Typen, Berichte und Dokumentation konsistent umstellen, wenn die neue Schnittstelle feststeht. Nicht vorzeitig Code nur kosmetisch verschieben.
- [ ] Regeln als eigenständige Module unter `src/context_agent/resources/refinements/` organisieren (geplantes Verzeichnis); `dollar_math.py` als existierenden Ausgangspunkt berücksichtigen.
- [ ] Anforderungen und Refinements in getrennten Verantwortungsbereichen führen; gemeinsame Infrastruktur für Befunde, Prüfläufe, Snapshots und Berichte wiederverwenden. Eine vorgeschlagene Verzeichnisstruktur ist **noch kein verbindliches API-Design**.
- [ ] Kurze Generierungsanweisungen beibehalten, damit Fehler möglichst gar nicht entstehen; längerfristig pro Refinement die Autorenanweisung und den Checker aus einer gemeinsamen Regeldefinition beziehen, statt `system.md` und Plugins unabhängig zu pflegen.
- [ ] Neue Regeln ohne zusätzliche Fallunterscheidungen im zentralen Workflow registrieren und aktivieren können.

### B. Regelmodell für viele Refinements

- [ ] Stabile Regel-ID, Version, Beschreibung, Beispiele, Geltungsbereich (Text, Mathematik, MetaPost, Tabellen usw.), Kostenklasse, Nachweisbarkeit und Abhängigkeiten definieren.
- [ ] **Verbindlichkeit trennen:** z. B. `required` (verbindliche Konvention), `recommended` (Qualitätspräferenz), optional `optional`. Schweregrad eines einzelnen Befunds separat modellieren. Nicht jedes Refinement ist automatisch ein harter Abbruchgrund.
- [ ] Regeln job- oder profilbezogen auswählbar machen (z. B. Sprache/Schulmaterial/technische Dokumentation); standardmäßig sinnvolle Vorgaben nutzen.
- [ ] Prüfergebnisse strukturiert erfassen: Regel, Fundstelle, Beleg, Erklärung, Reparaturhinweis, Sicherheit des Befunds und optional vorgeschlagene Korrektur.
- [ ] Statische günstige Checks zuerst; ConTeXt-dynamische Prüfungen möglichst bündeln, an Quell-/Artefaktzustände binden und nur bei relevanten Änderungen erneut ausführen.
- [ ] Kein unsicherer Regex-Treffer als verbindlicher Beweis: TeX-/MetaPost-Kontexte, Makros, nicht ausgeführte Definitionen und geschützte Quellbereiche berücksichtigen.

### C. Check und Repair strikt trennen

- [ ] `check(context) -> findings` konzeptionell **read-only** halten.
- [ ] Optionale Schnittstelle `propose_fixes(context, findings) -> edits` vorsehen; eine Regel darf **keinen** beliebigen, unkontrollierten Quelltext direkt verändern.
- [ ] Ein Edit beschreibt Datei, exakte Fundstelle, erwarteten Originaltext bzw. Hash, Ersatztext, Regel-ID, Begründung und Unsicherheit/Autofix-Freigabe.
- [ ] Nur eindeutige, semantikbewahrende Änderungen automatisch zulassen. Überlappende Edits, veraltete Ausgangsfassung oder nicht auflösbare Abhängigkeiten zentral erkennen und nicht stillschweigend überschreiben.
- [ ] Die vier offenen Regeln hinsichtlich Autofix-Eignung einzeln prüfen; `coordinate-reuse` vorerst nicht durch numerische Textersetzung „lösen“.
- [ ] Bewusstsein für die Sicherheitsgrenze: Aktuelle Plugins sind ausführbarer, vertrauenswürdiger Python-Code und nicht sandbox-isoliert.

### D. Transaktionen, Regression und Checkpoints

- [ ] Quellen **inklusive** Includes, generierten Assets und zugehörigen PDFs in einem konsistenten Snapshot behandeln; unveränderliche Eingaben, Vorlagen und externe Originale nicht modifizieren.
- [ ] Konfliktfreie Autofixes bündeln und auf einer temporären Arbeitsfassung anwenden; Reihenfolge und Wechselwirkungen explizit behandeln, z. B. `\digits` mit `\unit`.
- [ ] Nach Änderungen ConTeXt neu ausführen und die betroffenen Refinements erneut prüfen; festhalten, ob der Befund tatsächlich verschwunden ist.
- [ ] **Requirement-Regressionen prüfen:** Inhalt/Anzahl/Nummerierung, Werte, mathematische Bedeutung, Grafiken sowie Layout- und Bildvorgaben gegen den ursprünglichen Auftrag bzw. die validierte Baseline abgleichen. Reine Kompilierbarkeit reicht ausdrücklich nicht.
- [ ] Gezielte **risikobasierte Zwischenprüfungen** festlegen (etwa lokale Tests bei Textedits, erneutes Rendern/visuelles Review bei Layout- oder MetaPost-Änderungen), ohne für jeden einzelnen Autofix teure vollständige Reviews zu erzwingen. **Vor Freigabe zwingend vollständige Requirements Validation.**
- [ ] Unterscheiden zwischen `passed`, `failed` und `uncertain`/`not_verified`; eine unklare Prüfung nicht als Erfolg zählen. Bei Regression oder fehlender ausreichender Evidenz Änderungen zurückstellen, zurückrollen oder zur manuellen Prüfung markieren.
- [ ] Letzten überprüften Checkpoint erhalten; auch bei fehlgeschlagenen Reparaturen und Budget-Ende wiederherstellbar und reproduzierbar machen.
- [ ] Änderungsjournal führen: Diff, betroffene Regeln, neue/behobene Befunde, durchgeführte Requirements-Prüfungen, Ergebnis und gegebenenfalls Rollback-Grund.

### E. Reparatursteuerung und Wirtschaftlichkeit

- [ ] Reihenfolge: sichere lokale Autofixes → Re-Check → verbleibende mehrdeutige Befunde **gebündelt** an das LLM → Regression Gate → nächste Runde nur bei nachgewiesenem Fortschritt.
- [ ] Keine automatische Endlosschleife: maximale Zyklen, LLM-Aufrufe und Gesamtlaufzeit begrenzen; Oszillation („Regel A repariert, Regel B wieder kaputt“) erkennen.
- [ ] Vorgaben priorisieren: **Requirements vor verbindlichen Refinements vor Empfehlungen**. Innerhalb einer Stufe Nutzen, Risiko und Kosten abwägen.
- [ ] Gemeinsame Prüfinfrastruktur nutzen, um nicht für jeden Befund einen separaten Modell- oder Hosted-Shell-Aufruf zu benötigen. Caching/Batching dürfen keine veralteten Ergebnisse als gültig ausgeben.
- [ ] LLM-Reparaturen möglichst auf betroffene Quellbereiche eingrenzen und den ursprünglichen Auftrag, die unveränderlichen Inhalte und zuletzt validierten Zustand ausdrücklich als Grenzen vorgeben.

### F. Tests und Abnahmekriterien

- [ ] Pro Regel Positiv-, Negativ-, Grenzfall- und Kontexttests (Fließtext, Mathematik, MetaPost, unverarbeitete Definitionen, wörtlicher Text).
- [ ] Autofix-Tests: Idempotenz, Erhaltung der Bedeutung, Erkennen von Edits auf veralteter Basis, Konflikte und mehrere Regeln an derselben Stelle.
- [ ] Regressionstests: erfolgreicher Build bei **inhaltlichem Fehler** muss abgelehnt werden; falsche Zahl, fehlende Aufgabe oder verschobene Schaltungsbeschriftung erkennen; bei Unsicherheit keinen unverdienten `passed`-Status vergeben.
- [ ] Transaktions- und Wiederaufnahmetests: Kompilierfehler, Review-Regressionsbefund, LLM-Fehler, Rollback, Wiederaufnahme nach Unterbrechung, Budget-Ende.
- [ ] Reihenfolge und Kosten der Prüfschritte an kleinen Beispielen und einem echten mehrseitigen Auftrag kontrollieren; zuerst lokal/offline testen, kostenpflichtige Hosted-API-Tests nur bei begründetem Bedarf.

## Bereits umgesetzt (zur Einordnung, unverändert)

- [x] **Dollar-Mathematik** (`context-dollar-math`): dynamische ConTeXt-Prüfung für ausgeführte `$...$`/`$$...$$` und MetaPost-Beschriftungen (`resources/nogos/dollar_math.py`). Die derzeitige Korrektur läuft über das LLM, nicht über einen deterministischen Autofix.
- [x] **Hosted-Prozessverwaltung** (Version 0.7.0): generischer Supervisor für ConTeXt-Build und Linter, mit echtem Hosted-Shell-Smoke-Test für Start/Wait/Exit-Code und zwei bzw. null Dollar-Mathematik-Befunde. Das ist eine Infrastrukturgrundlage, aber **noch keine** Refinement-Autofix- oder Requirements-Regression-Gate-Implementierung.
