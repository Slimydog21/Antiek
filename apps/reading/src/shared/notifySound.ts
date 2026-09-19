/**
 * notifySound.ts — the sound visibility channel (herdr transfer P1).
 *
 * herdr plays a sound when an agent needs attention, suppressed while you
 * are watching it (src/app/actions.rs:59-64). The web equivalent: two short
 * synthesized tones (Web Audio — zero assets, zero network) fired only on
 * REAL state transitions observed from the event stream. The suppression
 * rule is what keeps a notification channel welcome; the mute switch lives
 * in Settings (localStorage-backed, versioned key).
 *
 * Pure module, no React: the hook that watches transitions lives in
 * hooks/useResearchNotifications.ts.
 */

const MUTE_KEY = "antiek:sound_muted:v1";

export function isSoundMuted(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setSoundMuted(muted: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (muted) window.localStorage.setItem(MUTE_KEY, "1");
    else window.localStorage.removeItem(MUTE_KEY);
  } catch {
    // Private mode — the mute choice degrades to unmuted; the chime is
    // quiet and local, so this is the safe direction.
  }
}

let _ctx: AudioContext | null = null;

function ctx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    if (!_ctx) {
      const AC =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AC) return null;
      _ctx = new AC();
    }
    if (_ctx.state === "suspended") void _ctx.resume();
    return _ctx;
  } catch {
    return null;
  }
}

function chime(notes: { freq: number; start: number; dur: number }[]): void {
  if (isSoundMuted()) return;
  const c = ctx();
  if (!c) return;
  for (const n of notes) {
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sine";
    osc.frequency.value = n.freq;
    const t0 = c.currentTime + n.start;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.08, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + n.dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + n.dur + 0.02);
  }
}

/** A research completed — a soft two-note rise (E5 → A5). */
export function playResearchDone(): void {
  chime([
    { freq: 659.25, start: 0, dur: 0.18 },
    { freq: 880.0, start: 0.12, dur: 0.3 },
  ]);
}

/** A research needs attention (failed) — a two-note fall (A5 → E5). */
export function playResearchAttention(): void {
  chime([
    { freq: 880.0, start: 0, dur: 0.18 },
    { freq: 659.25, start: 0.12, dur: 0.34 },
  ]);
}
