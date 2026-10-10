#!/usr/bin/env bash
# Full-history secret scan with a pinned, checksum-verified gitleaks binary.
# Findings are redacted: matched values are never printed.
# Usage: scripts/secret-scan.sh [--working-tree]
#   default         scan every commit reachable from any ref (history)
#   --working-tree  scan the current files, including uncommitted ones
set -euo pipefail

VERSION="8.21.2"
SHA256="5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba" # linux_x64
ROOT="$(git rev-parse --show-toplevel)"
CACHE="${GITLEAKS_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/agent-observatory/gitleaks-$VERSION}"
BIN="$CACHE/gitleaks"

if [[ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]]; then
  echo "secret-scan: only linux x86_64 is pinned; install gitleaks $VERSION and run it manually" >&2
  exit 2
fi

if [[ ! -x "$BIN" ]]; then
  mkdir -p "$CACHE"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL -o "$tmp/gl.tgz" \
    "https://github.com/gitleaks/gitleaks/releases/download/v$VERSION/gitleaks_${VERSION}_linux_x64.tar.gz"
  echo "$SHA256  $tmp/gl.tgz" | sha256sum -c --quiet -
  tar -xzf "$tmp/gl.tgz" -C "$tmp" gitleaks
  install -m 0755 "$tmp/gitleaks" "$BIN"
fi

# Redacted JSON report with locations (file, commit, line, rule) — never values.
REPORT="${SECRET_SCAN_REPORT:-$(mktemp -t gitleaks-report.XXXXXX.json)}"
set +e
if [[ "${1:-}" == "--working-tree" ]]; then
  "$BIN" dir --redact --no-banner --exit-code 1 --report-format json --report-path "$REPORT" "$ROOT"
else
  "$BIN" git --redact --no-banner --exit-code 1 --log-opts="--all" --report-format json --report-path "$REPORT" "$ROOT"
fi
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "secret-scan: findings (redacted) written to $REPORT" >&2
  python3 -I -c 'import json,sys
for f in json.load(open(sys.argv[1])):
    print("  {}: {}:{} commit={}".format(f.get("RuleID"), f.get("File"), f.get("StartLine"), (f.get("Commit") or "working-tree")[:12]))' "$REPORT" >&2 || true
fi
exit $rc
