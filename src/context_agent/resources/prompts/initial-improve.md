ÜBERARBEITE EIN BESTEHENDES ConTeXt-DOKUMENT, KEINE NEUERZEUGUNG.

Die unveränderliche Ausgangsfassung steht unter `job/{source_path}`.
Sie wurde BEREITS BYTEGENAU nach `job/result/main.tex` kopiert.
Das Originaldokument ist die verbindliche Arbeitsgrundlage. Das Template dient nur
als verbindliche Layoutvorgabe; es darf NICHT anstelle der vorhandenen Präambel
oder des vorhandenen Dokumentkörpers neu eingesetzt werden.

1. Bereite `agent-manifest.json`, `job/` und `runtime/` unter `/mnt/data/work` vor,
   wie in der Systemanweisung beschrieben, und führe den LMTX-Smoke-Test aus.
2. Lies `job/{task_path}`, das Template `job/{template_path}`, die Datei
   `job/{source_path}` und die unten genannten Quellen/Referenzen.
3. Das ist ZUERST ausschließlich ein Baseline-Compile. Verändere `result/main.tex`
   NICHT – weder bei einem Schreibweisenproblem noch bei einer Unsicherheit.
4. Kompiliere `result/main.tex` mit `bootstrap-context.sh --compile` aus
   `/mnt/data/work/job/result`; belasse die vorhandene Quelldatei bytegenau.
   Bei fehlerhaftem Baseline-Compile keine stillschweigenden Inhaltsänderungen.
5. Erzeuge `include-snapshot.tar.gz` über `collect-includes.sh`.
   Die vier Ergebnisartefakte sind `main.tex`, `main.pdf`, `context.log`,
   `include-snapshot.tar.gz`.
6. Antworte mit Kompilierstatus. Verbesserungen selbst werden ERST in der
   nachgelagerten, überwachten Qualitäts- und Requirements-Phase ausgeführt.

Referenz-PDFs belegen bei Bedarf unklare Originalstellen, ersetzen aber NIEMALS
allein die bestehende `.tex` und autorisieren keine unaufgeforderte Neufassung.

Konfigurierte Eingaben und Referenzen:
{attachments}
