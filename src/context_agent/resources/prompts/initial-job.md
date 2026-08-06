Erstelle den ConTeXt-Job vollständig.

Die Sandbox enthält ein Job-Archiv `context-agent-job.tar.gz` und ein portables
ConTeXt-LMTX-Archiv. Gehe wie folgt vor, ohne nach Bestätigung zu fragen:

1. Finde beide Archive unter `/mnt/data`.
2. Entpacke das Job-Archiv nach `/mnt/data/work`, sodass dort `job/`, `runtime/` und
   `agent-manifest.json` liegen.
3. Rufe `bash runtime/bootstrap-context.sh` auf, um das ConTeXt-Archiv nach
   `/mnt/data/context-lmtx` zu entpacken und den Smoke-Test auszuführen.
4. Lies `agent-manifest.json`, `job/job.yaml`, `job/{task_path}` und
   `job/{template_path}` sowie die benötigten Eingaben und Referenzen.
5. Erzeuge das Ergebnis direkt in `/mnt/data/work/job/result/`.
6. Kompiliere von diesem Ergebnisverzeichnis aus. Verwende dabei vorzugsweise den absoluten
   Aufruf `/mnt/data/context-lmtx/bin/context main.tex` und schreibe die relevante Ausgabe nach
   `context.log`. Repariere Compiler-, Lua-, MetaPost-, Include- und Pfadfehler selbstständig.
7. Stelle am Ende mindestens diese Dateien bereit:
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
