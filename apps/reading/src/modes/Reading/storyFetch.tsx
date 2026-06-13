import { useEffect } from "react";
import type { Decorator } from "@storybook/react";

/**
 * storyFetch — deterministic `window.fetch` control for reading-mode stories
 * (ALC SPR-09, product-character lift).
 *
 * The reading-mode stateful surfaces (ResearchThis, VoiceNote, PersonalSpace,
 * MetaReading) drive their loading / empty / error / saved states from their
 * OWN internal code path: a real `fetch` through `apiFetch`, plus internal
 * `useState` transitions. To author a NAMED Storybook story PER non-default
 * state — the rubric's level-3 criterion (Dimension 3) — without changing one
 * line of runtime behaviour, each story installs a controlled `fetch` so the
 * component genuinely transitions into the state being inspected. The component
 * runs its real reducer; only the network is pinned. This is more honest than
 * faking the rendered markup: the state on screen is the state the code reaches.
 *
 * Three primitives:
 *   - `stubFetch(handler)` — a story-scoped fetch decorator. The handler maps a
 *     URL to a `Response` (or rejects). Restored on unmount so stories don't
 *     leak into each other.
 *   - `pendingForever` — a fetch that never settles, used to PIN a transient
 *     in-flight state (busy / loading / transcribing / saving) so it is
 *     inspectable in isolation rather than flashing past.
 *   - `json(body, status)` / `httpError(status)` — Response builders.
 *
 * No MSW dependency is added (the repo has none); this is a plain global stub,
 * the same lever the existing reading components already lean on (their docs say
 * "Storybook has no backend, so this surfaces the graceful error").
 */

type FetchHandler = (
  url: string,
  init?: RequestInit,
) => Response | Promise<Response>;

/** A Response that never resolves — pins a transient in-flight state. */
export const pendingForever: FetchHandler = () => new Promise<Response>(() => {});

/** Build a JSON Response. */
export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build an HTTP error Response (empty body — the components read status). */
export function httpError(status: number): Response {
  return new Response("", { status });
}

/**
 * A story decorator that installs a controlled `window.fetch` for the lifetime
 * of the story and restores the original on unmount. Returning a never-settling
 * promise (`pendingForever`) pins a transient state for inspection.
 */
export function stubFetch(handler: FetchHandler): Decorator {
  const Decorated: Decorator = (Story) => {
    useEffect(() => {
      const original = window.fetch;
      window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;
        return Promise.resolve(handler(url, init));
      }) as typeof window.fetch;
      return () => {
        window.fetch = original;
      };
    }, []);
    return <Story />;
  };
  return Decorated;
}

/**
 * A story decorator that installs a synchronous MediaRecorder + getUserMedia
 * stub for the story's lifetime, so VoiceNote's REAL `useVoiceRecorder` hook
 * can produce a recorded blob WITHOUT a microphone. This lets a story drive the
 * component through its actual record → stop → transcribe phases (the real
 * reducer), with `fetch` (above) controlling the transcribe/save responses.
 * Nothing in VoiceNote is mocked — only the browser's mic + recorder APIs are.
 */
export function stubRecorder(): Decorator {
  const Decorated: Decorator = (Story) => {
    useEffect(() => {
      const nav = navigator as unknown as { mediaDevices?: { getUserMedia?: unknown } };
      const originalMedia = nav.mediaDevices;
      const OriginalRecorder = (window as unknown as { MediaRecorder?: unknown }).MediaRecorder;

      class FakeRecorder {
        ondataavailable: ((e: { data: Blob }) => void) | null = null;
        onstop: (() => void) | null = null;
        state: "inactive" | "recording" = "inactive";
        mimeType = "audio/webm";
        start() {
          this.state = "recording";
        }
        stop() {
          this.state = "inactive";
          this.ondataavailable?.({ data: new Blob(["audio"], { type: "audio/webm" }) });
          this.onstop?.();
        }
      }

      nav.mediaDevices = {
        ...(originalMedia ?? {}),
        getUserMedia: async () => ({ getTracks: () => [] }) as unknown as MediaStream,
      } as MediaDevices;
      (window as unknown as { MediaRecorder: unknown }).MediaRecorder =
        FakeRecorder as unknown as typeof MediaRecorder;

      return () => {
        nav.mediaDevices = originalMedia as MediaDevices;
        (window as unknown as { MediaRecorder: unknown }).MediaRecorder = OriginalRecorder;
      };
    }, []);
    return <Story />;
  };
  return Decorated;
}
