# Auftrag: Kurzarbeit VZ2 – eine Aufgabe mit vier Teilaufgaben

Erstelle ein eigenständiges, kompilierbares ConTeXt-Dokument (`result/main.tex` und
`result/main.pdf`) für eine **Kurzarbeit im Wahlpflichtfach Mathematik FHR**.

## Vertrauenswürdige Quellen

Nur die Verzeichnisse `input/` und `include/` gelten als brauchbare Ausgangsbasis.
Andere im ursprünglichen Paket enthaltene Job-Dateien galten als fehlerhaft und wurden
für diesen bereinigten Testjob bereits ersetzt.

## 1. Layout und formale Grundlage

- Verwende `template/template.tex` als verbindliche Grundlage.
- Das Layout soll in **Gestaltung, Kopfstruktur, Typografie und allgemeiner Anmutung**
  dem Dokument `input/Kurzarbeit1_VZ2_2526.tex` entsprechen.
- **Wichtig:** Im Template steht bereits ein vollständiger Deckblatt-Bereich zwischen
  `\starttext` und `\page[yes]`. Bewahre dessen **sichtbare Gestaltung und Struktur**:
  insbesondere Logo, Titel, Schrifthierarchie, Tabellen, Name/Datum/Klasse und den
  Seitenumbruch. Die eingebettete Font-Weiche ist verbindlich: bevorzugt echtes
  Calibri, sonst Carlito, sonst IBM Plex Sans. Alle drei Varianten sind zulässig;
  Carlito ist ausdrücklich KEIN Requirements-Verstoß. Die 11-pt-Normalschrift
  und der fette 14-pt-Titel sowie ihre visuelle Funktion bleiben erhalten. Füge die vier neuen Teilaufgaben nur im Inhaltsbereich **hinter**
  `\page[yes]` ein. Baue das Deckblatt nicht unnötig neu.
- **Font-Policy und Reproduzierbarkeit:** Die in `template/template.tex`
  vorhandene `\startluacode`-Weiche soll nach Möglichkeit übernommen werden.
  Bei fehlender Calibri-Installation ist Carlito ausdrücklich als
  metrisch kompatibler Ersatz zulässig; die dritte Stufe IBM Plex Sans ist
  ebenfalls erlaubt. Die Laufzeit muss eine tatsächlich verfügbare Schrift
  auswählen (inklusive Fettvariante). Fehlt die Schrift trotz vorhandener
  Weiche, ist das ein Ressourcenproblem und kein Verbot des Carlito-Fallbacks.
- **Quellcode ist nicht unveränderlich:** Die ausgewählten Qualitätsregeln dürfen
  semantisch gleichwertige Anpassungen der ConTeXt-Implementierung im **gesamten**
  Dokument vornehmen – ausdrücklich auch auf dem Deckblatt, in Tabellen, in der
  Präambel und in Fußzeilen. Beispielsweise wird `30min` als
  `30\unit{Minute}` gesetzt. Maßstab sind Inhalt und sichtbares Layout,
  nicht der exakte Quelltext der Vorlage. Originalquellen in `input/` bleiben
  selbstverständlich unverändert.
- Abweichungen gegenüber der alten Kurzarbeit sind bewusst: **16 BE statt 21 BE**
  und ein freies Datumsfeld statt `11.11.2025`. Die Bearbeitungszeit bleibt 30 Minuten.
- Erzeuge **keine Musterlösung**, sondern nur die Aufgabenstellung.
- Beginne den Aufgabenteil mit genau diesem Hinweis aus der Layoutvorlage:
  „Hinweis: Achten Sie auf eine übersichtliche und schöne äußere Form,
  korrekte mathematische Schreibweise und geben Sie bei Textaufgaben kurze
  Antworten an.“
- Kein MetaPost, keine zusätzlichen Abbildungen, keine unnötigen Helferdateien.

## 2. Inhaltliche Grundlage

- Nutze als fachliche Vorlage die Aufgabe aus
  `input/Schulaufgabe001_4FA_2324.tex`, in der die Funktion
  `x^4 - 3x^2` untersucht wird.
- Übernimm den **didaktischen Stil und die vier Teilaufgaben** dieser Vorlage,
  aber passe sie fachlich korrekt an die neue Funktion an.
- Verwende als neue Funktion verbindlich:

\startformula
f(x) = \frac{1}{8} (x^4 - 17x^2 + 16)
\stopformula

- Verwende für die Schnittpunktaufgabe weiterhin:

\startformula
g(x) = 2x^2 - 4
\stopformula

## 3. Gewünschte Struktur der Kurzarbeit

Die Kurzarbeit soll nach dem Hinweisabsatz **genau eine Hauptaufgabe** mit
**vier Teilaufgaben** enthalten. Inhaltlich sollen diese vier Teilaufgaben der
Vorlage entsprechen:

1. Symmetrieeigenschaften des Graphen von `f` nachweisen. **(BE 1)**
2. Nullstellen von `f(x)` berechnen und Vielfachheiten angeben. **(BE 4)**
3. Schnittpunkte der Graphen von `f` und `g` berechnen. **(BE 6)**
4. Die Graphen von `f` und `g` unter Verwendung der bisherigen Ergebnisse in ein
   kartesisches Koordinatensystem zeichnen. **(BE 5)**

Gesamtpunktzahl: **16 BE**. Die vier Teilaufgaben sollen im Stil und in der
Reihenfolge der Originalaufgabe formuliert sein; keine zusätzlichen Teilaufgaben.

## 4. Wichtige Anpassung gegenüber der Vorlage

- Kopiere die Quellaufgabe **nicht blind**.
- Setze für Teilaufgabe 4 den Zeichenbereich **verbindlich auf
  `-6 <= x <= 6`**. Der ursprüngliche Bereich `-2 <= x <= 2` wäre falsch:
  `f` hat Nullstellen bei `-4,-1,1,4`, und die weiter außen liegenden
  Schnittpunkte mit `g` liegen bei etwa `x = ±5.61`.
- Beachte bei der Zeichnung, dass der darzustellende `y`-Bereich ungefähr
  von `-10` bis `90` reicht; dies erfordert eine geeignete Skalierung.
  Die Aufgabe darf weiterhin die Schüler auffordern, das Koordinatensystem
  selbst unter Verwendung der bisherigen Ergebnisse zu zeichnen.
- Formuliere die Aufgabe so, dass sie wie eine stimmige Kurzarbeit wirkt und nicht wie
  ein unbearbeiteter Ausschnitt aus der Schulaufgabe.

## 5. Qualität und Prüfregeln

- Es handelt sich **nicht** um einen Reproduktionsauftrag, sondern um einen
  Erstellungsauftrag mit vorgegebenem Layout und vorgegebener fachlicher Struktur.
- Verwende gültige ConTeXt-Mathematik (`\math{...}`, `\startformula`/`\stopformula`),
  keine LaTeX-Dollar-Mathematik.
- Wenn du sprachliche Formelteile setzt, verwende die geeigneten High-Level-Befehle
  (`\text` bzw. `\mtext`) statt roher Schriftumschaltung.
- Achte auf saubere mathematische Schreibweise und konsistente ConTeXt-Syntax.
- Ziel ist eine **gute Ausgangsbasis für die manuelle Nachbearbeitung**. Falls eine
  Qualitätsregel nicht vollständig bestätigt werden kann, dokumentiere das offen.

## 6. Ergebnisartefakte

Erzeuge die regulären Ergebnisdateien:

- `result/main.tex`
- `result/main.pdf`
- `result/context.log`
- `result/include-snapshot.tar.gz`
