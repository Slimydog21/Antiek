#!/usr/bin/env bash
# Optional dev-environment dependencies for the Wrestle Evolution
# integration (2026-05-22 follow-up).
#
# The integration ships substrate + UI surfaces that degrade gracefully
# when these dependencies are missing. Installing them flips the
# graceful stubs to real implementations. Each block is independent;
# run the ones the operator needs.
#
# Usage:
#   bash scripts/install-optional-deps.sh         # install everything
#   bash scripts/install-optional-deps.sh thumbnails  # install just thumbnails
#   bash scripts/install-optional-deps.sh test    # install just test-env packages
#
# Idempotent — re-running is safe (pip + pnpm both detect already-installed).

set -euo pipefail

GROUP="${1:-all}"

THUMBNAILS=0
TIPTAP=0
PLAYWRIGHT=0
TESTENV=0

case "$GROUP" in
  thumbnails) THUMBNAILS=1 ;;
  tiptap)     TIPTAP=1 ;;
  playwright) PLAYWRIGHT=1 ;;
  test)       TESTENV=1 ;;
  all)        THUMBNAILS=1; TIPTAP=1; PLAYWRIGHT=1; TESTENV=1 ;;
  *)
    echo "usage: $0 [all|thumbnails|tiptap|playwright|test]" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "$THUMBNAILS" -eq 1 ]]; then
  echo "==> [thumbnails] Installing PyMuPDF for PDF page-1 thumbnail rendering."
  echo "    Unblocks services/library/thumbnails.py. The module also accepts"
  echo "    pdf2image + Poppler; PyMuPDF is the pure-Python option that doesn't"
  echo "    require a system Poppler install."
  pip install pymupdf
fi

if [[ "$TIPTAP" -eq 1 ]]; then
  echo "==> [tiptap] Installing TipTap for SPR-08 block NodeView wrapping."
  echo "    Unblocks the per-document notebook block components. Adds ~10MB"
  echo "    to node_modules but enables the rich-text editing the spec called"
  echo "    for. The components are already shaped-as-NodeView; this install"
  echo "    flips them from React+Tailwind to true TipTap wrappers."
  if command -v pnpm >/dev/null; then
    (cd apps/reading && pnpm add @tiptap/core @tiptap/react @tiptap/starter-kit)
  else
    (cd apps/reading && npm install --save @tiptap/core @tiptap/react @tiptap/starter-kit)
  fi
fi

if [[ "$PLAYWRIGHT" -eq 1 ]]; then
  echo "==> [playwright] Installing Playwright for the SPR-04/SPR-05/SPR-06/SPR-07/SPR-08/SPR-11 E2E specs."
  echo "    Unblocks the 7 e2e/*.spec.ts files committed at canonical paths."
  if command -v pnpm >/dev/null; then
    (cd apps/reading && pnpm add -D @playwright/test && pnpm exec playwright install chromium)
  else
    (cd apps/reading && npm install --save-dev @playwright/test && npx playwright install chromium)
  fi
fi

if [[ "$TESTENV" -eq 1 ]]; then
  echo "==> [test] Installing FastAPI + fakeredis for Python test env."
  echo "    Unblocks 23 ingestion tests + the API tests that need a"
  echo "    FastAPI TestClient. fakeredis matches the SPR-03 throttle path."
  pip install fastapi fakeredis httpx
fi

echo ""
echo "Done. The relevant stubs/skips will now flip to real implementations:"
[[ "$THUMBNAILS" -eq 1 ]] && echo "  ✓ services.library.thumbnails.generate_thumbnail returns real PNG"
[[ "$TIPTAP" -eq 1 ]] && echo "  ✓ SPR-08 block components ready for TipTap NodeView wrapping"
[[ "$PLAYWRIGHT" -eq 1 ]] && echo "  ✓ pnpm e2e <spec>.ts runs across all 7 committed specs"
[[ "$TESTENV" -eq 1 ]] && echo "  ✓ pytest services/ingestion/tests/ runs all 22+e2e+api tests"
