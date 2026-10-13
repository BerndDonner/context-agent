SETZE EINEN GESPEICHERTEN ConTeXt-JOB FORT – KEINE NEUERZEUGUNG.

Der alte Hosted-Container und die alte Modellkonversation sind NICHT mehr verfügbar.
Im neuen Job-Archiv befinden sich bereits die letzte erstellte main.tex,
main.pdf, context.log und include-snapshot.tar.gz sowie ein checkpoint.json
und report.json. Die Include-Dateien wurden aus dem gesicherten Snapshot wiederhergestellt.

1. Suche unter /mnt/data nach agent-manifest.json oder context-agent-job.tar.gz.
   Wenn agent-manifest.json vorhanden ist, kopiere dessen job/ und runtime/ nach
   /mnt/data/work; ansonsten entpacke context-agent-job.tar.gz nach /mnt/data/work.
2. Führe den ConTeXt-Smoketest mit
   bash /mnt/data/work/runtime/bootstrap-context.sh --smoke aus.
3. Prüfe die bereits gespeicherte /mnt/data/work/job/result/main.tex sowie
   /mnt/data/work/job/result/checkpoint.json, report.json und task.md.
4. REPARIERE AUSSCHLIESSLICH die danach benannten offenen Fehler.
   Bewahre die übrige bisherige Fassung, einschließlich vorhandener Lösungen,
   Diagramme und sämtlicher allgemeiner Include-Helfer.
5. Kompiliere mit
   bash /mnt/data/work/runtime/bootstrap-context.sh --compile /mnt/data/work/job/result/main.tex /mnt/data/work/job/result/context.log
6. Aktualisiere nach jedem erfolgreichen Kompilieren den Include-Snapshot:
   bash /mnt/data/work/runtime/collect-includes.sh /mnt/data/work/job
7. Hinterlasse main.tex, main.pdf, context.log und include-snapshot.tar.gz
   im bestehenden /mnt/data/work/job/result/. Keine Git-Commits oder Pushes.

Du darfst keine fachliche Bearbeitung oder typografische Optimierung ausführen,
die nicht im eigentlichen Arbeitsauftrag verlangt wurde. Bei unleserlichen Stellen
ist die dokumentierte Unsicherheit beizubehalten. Verwende ConTeXt-Mathe statt $...$.


Längere ConTeXt-Kompilierungen über `managed-process.py start` und wiederholte
`managed-process.py wait`-Abfragen ausführen (siehe Systemanweisung),
nicht aus einem vorläufigen Shell-Exit-Code auf den Abschluss schließen.
