#!/usr/bin/env bash
# Goal verification plan — canonical root only (see docs/WORKFLOW_SINGLE_ROOT.md).
# Full stdout (no tail truncation). Usage:
#   ./scripts/run_goal_verification_plan.sh /path/to/scratch
set -euo pipefail
SCRATCH="${1:?scratch dir required}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi

mkdir -p "$SCRATCH"

{
  echo "=== step 1a: antiek_check workflows (run 1) ==="
  "$PY" antiek_check.py workflows
  echo "=== step 1b: antiek_check workflows (run 2) ==="
  "$PY" antiek_check.py workflows
} 2>&1 | tee "$SCRATCH/antiek-check-full.log"

{
  echo "=== step 2: goal_workflow_evidence (9-phase clean intake) ==="
  "$PY" scripts/goal_workflow_evidence.py
} 2>&1 | tee "$SCRATCH/deep-research-verify.log"

{
  echo "=== step 2b: pytest goal workflow (capture=tee) ==="
  "$PY" -m pytest tests/test_goal_workflow_verification.py -vv --capture=tee-sys
} 2>&1 | tee "$SCRATCH/goal-workflow-pytest.log"

{
  echo "=== step 3: HTML projection artifact ==="
  "$PY" -c "
from pathlib import Path
from substrate.research_artifact.schema import ResearchArtifactBody, ArtifactInsight
from substrate.research_artifact.render import render_html
from substrate.research_artifact.projection_verify import verify_kb_projection
body = ResearchArtifactBody(
    investigation_id='inv-scratch-proj',
    problem_question='Scratch projection verify',
    insights=[ArtifactInsight(node_id='n1', text='claim', confidence='high')],
    synthesis_excerpt='Synth excerpt.',
)
html = render_html(body, interactive=False)
Path('$SCRATCH/html-projection-artifact.html').write_text(html)
r = verify_kb_projection(body)
Path('$SCRATCH/projection-verify.log').write_text(str(r))
print('projection_verify', r)
print('html_path=$SCRATCH/html-projection-artifact.html')
"
} 2>&1 | tee -a "$SCRATCH/projection-verify.log"

{
  echo "=== step 4a: pytest reading workflow (Python) ==="
  "$PY" -m pytest tests/test_reading_kb_artifact.py tests/test_reader_snapshot.py -vv --capture=tee-sys
  echo "=== step 4b: vitest kbArtifactCondense (TypeScript) ==="
  (cd apps/reading && npm run test -- --run src/lib/kbArtifactCondense.test.ts)
} 2>&1 | tee "$SCRATCH/reading-workflow.log"

{
  echo "=== step 5: co-CEO CLIs ==="
  command -v grok
  grok --help 2>&1 | head -6
  command -v mimo
  mimo --help 2>&1 | head -6
} 2>&1 | tee "$SCRATCH/ai-co-ceo-clis.log"

echo "GOAL_VERIFICATION_PLAN_DONE" | tee "$SCRATCH/verification-plan.done"