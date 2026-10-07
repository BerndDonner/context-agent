from pathlib import Path


def test_runtime_script_uses_ephemeral_context_tree() -> None:
    script = (
        Path(__file__).parents[1]
        / "src/context_agent/resources/runtime/bootstrap-context.sh"
    ).read_text(encoding="utf-8")

    assert "*.ctxbundle" in script
    assert "mktemp -d /mnt/data/context-agent-lmtx" in script
    assert "trap 'rm -rf \"$temporary\"' EXIT" in script
    assert "--compile" in script
