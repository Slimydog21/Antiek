# Runtime dependency security repair, 2026-09-20

## User-visible failure and scope

Read-only production metadata found cryptography49.0.0, pypdf6.11.0 and
yt-dlp2026.3.17. Saved OSV records mark these versions affected by published
advisories. Feature-specific exploitability has not been established. Production
uses CPython3.12.3 on x86_64. Neither deployment playbook applied the committed
lock or constraints to its editable install, and neither requested the youtube
extra, so an older yt-dlp could remain installed indefinitely.

## Contract and diagnosis

Security constraints must affect actual installation and fail deployment if
installed versions differ. The production install must request the packages it
manages; a constraint alone does not install an unrequested extra. A lockfile
update alone is not a production fix. Full production environment locking is a
separate open requirement; this patch enforces the three reviewed security
versions without imposing unrelated lint-environment pins on production.

## Evidence before repair

Production metadata was read without changing services or packages. The saved
OSV response contains48 records representing25 alias-connected advisories,
not48 distinct vulnerabilities. Minimum versions covering those saved records
are cryptography50.0.0, pypdf6.16.1 and yt-dlp2026.7.4. Targeted OSV queries for
50.0.1,6.19.0 and2026.8.19 returned no matching advisories on2026-09-20. This is
a point-in-time advisory query, not a guarantee against undisclosed defects.

## Implementation

Root requirement floors and uv.lock resolution are upgraded. Setup and deploy
share Python install/verification tasks. Existing extras are preserved, youtube
is added, and infrastructure/requirements-security.txt constrains the three
exact versions. The task then verifies installed distribution metadata against
that file and runs pip check before continuing. Errors stop the play. No service
restart or production installation has been executed.

## Verification

RAN: six deployment tests exercise task wiring, actual metadata discovery with
isolated dist-info fixtures, stale/missing packages, and empty constraints.
Both Ansible playbook syntax checks pass. Ruff and diff checks pass for the
new tests. uv cross-platform resolution succeeds for the actual deployment
extras on Linux x86_64 with both Python3.12.3 and3.14, under the security pins.
This proves resolution, not Linux package execution.

RAN: actual shared Ansible tasks against a disposable Python3.12 fixture seeded
with cryptography49 upgraded it to50.0.1, installed pypdf6.19.0 and
yt-dlp2026.8.19, and passed metadata verification and pip check,3 tasks0 failed.
After installing declared core dependencies, actual library and native-format
tests passed86 with10 existing missing-substrate/ingestion integration skips.
The initial smaller fixture failed collection for missing httpx; it is not
counted as a pass. PDF extraction, WebAuthn ECDSA verification/tamper rejection
and offline yt-dlp metadata processing all executed against upgraded libraries.

In progress: full CI-extra Python3.14 install and lint baseline comparison;
independent GLM deployment review. A Linux3.12/3.14 workflow now runs the scoped
real-library suite under the security constraints; no remote pass is claimed
until that workflow executes.

## Risks and limitations

The local Docker daemon is unavailable. Native Linux execution remains unproven.
Existing YouTube adapter and passkey-route tests mock external metadata or
verification; the new library-level tests reduce that gap without claiming a
live browser authenticator or YouTube network interaction. Applying upgrades to
an existing venv is not atomic; a failed install/check can leave it partially
changed, as in the existing deployment mechanism. Version verification prevents
continuation but is not rollback. A staged venv generation/rollback design is a
separate environment-reproducibility requirement.

## Grade and next action

Implementation and verification are in progress. No100/100 or production repair
claim. Prior evidence review92/100 excluded clean environment resolution and
application verification. Finish those checks, resolve the complete constraint
freeze/baseline diff, obtain heterogeneous review, then open a draft PR. Merge
and production integration remain operator-controlled.

## Reproduction and handoff

Worktree: .worktrees/runtime-dependency-security-20260920.
Branch: fix/runtime-dependency-security-20260920, baseee283d9c8.
Evidence logs: .audit/dependency-security/ including Linux resolution, target
OSV query, Ansible syntax, isolated deployment run, package install and review.
No schema, Parquet, writer-coordination or frontend change belongs to this lane.
