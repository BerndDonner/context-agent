# Auftrag: Übungen Einführung Messtechnik – originalgetreue ConTeXt-Reproduktion

Erstelle aus `input/Übungen Einführung Messtechnik.pdf` ein eigenständiges,
kompilierbares ConTeXt-LMTX-Übungsblatt (`result/main.tex` und `result/main.pdf`).
Es handelt sich um einen **reinen Reproduktionsauftrag**, nicht um eine
redaktionelle, fachliche oder typografische Überarbeitung.

## 1. Verbindliche Inhaltsquelle

- Reproduziere **alle 11 Originalseiten inhaltlich vollständig**: alle
  **20 nummerierten Aufgaben (1–20)**, sämtliche zugehörigen Teilaufgaben,
  Originalabsätze, Abschnittsüberschriften, Zahlenwerte, Einheiten, Formeln,
  Tabellen, Beschriftungen, Abbildungen und Schaltungen.
- **Übernimm jede im Original bereits gedruckte Lösung und Ergebnisangabe
  vollständig.** Auch leere bzw. unvollständige Lösungsrubriken, sofern gedruckt,
  gehören zur Vorlage. Keine Lösungen weglassen, neu berechnen oder ergänzen.
- Wortlaut, Reihenfolge, Nummerierung und fachliche Aussagen so weit wie
  lesbar **unverändert** erhalten. Auch vermeintliche Tippfehler oder fachliche
  Fehler der Vorlage nicht stillschweigend korrigieren.
- Die Quelle ist ein **reiner Scan ohne Textebene**. Lies deshalb jede Seite
  visuell; `pdftotext` liefert keine verlässliche Aufgabenabschrift. Achte
  besonders auf kleine Indizes, Exponenten, Kommas, Prozentzeichen und
  Vorzeichen, sowie auf Größenwerte innerhalb der Diagramme.
- Wenn ein Detail nicht eindeutig entzifferbar ist, **nicht raten oder
  erfinden**. Die fragliche Stelle explizit als Unsicherheit erkennbar
  dokumentieren, damit die unabhängige Inhaltskontrolle `needs_review`
  auslösen kann. Eine unsichere Stelle ist keine bestätigte Reproduktion.

## 2. Dokumentkopf und Gestaltungsgrundlage

- Nutze die vollständige Präambel von `template/template.tex` als verbindliche
  Grundlage für **Schul-/Logo-Kopf, Seitenlayout, Fußzeile und die dort
  vorhandenen ConTeXt-Makros**.
- Der Kopf stammt aus `Arbeitsblatt1_SI_Genauigkeitsklasse.tex`; im
  bereitgestellten Template wurden lediglich zwei themenabhängige Beschriftungen
  auf `Übungsblatt` und `Einführung Messtechnik` umgestellt.
- Ersetze den Template-Platzhalter zwischen `\starttext` und `\stoptext`
  durch die Reproduktion der Messtechnik-PDF. **Keine** alten SI-Aufgaben,
  Erläuterungen oder Übungen aus der ursprünglichen Template-Datei übernehmen.
- Das Schul-Logo wird über `../Logo/sabel.png` geladen. `main.tex` liegt in
  `job/result/`; andere mitgelieferte Ressourcen liegen in `job/include/`.
- Beginne den Text mit einer schlichten, passenden Überschrift
  `Übungen – Einführung Messtechnik` im Stil der bestehenden Vorlage.
- Originale Seitenumbrüche, riesige Weißräume, die eingescannten Papierkanten,
  Lochungen und **ursprüngliche PDF-Seitenzahlen** müssen nicht nachgebildet
  werden. Inhalte und Abbildungsbeziehungen dagegen vollständig übernehmen.
- Keine zusätzliche fachliche Erklärung, Modernisierung, Umformulierung oder
  typografische Verschönerung. Die vorhandene Gestaltung der neuen Vorlage
  ist ausreichend.

## 3. Grafiken: vorhandene Hilfsfunktionen zuerst

- Erstelle Signal-, Spannungs- und Zeitdiagramme, Koordinatenachsen,
  Widerstands-/Messschaltungen usw. als **editierbare Vektorgrafiken** in
  ConTeXt/MetaPost (ggf. Lua), möglichst nicht als aus dem Scan ausgeschnittene
  Rasterbilder.
- Prüfe **vor dem Zeichnen** die dokumentierte API in
  `../include/plotmod-api.md` sowie `../include/plotmod.lua` und
  `../include/mymacros.mp`. Nutze bestehende öffentlich dokumentierte
  Plot-Funktionen, Beschriftungen und elektrische Symbole, soweit sie
  fachlich und geometrisch passen. Rohes MetaPost ist zulässig, wenn kein
  sinnvoller Helfer vorhanden ist.
- Definiere markante Punkte, Signalecken, Zeiten und gemeinsame
  Koordinaten **einmal**; alle Pfeile, Kurven, Beschriftungen und
  Periodengrenzen daraus ableiten. Nicht dieselben Koordinaten mehrfach
  hart codieren.
- Wenn sich beim Bearbeiten eine **sinnvolle, allgemein wiederverwendbare
  Abstraktion** ergibt, implementiere und teste sie **zuerst** in
  `../include/plotmod.lua` oder `../include/mymacros.mp` (bzw. einer
  neuen Datei in `../include/`), dokumentiere die öffentliche Verwendung
  in `../include/plotmod-api.md`, und verwende sie dann im Dokument.
  Bestehende Funktionen und Dateien nicht ohne Not ändern oder löschen.
  Keine zu speziell auf diese eine Abbildung zugeschnittene API erfinden.
- Falls eine weitere generische Abstraktion nur vorgeschlagen, aber nicht
  benötigt wird, notiere sie als Kommentar in `main.tex` unter der Kennung
  `% HELPER-IDEE:`; diese Kommentare dürfen im PDF nicht erscheinen.

## 4. Abnahme

- Das erzeugte PDF muss alle beauftragten Inhalte enthalten: besonders
  Aufgaben **1–20 mit sämtlichen Lösungen** sowie die Diagramme aus dem
  Original. Ein reiner PDF-Build beweist noch keine Vollständigkeit.
- Verwende gültige ConTeXt-Mathematik (`\m{...}` bzw.
  `\startformula`/`\stopformula`), keine LaTeX-Dollar-Mathe.
- Baue und teste mit der bereitgestellten ConTeXt-LMTX-Umgebung. Nutze die
  automatisch angestoßene unabhängige Inhaltsprüfung und die visuelle
  Reproduktionsprüfung und repariere nachgewiesene Abweichungen.
- Ziel ist eine möglichst vollständige und reproduzierbare Reproduktion,
  **kein neues Unterrichtsmaterial**. Keine eigenmächtigen Kürzungen.
- Bei unauflösbaren Scan-Unsicherheiten diese offenlassen und im Prüfbericht
  dokumentieren; kein uneingeschränkter `success`-Status für ungeprüfte Stellen.
- Erzeuge die regulären Ergebnisartefakte `main.tex`, `main.pdf`,
  `context.log`, `include-snapshot.tar.gz`. Git-Commits und Pushes
  sind nicht Aufgabe des Agenten.
