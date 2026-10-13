# ca-messtechnik – Vorbereitung und Start

Dieser Example-Job ist ein **Reproduktionsauftrag**, kein fertiges Übungsblatt.
Die eigentliche Umwandlung ist **nicht ausgeführt**.

## Materialien

- `input/Übungen Einführung Messtechnik.pdf`: unveränderter elfseitiger Scan,
  20 nummerierte Aufgaben, Diagramme, Schaltung und vorgedruckte Lösungen.
- `template/template.tex`: nur die Präambel/Kopfstruktur von
  `Arbeitsblatt1_SI_Genauigkeitsklasse.tex` und ein leerer Dokumentkörper.
  Zwei offensichtlich alte, themenabhängige **Kopf-Beschriftungen** wurden
  von `1. Arbeitsblatt` und `SI-Einheiten und Genauigkeit` auf
  `Übungsblatt` und `Einführung Messtechnik` gesetzt.
- `Logo/sabel.png`: Logo aus dem übergebenen `Logo/`-Verzeichnis,
  relativ zu `result/main.tex` über `../Logo/sabel.png` erreichbar.
- `include/`: originale Hilfsdateien übernommen. Nur in `mymacros.mp` wurden
  überflüssige Leerzeichen an Zeilenenden und Leerzeilen am Dateiende
  entfernt (ohne fachliche oder funktionale Änderung).

Die Metadaten `Schuljahr 2026/27`, `Klasse M1A`, `B. Donner` und
`Arbeitszeit: ca. 90 min` stammen unverändert aus dem übergebenen Kopf.
Insbesondere die Arbeitszeit ist **nicht fachlich validiert** – bei Bedarf
vor dem Run im Template ändern.

## Start

Vom Repository-Root aus:

```bash
context-agent validate examples/ca-messtechnik
context-agent run examples/ca-messtechnik
```

Der `runtime.context_archive` entspricht dem bereits im CTC-Example
verwendeten lokalen Pfad. Ggf. anpassen, falls das Archiv verschoben wurde.
`processing.mode` ist bewusst `standard`: Der letzte Flex-Test wurde
mit HTTP 429 `flex_unavailable` abgewiesen. Das ist keine generelle
Aussage zur Verfügbarkeit von Flex.

Der Job ist wegen elf vollständig gescannter Seiten teuer und kann trotz
`max_agent_turns: 80` und `timeout_seconds: 3600` scheitern oder
`needs_review` melden. Vorher ein funktionierendes API-Budget sicherstellen.

## Ergebnisse und Sicherheit

- `result/` wird bei jedem Run geleert; vergangene Artefakte vorher sichern.
- Nach uneingeschränktem `success` übernimmt der Agent mögliche Änderungen
  aus der Sandbox **direkt in dieses lokale `include/`**; keine automatischen
  Commits. `git diff` vor dem Commit prüfen.
- Bei `failed` oder `needs_review` werden Include-Änderungen nicht
  übernommen; die Ergebnisartefakte bleiben zur Kontrolle liegen.
- Der Original-PDF-Scan bleibt als Eingabedatei unverändert.
- Dies ist eine **inhaltlich und visuell modellabhängige** Prüfung, kein
  formaler Nachweis einer perfekten Reproduktion.
