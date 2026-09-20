# Werner arcade cursor handoff — Cycle 567

Status: verified for stacked transport.

## Decision

The route-derived station instrument remains deterministic until a focused
product surface explicitly owns pointer input. Paperclip Zombies is the first
such case: its playing state temporarily suspends global cursor chrome, returns
the native cursor to the canvas, and releases that authority on every teardown.

## Why a lease

A persisted activity override would create a second routing authority and could
strand the wrong cursor after navigation. The process-local suspension seam
instead issues idempotent leases. Overlapping owners cannot restore the global
instrument until the final lease releases; no owner can choose another activity
or move Werner.

## Lifecycle

Waiting and offer do nothing. The playing commit acquires in a layout effect so
the research lens cannot paint over the game. Exit, Escape, episode replacement,
terminal removal, and unmount all run the same effect cleanup. The shell combines
the lease with its existing feature-flag and reduced-motion policy, which also
removes the hidden-native-cursor root class.

## Proof

Unit proof covers overlapping leases and idempotent release. Shell proof covers
instrument removal, native-cursor restoration, and route-instrument recovery.
Wait-host proof covers Play, both voluntary exits, episode reset, and terminal
unmount. Storybook shows the offer and playing ownership states without a
production bypass.

## Deferred

This does not add a general operator override or new game cursor artwork. Those
require independent user need and visual authority; the canvas-native control is
the honest current game instrument.
