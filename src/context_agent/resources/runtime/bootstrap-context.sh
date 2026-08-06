#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
DEST="${2:-/mnt/data/context-lmtx}"

if [[ -z "$ARCHIVE" ]]; then
  ARCHIVE="$(find /mnt/data -maxdepth 2 -type f -name 'context*lmtx*.tar.xz' -print -quit)"
fi
if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "ConTeXt archive not found" >&2
  return 2 2>/dev/null || exit 2
fi

if [[ ! -f "$DEST/.context-agent-ready" ]]; then
  rm -rf "$DEST"
  mkdir -p "$DEST"
  tar -xJf "$ARCHIVE" -C "$DEST" --strip-components=1
  chmod -R u+rwX "$DEST"

  mkdir -p "$DEST/bin"
  cat > "$DEST/bin/mtxrun" <<EOF
#!/usr/bin/env bash
exec "$DEST/tex/texmf-linux-64/bin/luametatex" \
  --luaonly "$DEST/tex/texmf-linux-64/bin/mtxrun.lua" "\$@"
EOF
  cat > "$DEST/bin/context" <<EOF
#!/usr/bin/env bash
exec "$DEST/tex/texmf-linux-64/bin/luametatex" \
  --luaonly "$DEST/tex/texmf-linux-64/bin/context.lua" "\$@"
EOF
  chmod +x "$DEST/bin/mtxrun" "$DEST/bin/context"

  "$DEST/bin/mtxrun" --generate
  touch "$DEST/.context-agent-ready"
fi

export PATH="$DEST/bin:$PATH"
export CONTEXT_AGENT_CONTEXT_ROOT="$DEST"

SMOKE="$DEST/smoke-test"
mkdir -p "$SMOKE"
cat > "$SMOKE/smoke.tex" <<'EOF'
\starttext
ConTeXt funktioniert.
\stoptext
EOF
(
  cd "$SMOKE"
  context smoke.tex > smoke-run.log 2>&1
)

if [[ ! -s "$SMOKE/smoke.pdf" ]]; then
  echo "ConTeXt smoke test failed" >&2
  tail -n 100 "$SMOKE/smoke-run.log" >&2 || true
  return 3 2>/dev/null || exit 3
fi

cat > "$DEST/env.sh" <<EOF
export PATH="$DEST/bin:\$PATH"
export CONTEXT_AGENT_CONTEXT_ROOT="$DEST"
EOF

echo "ConTeXt ready: $DEST/bin/context"
context --version 2>/dev/null | head -n 5 || true
