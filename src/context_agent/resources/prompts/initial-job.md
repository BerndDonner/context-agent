Erstelle den ConTeXt-Job vollständig.

Die Sandbox enthält die entpackten oder noch gepackten Bestandteile eines Job-Archivs sowie
ein undurchsichtig verpacktes ConTeXt-LMTX-Bündel mit der Endung `.ctxbundle`. Gehe wie folgt
vor, ohne nach Bestätigung zu fragen:

1. Finde unter `/mnt/data` die Datei `agent-manifest.json`.
   - Wenn sie bereits vorhanden ist, bestimme ihr Verzeichnis als Quellwurzel. Kopiere von
     dort ausschließlich `job/`, `runtime/` und `agent-manifest.json` nach `/mnt/data/work`.
   - Wenn sie noch nicht vorhanden ist, finde `context-agent-job.tar.gz` und entpacke dieses
     Archiv nach `/mnt/data/work`.
   Danach müssen `/mnt/data/work/job`, `/mnt/data/work/runtime` und
   `/mnt/data/work/agent-manifest.json` existieren.
2. Führe einmal den Smoke-Test aus:
   `bash /mnt/data/work/runtime/bootstrap-context.sh --smoke`
3. Lies `agent-manifest.json`, `job/job.yaml`, `job/{task_path}` und
   `job/{template_path}` sowie die benötigten Eingaben und Referenzen.
4. Erzeuge das Ergebnis direkt in `/mnt/data/work/job/result/`.
5. Kompiliere von dort aus mit dem flüchtigen ConTeXt-Runner:
   `bash /mnt/data/work/runtime/bootstrap-context.sh --compile /mnt/data/work/job/result/main.tex /mnt/data/work/job/result/context.log`
   Der Runner entpackt ConTeXt nur für diesen einen Lauf und räumt es auch bei einem Fehler
   danach wieder auf. Rufe ihn bei jeder Reparaturrunde erneut auf. Repariere Compiler-, Lua-,
   MetaPost-, Include- und Pfadfehler selbstständig.
6. Stelle am Ende mindestens diese Dateien bereit:
   - `/mnt/data/work/job/result/main.tex`
   - `/mnt/data/work/job/result/main.pdf`
   - `/mnt/data/work/job/result/context.log`

Konfigurierte Eingaben und Referenzen:
{attachments}

Die PDF- und Bilddateien sind zusätzlich direkt an diese Anfrage angehängt. Nutze sie für
inhaltliche und visuelle Quellenauswertung, aber beachte weiterhin Rolle und Policy aus dem
Manifest.

Wichtig: `main.tex` liegt im Verzeichnis `job/result`. Relative Pfade zu mitgelieferten
Dateien sollen deshalb vorzugsweise auf `../include/...` zeigen. Passe alte Template-Pfade nur
soweit technisch nötig an; erfinde kein neues Layout.
