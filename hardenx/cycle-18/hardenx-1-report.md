
hardenx  /Users/slimydog/Antiek/platform/worktrees/campaign-mo-swarm
  framework=fastapi  ·  ai=HuggingFace,OpenAI Whisper,HuggingFace,Anthropic,PyTorch,HuggingFace  ·  git

  ADVISORY (11) — context, not gate-worthy
      medium  services/antiek_format/signature.py:209  high_entropy_string
              untyped high-entropy string — usually a hash/constant, verify by eye
      medium  substrate/graph/schema.py:1003  high_entropy_string
              untyped high-entropy string — usually a hash/constant, verify by eye
      medium  tools/reachability/probes/usability_keystone.py:167  high_entropy_string
              untyped high-entropy string — usually a hash/constant, verify by eye
      medium  tools/synquery/client.py:76  high_entropy_string
              untyped high-entropy string — usually a hash/constant, verify by eye
         low  orjson  installed 3.11.9 (floor 3.10) — patched
              manifest floor flagged but the installed version is clean per OSV
         low  requests  installed 2.33.1 (floor 2.31) — patched
              manifest floor flagged but the installed version is clean per OSV
         low  pynacl  installed 1.6.2 (floor 1.5) — patched
              manifest floor flagged but the installed version is clean per OSV
         low  cryptography  installed 49.0.0 (floor 42.0) — patched
              manifest floor flagged but the installed version is clean per OSV
      medium  pypdf  floor 4.3: 38 CVE(s); not installed/resolved
              flagged at manifest floor; not present in the resolved environment — verify before acting
      medium  yt-dlp  floor 2024.8.6: 5 CVE(s); not installed/resolved
              flagged at manifest floor; not present in the resolved environment — verify before acting
         low  pytest  installed 9.1.1 (floor 8.3) — patched
              manifest floor flagged but the installed version is clean per OSV

  raw harden 100/CRITICAL  →  hardenx LOW   (0 real · 11 advisory · 9 filtered · deps via .venv (OSV-reverified))
  (run with --explain to see the 9 filtered)

