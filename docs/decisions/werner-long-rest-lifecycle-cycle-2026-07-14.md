# Werner long-rest lifecycle — 2026-07-14

Decision: the shell-owned `PenguinMascot` gains one persistent rest lifecycle, separate from the selected station activity's pointer-idle ambient.

Why: two-second pointer idle is cursor-bait state and already owns ice fishing. It is not evidence that the whole workstation has rested. SPR-18 removed the resulting duplicate sleeping reaction. SPR-17 preserved an authored waking asset but forbade runtime use until a truthful persistent lifecycle existed.

Authority:

- `createStationRestLifecycle` owns one cancellable rest deadline, wake deadline, phase, and epoch.
- `PenguinMascot` is the only production consumer and the only renderer choosing neutral rig, activity ambient, sleep, wake, foreground emote, or movement.
- The private `WernerAuthoredPose` map owns the waking raster import.
- The existing arcade suspension lease blocks the lifecycle during explicit play.

Timing: `STATION_LONG_REST_MS = 120_000` is a deliberate product value, not derived from `POINTER_IDLE_MS`. It leaves the normal fishing episode ample room to read before the rarer background-TV sleep episode. `STATION_WAKE_MS = 900` matches one restrained, legible authored-pose arrival without delaying or swallowing the triggering interaction. Both values are named and controller-injectable; visual or usage evidence can revise them later without changing authority.

Interaction set: pointer-down, key-down, wheel, and input are user-presence edges. Product emotes, directed travel/return, drag, hidden documents, reduced motion, and arcade leases make the lifecycle ineligible. Background research progress, animation frames, pointer sampling, and visibility restoration do not fabricate presence or waking.

Accessibility: the mascot remains one project button with its existing label, focus, click, double-click, drag, and navigation semantics. Sleep and wake are decorative and `aria-hidden`. Reduced motion disables the episode and preserves the static neutral control.

Rejected: the finite sleeping emote, route-owned sleep, direct raster imports, cross-reload persistence, and treating machine work as user presence.
