#!/usr/bin/env bash
# Branding densify pack — invent reframe + living-TV + arcade + product invent doors.
# Expectation (product-door + mini-game densify wave): 47 files / 405 tests. Exit non-zero on any failure.
# Invoke: npm run test:branding-densify   (from apps/reading)
#         or bash scripts/branding-densify-pack.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec npm test -- --run \
  src/components/ModelDecisionBar.test.tsx \
  src/modes/Sources/Sources.brand.test.tsx \
  src/modes/DeepResearchWorkspace/ResearchWaitArcadeGame.test.tsx \
  src/modes/Write/SubAgentProposal.test.tsx \
  src/modes/Reading/HouseSlot.test.tsx \
  src/modes/DeepResearchWorkspace/ResearchWaitArcade.test.tsx \
  src/brand/werner/sessionAssets.integrity.test.ts \
  src/arcade/ArcadeCabinet.test.tsx \
  src/arcade/host/LoadingGameHost.playing.test.tsx \
  src/modes/Home/Home.test.tsx \
  src/modes/shared/FloatMenu/FloatMenu.test.tsx \
  src/arcade/host/LoadingGameHost.test.tsx \
  src/brand/SessionBrandChrome.doors.test.tsx \
  src/brand/SessionBrandChrome.test.tsx \
  src/brand/sessionLivingTv.test.tsx \
  src/brand/werner/sessionSceneWebp.integrity.test.ts \
  src/brand/werner/sessionAssets.test.tsx \
  src/arcade/arcadeBoundary.test.ts \
  src/modes/BrainstormStation/ThoughtPartnerPanel.test.tsx \
  src/shell/PenguinMascot.reactions.test.tsx \
  src/werner/livingTvAmbient.test.ts \
  src/modes/DeepResearchWorkspace/DeepResearchWorkspace.waitArcade.test.tsx \
  src/werner/reactionBus.test.ts \
  src/werner/activities/registry.test.ts \
  src/arcade/cartridgeFactory.test.ts \
  src/werner/emoteForProductDoor.test.ts \
  src/modes/DeepResearchWorkspace/researchWaitArcadePolicy.test.ts \
  src/modes/Settings/AntiekBenchPanel.test.tsx \
  src/arcade/games/ice-fishing/logic.test.ts \
  src/arcade/games/ice-fishing/visuals.test.ts \
  src/arcade/games/clam-catcher/logic.test.ts \
  src/arcade/games/clam-catcher/visuals.test.ts \
  src/arcade/games/zombies/logic.test.ts \
  src/arcade/games/zombies/zombiesVisuals.test.ts \
  src/arcade/games/zombies/zombiesCartridge.test.ts \
  src/werner/WernerIceBait.test.tsx \
  src/werner/fishingLineGeometry.test.ts \
  src/werner/instrumentBarrel.densify.test.ts \
  src/werner/productSelector.densify.test.ts \
  src/werner/wernerTargetAttr.densify.test.ts \
  src/werner/stationInstrumentSuspension.test.tsx \
  src/werner/useMouseFollow.test.ts \
  src/werner/WernerIceCursorShell.transition.test.tsx \
  src/brand/flipbookStreamLadder.densify.test.ts \
  src/brand/inventProductInventory.densify.test.ts \
  src/brand/inventClassProductMap.densify.test.ts \
  src/brand/inventPolishWaveHonesty.densify.test.ts
