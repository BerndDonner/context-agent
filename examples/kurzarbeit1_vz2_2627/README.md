# Kurzarbeit VZ2 2627 – bereinigter Testjob für context-agent

Dieser Job erzeugt **eine kurze Mathematik-Kurzarbeit** im Layout von
`input/Kurzarbeit1_VZ2_2526.tex`.

## Inhalt

- **Layoutquelle:** `input/Kurzarbeit1_VZ2_2526.tex`
- **Fachliche Vorlage:** `input/Schulaufgabe001_4FA_2324.tex`
- **Neue Zielfunktion:** `f(x) = \frac{1}{8}(x^4 - 17x^2 + 16)`
- **Vier Teilaufgaben:** Symmetrie (1 BE), Nullstellen (4 BE), Schnittpunkte
  mit `g(x)=2x^2-4` (6 BE), Zeichnung beider Graphen auf `-6 <= x <= 6` (5 BE)

## Wichtige Hinweise

- Nur `input/` und `include/` stammen aus dem ursprünglichen halbfertigen Paket.
- `job.yaml`, `task.md`, `README.md` und `template/template.tex` wurden für
  diesen Testjob neu erstellt.
- Es handelt sich **nicht** um eine Reproduktion, sondern um einen
  Erstellungsauftrag mit verbindlichem Layout und inhaltlicher Leitvorlage.
- Das Template enthält bereits das Deckblatt. Der Agent soll ausschließlich
  den Aufgabenbereich nach `\page[yes]` austauschen; 16 BE und ein freies
  Datumsfeld sind bewusst so festgelegt.
- Die aktivierten Quality Rules sind:
  - `dollar_math`
  - `semantic_numbers`
  - `semantic_math_text`
  - `number_with_unit`
- `coordinate_reuse` ist absichtlich **nicht** aktiviert, weil keine MetaPost-
  Grafik erzeugt werden soll.

## Start

Vom Repository-Root aus:

```bash
context-agent validate /pfad/zum/job
context-agent run /pfad/zum/job
```

Passe `runtime.context_archive` in `job.yaml` an, falls dein lokaler Pfad abweicht.

## Konsistenzprüfung: Einheiten auf dem Deckblatt

Die Kurzarbeitsvorlage dient als visuelle und strukturelle Referenz, nicht als
unveränderbarer Quellcode. `30min` wurde im Template durch `30\unit{Minute}`
ersetzt. Die Qualitätsregeln dürfen gleichwertige technische Verbesserungen
auch am Deckblatt und in den Fußzeilen vornehmen; `input/` bleibt unverändert.

## Schriften / erster Requirements-Test

Die Font-Weiche im Template übernimmt die vorgegebene Auswahl:
**Calibri → Carlito → IBM Plex Sans**. Die ursprüngliche Kurzarbeit in
`input/` bleibt unverändert. Bei fehlendem Calibri gilt Carlito ausdrücklich
als zulässig; eine Requirements-Prüfung darf daraus allein keinen Fehler
machen. Verwendete Schriften und Schriftschnitte sollen im kompilierten PDF
kontrolliert werden. Die letzte Stufe benötigt ebenfalls tatsächlich
vorhandene IBM-Plex-Sans-Schriftdateien.
