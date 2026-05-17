# roles/user_agent/

Synthetic user for multi-turn evaluation.

Load-bearing for interview-workflow development. Testing interview
flows against real subjects is slow, expensive, and ethically
constrained. The User Agent simulates the other side of the
conversation with realistic patterns:

- "Elderly family member being interviewed about their early career"
- "Technical founder being interviewed about hardware milestones"
- "Domain expert being interviewed about contested claims"

See architecture_notes §3.4.

## Discipline

The User Agent emits structured turns that look indistinguishable
from real subject responses to the interview workflow. Its behavior is
configurable per subject profile.

## Tier

Pro. Realistic conversational patterns require reasoning depth; a
flash-tier User Agent produces caricatures.

## Events emitted

- `simulate_subject_turn` — each generated response, tagged with the
  subject profile used
