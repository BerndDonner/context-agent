Der äußere Orchestrator konnte den letzten Lauf nicht als erfolgreich abnehmen.
Folgende Ergebnisanforderungen fehlen oder sind ungültig:

{missing}

Arbeite im bestehenden Container und im bestehenden Verzeichnis
`/mnt/data/work/job/result`. Diagnostiziere die Ursache, repariere das Dokument und kompiliere
erneut. Bewahre vorhandene brauchbare Arbeit. Erzeuge nach dem Kompilieren stets
`bash /mnt/data/work/runtime/collect-includes.sh /mnt/data/work/job`.
Stelle danach `main.tex`, ein gültiges `main.pdf`, `context.log` und
`include-snapshot.tar.gz` bereit.


Längere ConTeXt-Kompilierungen über `managed-process.py start` und wiederholte
`managed-process.py wait`-Abfragen ausführen (siehe Systemanweisung),
nicht aus einem vorläufigen Shell-Exit-Code auf den Abschluss schließen.
