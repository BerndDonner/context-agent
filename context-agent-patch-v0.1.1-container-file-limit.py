#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


CONTEXT_HEADER = 'CONTEXT_AGENT_ARCHIVE_V1'


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one matching block, found {count}')
    return text.replace(old, new, 1)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
    package = root / 'src' / 'context_agent'
    if not (root / 'pyproject.toml').is_file() or not package.is_dir():
        raise RuntimeError(
            f'{root} does not look like the context-agent repository root '
            '(pyproject.toml and src/context_agent are required)'
        )

    patch_backend(package / 'openai_backend.py')
    write_runtime(package / 'resources' / 'runtime' / 'bootstrap-context.sh')
    write_initial_prompt(package / 'resources' / 'prompts' / 'initial-job.md')
    patch_system_prompt(package / 'resources' / 'prompts' / 'system.md')
    patch_tests(root)
    patch_docs(root)
    bump_version(root / 'pyproject.toml')

    print('Patch applied successfully.')
    print('Run:')
    print('  python -m pytest -q')
    print('  python -m context_agent validate examples/minimal-job')
    print('  python -m context_agent run examples/minimal-job')
    return 0


def patch_backend(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    if '_CONTEXT_BUNDLE_HEADER = b"CONTEXT_AGENT_ARCHIVE_V1\\n"' in text:
        print(f'already patched: {path}')
        return

    text = replace_once(
        text,
        'import json\n',
        'import json\nimport shutil\nimport tempfile\n',
        label='openai_backend imports',
    )
    text = replace_once(
        text,
        'from context_agent.models import AgentTurn, ResolvedJob\n',
        'from context_agent.models import AgentTurn, ResolvedJob\n\n\n'
        '_CONTEXT_BUNDLE_HEADER = b"CONTEXT_AGENT_ARCHIVE_V1\\n"\n',
        label='openai_backend bundle header',
    )

    old = '''    def _prepare_remote(self) -> None:
        bundle = self._upload(self.bundle_path)
        context_archive = self._upload(self.job.context_archive)
        for path in self.direct_files:
            self._upload(path)

        expires_minutes = min(60, max(20, self.job.config.limits.timeout_seconds // 60 + 5))
        try:
            container = self._client.containers.create(
                name=f"context-agent-{self.job.root.name}",
                file_ids=[item.file_id for item in self._uploaded],
                memory_limit=self.job.config.runtime.memory_limit,
                expires_after={"anchor": "last_active_at", "minutes": expires_minutes},
            )
        except Exception as exc:
            raise RemoteAgentError(f"failed to create hosted container: {exc}") from exc
        self.container_id = str(container.id)

        if bundle.file_id == context_archive.file_id:  # defensive; should never happen
            raise RemoteAgentError("job bundle and ConTeXt archive received identical file IDs")
'''
    new = '''    def _prepare_remote(self) -> None:
        bundle = self._upload(self.bundle_path)

        # Hosted containers automatically expand recognized archives. A complete
        # ConTeXt tree contains several thousand files and would exceed the container
        # attachment limit before the first model turn. Prefixing the XZ stream with a
        # private header keeps it as one opaque file. The runtime helper removes the
        # header and extracts ConTeXt only for one compilation.
        with tempfile.TemporaryDirectory(prefix="context-agent-upload-") as temporary:
            context_bundle_path = Path(temporary) / "context-lmtx.ctxbundle"
            _write_context_bundle(self.job.context_archive, context_bundle_path)
            context_bundle = self._upload(context_bundle_path)

            for path in self.direct_files:
                self._upload(path)

            expires_minutes = min(
                60, max(20, self.job.config.limits.timeout_seconds // 60 + 5)
            )
            try:
                container = self._client.containers.create(
                    name=f"context-agent-{self.job.root.name}",
                    file_ids=[item.file_id for item in self._uploaded],
                    memory_limit=self.job.config.runtime.memory_limit,
                    expires_after={"anchor": "last_active_at", "minutes": expires_minutes},
                )
            except Exception as exc:
                raise RemoteAgentError(f"failed to create hosted container: {exc}") from exc
            self.container_id = str(container.id)

        if bundle.file_id == context_bundle.file_id:  # defensive; should never happen
            raise RemoteAgentError("job bundle and ConTeXt bundle received identical file IDs")
'''
    text = replace_once(text, old, new, label='openai_backend _prepare_remote')

    marker = '\ndef _extract_output_text(response: Any, raw: dict[str, Any]) -> str:\n'
    helper = '''

def _write_context_bundle(source: Path, destination: Path) -> None:
    """Wrap an XZ archive so hosted containers do not auto-expand it on attachment."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_stream, destination.open("wb") as output_stream:
        output_stream.write(_CONTEXT_BUNDLE_HEADER)
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
'''
    text = replace_once(text, marker, helper + marker, label='openai_backend helper insertion')
    path.write_text(text, encoding='utf-8')


def write_runtime(path: Path) -> None:
    content = r'''#!/usr/bin/env bash
set -euo pipefail

HEADER='CONTEXT_AGENT_ARCHIVE_V1'

find_bundle() {
  find /mnt/data -type f -name '*.ctxbundle' -print -quit
}

run_context() (
  source_file="$1"
  log_file="$2"

  bundle="${CONTEXT_AGENT_CONTEXT_BUNDLE:-$(find_bundle)}"
  if [[ -z "$bundle" || ! -f "$bundle" ]]; then
    echo "Opaque ConTeXt bundle (*.ctxbundle) not found under /mnt/data" >&2
    return 2
  fi
  if [[ ! -f "$source_file" ]]; then
    echo "ConTeXt source not found: $source_file" >&2
    return 2
  fi

  source_file="$(realpath "$source_file")"
  log_file="$(realpath -m "$log_file")"
  mkdir -p "$(dirname "$log_file")"

  temporary="$(mktemp -d /mnt/data/context-agent-lmtx.XXXXXX)"
  trap 'rm -rf "$temporary"' EXIT
  archive="$temporary/context-lmtx-ready.tar.xz"
  context_root="$temporary/context-lmtx"
  mkdir -p "$context_root"

  python - "$bundle" "$archive" "$HEADER" <<'PYCODE'
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
header = (sys.argv[3] + "\n").encode("ascii")
with source.open("rb") as input_stream:
    actual = input_stream.read(len(header))
    if actual != header:
        raise SystemExit("invalid context-agent ConTeXt bundle header")
    with destination.open("wb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
PYCODE

  tar -xJf "$archive" -C "$context_root" --strip-components=1

  (
    cd "$(dirname "$source_file")"
    "$context_root/context-local.sh" "$(basename "$source_file")" >"$log_file" 2>&1
  )
)

case "${1:-}" in
  --smoke)
    smoke_dir="$(mktemp -d /mnt/data/context-agent-smoke.XXXXXX)"
    trap 'rm -rf "$smoke_dir"' EXIT
    cat > "$smoke_dir/smoke.tex" <<'EOF'
\starttext
ConTeXt funktioniert.
\stoptext
EOF
    run_context "$smoke_dir/smoke.tex" "$smoke_dir/context.log"
    if [[ ! -s "$smoke_dir/smoke.pdf" ]]; then
      echo "ConTeXt smoke test failed" >&2
      tail -n 100 "$smoke_dir/context.log" >&2 || true
      exit 3
    fi
    echo "ConTeXt smoke test passed"
    ;;
  --compile)
    if [[ $# -ne 3 ]]; then
      echo "usage: $0 --compile SOURCE.tex LOGFILE" >&2
      exit 2
    fi
    run_context "$2" "$3"
    ;;
  *)
    echo "usage: $0 --smoke | --compile SOURCE.tex LOGFILE" >&2
    exit 2
    ;;
esac
'''
    path.write_text(content, encoding='utf-8')
    path.chmod(0o755)


def write_initial_prompt(path: Path) -> None:
    content = r'''Erstelle den ConTeXt-Job vollständig.

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
'''
    path.write_text(content, encoding='utf-8')


def patch_system_prompt(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    if 'bereitgestellten flüchtigen Runner' in text:
        return
    old = (
        'Du darfst das Shell-Werkzeug selbstständig und mehrfach verwenden. Das Netzwerk wird nicht\n'
        'benötigt. Antworte am Ende knapp und nenne den Kompilierstatus.\n'
    )
    new = (
        'Du darfst das Shell-Werkzeug selbstständig und mehrfach verwenden. Verwende für jeden\n'
        'ConTeXt-Lauf ausschließlich den bereitgestellten flüchtigen Runner; entpacke die ConTeXt-\n'
        'Distribution nicht dauerhaft selbst. Das Netzwerk wird nicht benötigt. Antworte am Ende knapp\n'
        'und nenne den Kompilierstatus.\n'
    )
    path.write_text(replace_once(text, old, new, label='system prompt'), encoding='utf-8')


def patch_tests(root: Path) -> None:
    backend_test = root / 'tests' / 'test_openai_backend.py'
    text = backend_test.read_text(encoding='utf-8')
    if '_write_context_bundle' not in text:
        text = replace_once(
            text,
            'from context_agent.openai_backend import OpenAIHostedSession, UploadedFile\n',
            'from context_agent.openai_backend import (\n'
            '    OpenAIHostedSession,\n'
            '    UploadedFile,\n'
            '    _write_context_bundle,\n'
            ')\n',
            label='test_openai_backend import',
        )
        text += '''

def test_context_archive_is_wrapped_as_opaque_bundle(tmp_path: Path) -> None:
    source = tmp_path / "context.tar.xz"
    source.write_bytes(b"\\xfd7zXZ\\x00payload")
    destination = tmp_path / "context.ctxbundle"

    _write_context_bundle(source, destination)

    data = destination.read_bytes()
    assert data.startswith(b"CONTEXT_AGENT_ARCHIVE_V1\\n")
    assert data.endswith(source.read_bytes())
    assert not data.startswith(b"\\xfd7zXZ")
'''
        backend_test.write_text(text, encoding='utf-8')

    runtime_test = root / 'tests' / 'test_runtime_script.py'
    runtime_test.write_text(
        '''from pathlib import Path\n\n\ndef test_runtime_script_uses_ephemeral_context_tree() -> None:\n'''
        '    script = (\n'
        '        Path(__file__).parents[1]\n'
        '        / "src/context_agent/resources/runtime/bootstrap-context.sh"\n'
        '    ).read_text(encoding="utf-8")\n\n'
        '    assert "*.ctxbundle" in script\n'
        '    assert "mktemp -d /mnt/data/context-agent-lmtx" in script\n'
        '    assert "trap \'rm -rf \\\"$temporary\\\"\' EXIT" in script\n'
        '    assert "--compile" in script\n',
        encoding='utf-8',
    )


def patch_docs(root: Path) -> None:
    note = '''

### Dateigrenze des Hosted Containers

Das portable ConTeXt-Archiv wird als undurchsichtiges `.ctxbundle` hochgeladen und nicht als
erkennbares Archiv. Erkannte Archive werden beim Bereitstellen für den Container aufgefächert;
der vollständige ConTeXt-Baum enthält mehr als 6.000 Dateien. Der Runtime-Helper entfernt den
privaten Header, entpackt ConTeXt nur für genau einen Übersetzungslauf und löscht den temporären
Baum auch nach einem Compilerfehler wieder.
'''
    for name in ('DESIGN.md', 'README.md'):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if 'Dateigrenze des Hosted Containers' not in text:
            path.write_text(text + note, encoding='utf-8')


def bump_version(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    if 'version = "0.1.0"' in text:
        path.write_text(text.replace('version = "0.1.0"', 'version = "0.1.1"', 1), encoding='utf-8')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'Patch failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
