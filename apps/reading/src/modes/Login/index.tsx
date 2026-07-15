import { startAuthentication, startRegistration } from "@simplewebauthn/browser";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import Werner from "../../brand/Werner";
import { LemonButton, LemonInput } from "../../components/lemon";
import {
  approveLogin,
  authCallbackErrorDisplay,
  authLoginErrorDisplay,
  beginPasskeyLogin,
  beginPasskeyRegistration,
  claimLogin,
  finishPasskeyLogin,
  finishPasskeyRegistration,
  getPasskeyStatus,
  requestMagicLink,
  useAuth,
} from "../../lib/auth";
import { track, trackException } from "../../lib/analytics";
import type { AuthDiagnosticCode } from "../../lib/authDiagnosticCodes";

import "./Login.css";

type EmailStatus = "idle" | "sending" | "sent" | "approved" | "expired" | "error";
type PasskeyState = "checking" | "ready" | "absent" | "working" | "error";

function isPasskeyCancellation(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "AbortError");
}

function deviceLabel(): string {
  const ua = navigator.userAgent;
  if (/iPad/i.test(ua)) return "this iPad";
  if (/iPhone/i.test(ua)) return "this iPhone";
  if (/Mac/i.test(ua)) return "this Mac";
  return "this device";
}

function PasskeyMark({ active = false }: { active?: boolean }) {
  return (
    <span className="passkey-mark" data-active={active || undefined} aria-hidden="true">
      <span className="passkey-mark__arc passkey-mark__arc--one" />
      <span className="passkey-mark__arc passkey-mark__arc--two" />
      <span className="passkey-mark__stem" />
    </span>
  );
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [emailStatus, setEmailStatus] = useState<EmailStatus>("idle");
  const [passkeyState, setPasskeyState] = useState<PasskeyState>("checking");
  const [errorMsg, setErrorMsg] = useState("");
  const [errorHint, setErrorHint] = useState<string | null>(null);
  const [diagnosticCode, setDiagnosticCode] = useState<AuthDiagnosticCode | null>(null);
  const [handoff, setHandoff] = useState<{
    attemptId: string;
    claimSecret: string;
    deviceCode: string;
  } | null>(null);
  const [approvalWorking, setApprovalWorking] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { state, refresh } = useAuth();
  const isSetup = searchParams.get("setup") === "passkey";
  const approvalAttempt = searchParams.get("approve");
  const approvalCode = searchParams.get("code");
  const nextPath = useMemo(
    () =>
      searchParams.get("next") ??
      (location.state as { from?: string } | null)?.from ??
      "/",
    [location.state, searchParams],
  );

  useEffect(() => {
    if (state.status === "authenticated" && !isSetup && !approvalAttempt) {
      navigate(nextPath, { replace: true });
    }
  }, [approvalAttempt, isSetup, navigate, nextPath, state.status]);

  useEffect(() => {
    if (isSetup || approvalAttempt) return;
    let live = true;
    void getPasskeyStatus()
      .then(({ available }) => {
        if (live) setPasskeyState(available ? "ready" : "absent");
      })
      .catch(() => {
        if (live) setPasskeyState("absent");
      });
    return () => {
      live = false;
    };
  }, [approvalAttempt, isSetup]);

  useEffect(() => {
    const callbackError = searchParams.get("error");
    const display = authCallbackErrorDisplay(callbackError);
    if (!display) return;
    setEmailStatus("error");
    setErrorMsg(display.message);
    setErrorHint(display.hint);
    setDiagnosticCode(
      callbackError === "magic_link_expired"
        ? "B-POLICY-CALLBACK-EXPIRED"
        : callbackError === "magic_link_invalid"
          ? "B-POLICY-CALLBACK-INVALID"
          : callbackError === "not_authorized"
            ? "B-POLICY-CALLBACK-NOT-AUTH"
            : null,
    );
    const clean = new URLSearchParams(searchParams);
    clean.delete("error");
    navigate({ pathname: "/login", search: clean.toString() ? `?${clean}` : "" }, { replace: true });
  }, [navigate, searchParams]);

  useEffect(() => {
    if (!handoff || emailStatus !== "sent") return;
    let live = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const result = await claimLogin(handoff.attemptId, handoff.claimSecret);
        if (!live) return;
        if (result.status === "authenticated") {
          setEmailStatus("approved");
          await refresh();
          navigate(
            result.setup_passkey
              ? `/login?setup=passkey&next=${encodeURIComponent(result.next)}`
              : result.next,
            { replace: true },
          );
          return;
        }
        if (result.status === "expired") {
          setEmailStatus("expired");
          setErrorMsg("That handoff melted away.");
          setErrorHint("Send a fresh one and leave this screen open.");
          return;
        }
      } catch {
        // A brief network interruption must not cancel a valid handoff.
      }
      if (live) timer = window.setTimeout(poll, 1800);
    };
    void poll();
    return () => {
      live = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [emailStatus, handoff, navigate, refresh]);

  async function unlockWithPasskey() {
    if (passkeyState === "working") return;
    setPasskeyState("working");
    setErrorMsg("");
    setErrorHint(null);
    track("passkey_login_started");
    try {
      const { ceremony_id, ...optionsJSON } = await beginPasskeyLogin();
      const credential = await startAuthentication({ optionsJSON });
      await finishPasskeyLogin(ceremony_id, credential);
      await refresh();
      track("passkey_login_succeeded");
      navigate(nextPath, { replace: true });
    } catch (error) {
      if (isPasskeyCancellation(error)) {
        setPasskeyState("ready");
        return;
      }
      const message = error instanceof Error ? error.message : "That passkey didn't unlock Antiek.";
      setErrorMsg(message);
      setErrorHint("Try again, use a nearby device, or recover with email.");
      setPasskeyState("error");
      trackException(error instanceof Error ? error : new Error(message));
    }
  }

  async function savePasskey() {
    if (passkeyState === "working") return;
    setPasskeyState("working");
    setErrorMsg("");
    try {
      const { ceremony_id, ...optionsJSON } = await beginPasskeyRegistration();
      const credential = await startRegistration({ optionsJSON });
      await finishPasskeyRegistration(ceremony_id, credential, deviceLabel());
      track("passkey_registered");
      setPasskeyState("ready");
      navigate(nextPath, { replace: true });
    } catch (error) {
      if (isPasskeyCancellation(error)) {
        setPasskeyState("absent");
        return;
      }
      const message = error instanceof Error ? error.message : "Antiek couldn't save that passkey.";
      setErrorMsg(message);
      setErrorHint("Your email sign-in is still active. You can try again safely.");
      setPasskeyState("error");
      trackException(error instanceof Error ? error : new Error(message));
    }
  }

  async function onEmailSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!email) return;
    setEmailStatus("sending");
    setErrorMsg("");
    setErrorHint(null);
    setDiagnosticCode(null);
    track("login_requested");
    const result = await requestMagicLink(email, nextPath);
    if (result.kind === "sent") {
      setHandoff({
        attemptId: result.attempt_id,
        claimSecret: result.claim_secret,
        deviceCode: result.device_code,
      });
      setEmailStatus("sent");
      track("login_link_sent");
      return;
    }
    const display = authLoginErrorDisplay(result);
    setEmailStatus("error");
    setErrorMsg(display.message);
    setErrorHint(display.hint);
    setDiagnosticCode(result.diagnostic_code);
    trackException(new Error(`Magic link failed: ${display.message}`));
  }

  async function approveHandoff() {
    if (!approvalAttempt || approvalWorking) return;
    setApprovalWorking(true);
    setErrorMsg("");
    try {
      await approveLogin(approvalAttempt);
      navigate("/login?approved=1", { replace: true });
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : "This device handoff has expired.");
      setApprovalWorking(false);
    }
  }

  if (approvalAttempt) {
    return (
      <ReceiptShell>
        <section className="handoff-receipt" aria-labelledby="handoff-title">
          <Werner mood="idle" size={92} label="Werner checking the matching code" className="handoff-receipt__werner" />
          <div className="antiek-login__eyebrow"><span /> Tiny security check</div>
          <h1 id="handoff-title">Same four digits?</h1>
          <p className="handoff-code" aria-label={`Device code ${approvalCode}`}>{approvalCode}</p>
          <p>Approve only if the computer or iPad where you started shows this exact code.</p>
          <button
            type="button"
            className="antiek-login__primary"
            onClick={() => void approveHandoff()}
            disabled={approvalWorking}
          >
            <span className="approval-tick" aria-hidden="true">✓</span>
            <span>
              <strong>{approvalWorking ? "Carrying the yes…" : "Yes, open that screen"}</strong>
              <small>One-time approval · expires in 15 minutes</small>
            </span>
            <span className="antiek-login__arrow" aria-hidden="true">→</span>
          </button>
          {errorMsg && <ErrorNotice message={errorMsg} />}
        </section>
      </ReceiptShell>
    );
  }

  if (searchParams.get("approved") === "1") {
    return (
      <ReceiptShell>
        <section className="handoff-receipt handoff-receipt--approved" role="status">
          <Werner mood="idle" size={110} label="Werner celebrating the approved sign-in" className="handoff-receipt__werner" />
          <span className="handoff-receipt__stamp">Approved</span>
          <div className="antiek-login__eyebrow"><span /> Delivery complete</div>
          <h1>Your other screen is opening.</h1>
          <p>Werner carried the yes back. You can close this page.</p>
        </section>
      </ReceiptShell>
    );
  }

  const showPasskeyFirst = passkeyState !== "absent" && passkeyState !== "checking";
  const setupReady = isSetup && state.status === "authenticated";

  return (
    <main className="antiek-login" data-passkey-state={passkeyState}>
      <div className="antiek-login__grain" aria-hidden="true" />
      <section className="antiek-login__desk" aria-label="Antiek sign in">
        <header className="antiek-login__brand">
          <span className="antiek-login__wordmark">Antiek</span>
          <span className="antiek-login__edition">Private research workstation</span>
        </header>

        <div className="antiek-login__card">
          {setupReady ? (
            <>
              <Eyebrow>One last step</Eyebrow>
              <h1>Leave email behind.</h1>
              <p className="antiek-login__lede">Save a passkey now. Next time, Antiek opens with Face ID, Touch ID, or your device PIN.</p>
              <ActionButton
                busy={passkeyState === "working"}
                title={passkeyState === "working" ? "Saving passkey…" : `Save to ${deviceLabel()}`}
                detail="Encrypted and synced by your device"
                onClick={() => void savePasskey()}
              />
              {errorMsg && <ErrorNotice message={errorMsg} hint={errorHint} />}
              <button className="antiek-login__quiet" type="button" onClick={() => navigate(nextPath, { replace: true })}>Do this later</button>
            </>
          ) : showPasskeyFirst ? (
            <>
              <Eyebrow>Welcome back</Eyebrow>
              <h1>Pick up the thread.</h1>
              <p className="antiek-login__lede">Your workstation is exactly where you left it.</p>
              <ActionButton
                busy={passkeyState === "working"}
                title={passkeyState === "working" ? "Unlocking…" : "Unlock with passkey"}
                detail="Face ID, Touch ID, or a nearby device"
                onClick={() => void unlockWithPasskey()}
              />
              {(passkeyState === "error" || errorMsg) && <ErrorNotice message={errorMsg} hint={errorHint} />}
              <details className="antiek-login__recovery">
                <summary>Use email recovery</summary>
                <EmailForm email={email} setEmail={setEmail} status={emailStatus} onSubmit={onEmailSubmit} errorMsg={emailStatus === "error" ? errorMsg : ""} errorHint={emailStatus === "error" ? errorHint : null} diagnosticCode={diagnosticCode} />
              </details>
            </>
          ) : emailStatus === "sent" ? (
            <div className="antiek-login__sent" role="status">
              <Eyebrow>Werner is waiting</Eyebrow>
              <h1>Now check your phone.</h1>
              <p className="antiek-login__lede">Open the message sent to <strong>{email}</strong>. Approve it there; this screen will open itself.</p>
              <div className="handoff-code handoff-code--desk" aria-label={`Device code ${handoff?.deviceCode}`}>
                <small>Match this code on your phone</small>
                <strong>{handoff?.deviceCode}</strong>
              </div>
              <HandoffSteps />
              {(emailStatus as EmailStatus) === "expired" && <ErrorNotice message={errorMsg} hint={errorHint} />}
              <button type="button" className="antiek-login__quiet" onClick={() => { setEmailStatus("idle"); setHandoff(null); }}>Use a different email</button>
            </div>
          ) : (
            <>
              <Eyebrow>First unlock</Eyebrow>
              <h1>Open your desk.</h1>
              <p className="antiek-login__lede">Start here, approve on your phone. This screen opens itself. No link gymnastics.</p>
              <EmailForm email={email} setEmail={setEmail} status={emailStatus} onSubmit={onEmailSubmit} errorMsg={errorMsg} errorHint={errorHint} diagnosticCode={diagnosticCode} />
            </>
          )}
        </div>

        <footer className="antiek-login__footer">
          <span>Private by default</span><span aria-hidden="true">·</span><a href="/trust">How Antiek protects your work</a>
        </footer>
      </section>

      <aside className="antiek-login__trail" aria-label="Werner explains the secure device handoff">
        <div className="handoff-world">
          <p className="handoff-world__tag">ANTIEK ACCESS DESK · SIGNAL CLEAR</p>
          <div className="handoff-world__bubble">I’ll carry the yes back.</div>
          <div className="handoff-world__werner" data-waiting={emailStatus === "sent" || undefined}>
            <Werner mood="idle" size={184} label="Werner, Antiek's penguin guide" />
            <span className="handoff-world__thinking" aria-hidden="true"><i /><i /><i /></span>
            <span className="handoff-world__ticket" aria-hidden="true">YES</span>
          </div>
          <HandoffSteps scenic />
          <p className="handoff-world__note">The email moves.<br />Your research stays put.</p>
        </div>
      </aside>
    </main>
  );
}

function ReceiptShell({ children }: { children: React.ReactNode }) {
  return <main className="antiek-login antiek-login--receipt"><div className="antiek-login__grain" aria-hidden="true" />{children}</main>;
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="antiek-login__eyebrow"><span /> {children}</div>;
}

function ActionButton({ busy, title, detail, onClick }: { busy: boolean; title: string; detail: string; onClick: () => void }) {
  return (
    <button type="button" className="antiek-login__primary" onClick={onClick} disabled={busy}>
      <PasskeyMark active={busy} />
      <span><strong>{title}</strong><small>{detail}</small></span>
      <span className="antiek-login__arrow" aria-hidden="true">→</span>
    </button>
  );
}

function HandoffSteps({ scenic = false }: { scenic?: boolean }) {
  return (
    <div className={scenic ? "handoff-ticket handoff-ticket--scenic" : "handoff-ticket"} aria-label="Sign-in handoff: request here, approve on phone, then this screen opens">
      <div><small>01 · REQUEST</small><strong>This screen</strong></div>
      <span className="handoff-ticket__route" aria-hidden="true"><i /><i /><i /></span>
      <div><small>02 · APPROVE</small><strong>Your phone</strong></div>
      <span className="handoff-ticket__route" aria-hidden="true"><i /><i /><i /></span>
      <div><small>03 · OPEN</small><strong>Automatically</strong></div>
    </div>
  );
}

function ErrorNotice({ message, hint, diagnosticCode }: { message: string; hint?: string | null; diagnosticCode?: AuthDiagnosticCode | null }) {
  return <div className="antiek-login__error" role="alert" data-auth-diagnostic={diagnosticCode ?? undefined}><strong>{message}</strong>{hint && <span>{hint}</span>}</div>;
}

interface EmailFormProps {
  email: string;
  setEmail: (value: string) => void;
  status: EmailStatus;
  onSubmit: (event: React.FormEvent) => void;
  errorMsg: string;
  errorHint: string | null;
  diagnosticCode: AuthDiagnosticCode | null;
}

function EmailForm({ email, setEmail, status, onSubmit, errorMsg, errorHint, diagnosticCode }: EmailFormProps) {
  return (
    <form onSubmit={onSubmit} className="antiek-login__form">
      <label>
        <span>Email</span>
        <LemonInput type="email" autoFocus autoComplete="email" required disabled={status === "sending"} value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" sizing="lg" wrapperClassName="w-full" />
      </label>
      <LemonButton type="submit" variant="primary" size="lg" fullWidth disabled={status === "sending" || !email}>
        {status === "sending" ? "Sending secure link…" : "Continue with email"}
      </LemonButton>
      {status === "error" && errorMsg && <ErrorNotice message={errorMsg} hint={errorHint} diagnosticCode={diagnosticCode} />}
    </form>
  );
}
