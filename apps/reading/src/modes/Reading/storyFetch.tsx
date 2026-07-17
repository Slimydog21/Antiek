import { useEffect, useLayoutEffect, type ReactNode } from "react";
import type { Decorator } from "@storybook/react";

type FetchHandler = (
  url: string,
  init?: RequestInit,
) => Response | Promise<Response>;

export const pendingForever: FetchHandler = () => new Promise<Response>(() => {});

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function httpError(status: number): Response {
  return new Response("", { status });
}

export function stubFetch(handler: FetchHandler): Decorator {
  function FetchStub({ children }: { children: ReactNode }) {
    useLayoutEffect(() => {
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
    return children;
  }
  const Decorated: Decorator = (Story) => <FetchStub><Story /></FetchStub>;
  return Decorated;
}

export function stubRecorder(): Decorator {
  const Decorated: Decorator = (Story) => {
    useEffect(() => {
      const nav = navigator as unknown as {
        mediaDevices?: Partial<MediaDevices>;
      };
      const originalMedia = nav.mediaDevices;
      const win = window as unknown as { MediaRecorder?: typeof MediaRecorder };
      const OriginalRecorder = win.MediaRecorder;

      class FakeRecorder {
        ondataavailable: ((event: { data: Blob }) => void) | null = null;
        onstop: (() => void) | null = null;
        state: "inactive" | "recording" = "inactive";
        mimeType = "audio/webm";

        start() {
          this.state = "recording";
        }

        stop() {
          this.state = "inactive";
          this.ondataavailable?.({
            data: new Blob(["audio"], { type: "audio/webm" }),
          });
          this.onstop?.();
        }
      }

      nav.mediaDevices = {
        ...(originalMedia ?? {}),
        getUserMedia: async () => ({ getTracks: () => [] }) as unknown as MediaStream,
      };
      win.MediaRecorder = FakeRecorder as unknown as typeof MediaRecorder;

      return () => {
        nav.mediaDevices = originalMedia;
        win.MediaRecorder = OriginalRecorder;
      };
    }, []);
    return <Story />;
  };
  return Decorated;
}
