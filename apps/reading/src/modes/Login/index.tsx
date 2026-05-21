import { useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import wernerDefault from "../../brand/werner/poses/anchor/werner_default_v5_nano_corrected.png";
import { LemonButton, LemonInput } from "../../components/lemon";
import { requestMagicLink, useAuth } from "../../lib/auth";

/**
 * Login surface — Antiek's owned login page (H6 ship, 2026-05-21
 * PostHog-style auth decision; reskinned to the Werner / Antarctic
 * brand from the May-21 redesign).
 *
 * Visual identity:
 *   - Day mode = ice-2 page, ice-0 card, sun-yellow border, ink shadow
 *   - Night mode = space-2 page, charcoal-2 card, sun-yellow border, sun-deep shadow
 *   - Werner the penguin mark at the top (mark-180, round)
 *   - Headline in Charter serif (font-serif); subhead in Inter (font-sans)
 *   - LemonInput + LemonButton primary (sun fill)
 *
 * Flow:
 *   1. User lands here (typed /login or redirected by RequireAuth)
 *   2. Enters email → POST /auth/request
 *   3. MockEmailProvider (dev) or Resend (prod) delivers a magic link
 *   4. Click → /auth/callback?token=… → 302 back to `next` with
 *      ANTIEK_SESSION cookie set
 */
export default function Login() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { state } = useAuth();

  // Already signed in? Bounce to the destination.
  if (state.status === "authenticated") {
    const dest = searchParams.get("next") ?? "/";
    navigate(dest, { replace: true });
  }

  const nextPath =
    searchParams.get("next") ??
    (location.state as { from?: string } | null)?.from ??
    "/";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setStatus("sending");
    setErrorMsg("");
    const result = await requestMagicLink(email, nextPath);
    if (result.kind === "sent") {
      setStatus("sent");
    } else {
      setStatus("error");
      setErrorMsg(result.message);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 px-4 font-sans">
      <div className="w-full max-w-md">
        {/* Werner mark + wordmark */}
        <div className="flex flex-col items-center mb-7">
          <img
            src={wernerDefault}
            alt="Werner"
            width={88}
            height={88}
            className="rounded-full border-edge border-sun shadow-z2 dark:shadow-z2-night bg-ice-0 dark:bg-charcoal-2"
          />
          <div
            className="mt-4 text-[26px] leading-none font-semibold tracking-tight text-ink dark:text-bright font-serif"
          >
            Antiek
          </div>
          <div className="mt-2 text-[11px] tracking-[0.18em] uppercase text-shadow-1 dark:text-moonlight">
            Research workstation
          </div>
        </div>

        {/* Card */}
        <div
          className="bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog-lg shadow-z2 dark:shadow-z2-night p-7"
        >
          {status === "sent" ? (
            <div className="text-center">
              <h1 className="text-[22px] font-semibold text-ink dark:text-bright mb-2 font-serif">
                Check your email
              </h1>
              <p className="text-[13px] text-shadow-2 dark:text-starlight leading-relaxed">
                We sent a sign-in link to{" "}
                <span className="font-semibold text-ink dark:text-bright">{email}</span>.
                The link expires in 15 minutes.
              </p>
              <button
                type="button"
                className="mt-6 text-[11px] tracking-wider uppercase text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright underline decoration-sun underline-offset-4 decoration-2"
                onClick={() => {
                  setStatus("idle");
                  setEmail("");
                }}
              >
                Use a different email
              </button>
            </div>
          ) : (
            <>
              <h1 className="text-[22px] font-semibold text-ink dark:text-bright mb-1 font-serif">
                Sign in
              </h1>
              <p className="text-[13px] text-shadow-2 dark:text-starlight mb-5">
                We'll email you a sign-in link. No password to remember.
              </p>
              <form onSubmit={onSubmit} className="space-y-4">
                <label className="block">
                  <span className="block text-[11px] font-semibold tracking-wider uppercase text-shadow-1 dark:text-moonlight mb-1.5">
                    Email
                  </span>
                  <LemonInput
                    type="email"
                    autoFocus
                    autoComplete="email"
                    required
                    disabled={status === "sending"}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    sizing="lg"
                    wrapperClassName="w-full"
                  />
                </label>
                <LemonButton
                  type="submit"
                  variant="primary"
                  size="lg"
                  fullWidth
                  disabled={status === "sending" || !email}
                >
                  {status === "sending" ? "Sending…" : "Send sign-in link"}
                </LemonButton>
                {status === "error" && (
                  <p className="text-[12px] text-emperor mt-1">{errorMsg}</p>
                )}
              </form>
            </>
          )}
        </div>

        <p className="text-center text-[11px] text-shadow-1 dark:text-moonlight mt-6 leading-relaxed">
          By signing in you agree to Antiek's research-use terms.{" "}
          <a
            href="/trust"
            className="text-ink dark:text-bright underline decoration-sun underline-offset-4 decoration-2 hover:bg-sun/20 px-0.5"
          >
            Trust Center
          </a>
          .
        </p>
      </div>
    </div>
  );
}
