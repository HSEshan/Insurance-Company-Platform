import { useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getErrorMessage } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Alert, Badge, Button, Card, Field, Input, Notice } from "../../components/ui";
import { SimulatedCodeNotice } from "./SimulatedCodeNotice";
import type {
  CodeDispatch,
  Envelope,
  MfaMethod,
  RecoveryCodesResult,
  SecurityStatus,
  TotpSetup,
  User,
} from "../../types";

const STATUS_KEY = ["security-status"];

const METHOD_LABELS: Record<MfaMethod, string> = {
  totp: "Authenticator app",
  email: "Email code",
  sms: "Text message (SMS)",
};

const METHOD_HINTS: Record<MfaMethod, string> = {
  totp: "Google Authenticator, Microsoft Authenticator, 1Password, Authy, etc. Recommended.",
  email: "We email you a 6-digit code each time you sign in. Requires a verified email.",
  sms: "We text you a 6-digit code each time you sign in. Requires a verified phone.",
};

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
      {children}
    </h3>
  );
}

export function SecurityPage() {
  const queryClient = useQueryClient();
  const setUser = useAuthStore((s) => s.setUser);

  const { data: status, isLoading, isError } = useQuery({
    queryKey: STATUS_KEY,
    queryFn: async () => {
      const res = await api.get<Envelope<SecurityStatus>>("/auth/security");
      return res.data.data!;
    },
  });

  async function applyStatus(next: SecurityStatus) {
    queryClient.setQueryData(STATUS_KEY, next);
    // Keep the cached user (phone, verification flags) in step with the server.
    try {
      const res = await api.get<Envelope<User>>("/auth/me");
      if (res.data.data) setUser(res.data.data);
    } catch {
      // Non-fatal: the status card is already current.
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Security</h2>
        <p className="text-sm text-slate-500">
          Verify your contact details and protect your account with two-factor
          authentication (2FA).
        </p>
      </div>
      {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
      {isError && <Alert message="Could not load your security settings." />}
      {status && (
        <>
          <ContactVerificationCard status={status} onChange={applyStatus} />
          <TwoFactorCard status={status} onChange={applyStatus} />
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Contact verification                                                        //
// --------------------------------------------------------------------------- //
function ContactVerificationCard({
  status,
  onChange,
}: {
  status: SecurityStatus;
  onChange: (s: SecurityStatus) => void;
}) {
  const [phone, setPhone] = useState(status.phone ?? "");
  const phoneChanged = phone.trim() !== "" && phone.trim() !== (status.phone ?? "");

  return (
    <Card>
      <SectionTitle>Contact verification</SectionTitle>
      <div className="space-y-5">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 text-sm">
            <div>
              <p className="text-slate-500">Email</p>
              <p className="font-medium text-slate-800">{status.email}</p>
            </div>
            <Badge value={status.email_verified ? "verified" : "not_verified"} />
          </div>
          {!status.email_verified && (
            <CodeVerifier
              idPrefix="email"
              sendLabel="Send verification code"
              onSend={async () => {
                const res = await api.post<Envelope<CodeDispatch>>("/auth/verify/email/send");
                return res.data.data!;
              }}
              onConfirm={async (code) => {
                const res = await api.post<Envelope<SecurityStatus>>(
                  "/auth/verify/email/confirm",
                  { code },
                );
                onChange(res.data.data!);
              }}
            />
          )}
        </div>

        <div className="space-y-2 border-t border-slate-100 pt-4">
          <div className="flex items-center justify-between gap-2 text-sm">
            <p className="text-slate-500">Phone</p>
            <Badge
              value={status.phone && status.phone_verified ? "verified" : "not_verified"}
            />
          </div>
          <Field label="Mobile number" htmlFor="phone">
            <Input
              id="phone"
              type="tel"
              autoComplete="tel"
              placeholder="(555) 123-4567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={status.mfa_method === "sms"}
            />
          </Field>
          {status.mfa_method === "sms" && (
            <p className="text-xs text-slate-500">
              This number receives your sign-in codes. Switch 2FA methods to change it.
            </p>
          )}
          {(phoneChanged || (status.phone && !status.phone_verified)) && (
            <CodeVerifier
              key={phoneChanged ? phone : "current"}
              idPrefix="phone"
              sendLabel={phoneChanged ? "Verify new number" : "Send verification code"}
              onSend={async () => {
                const res = await api.post<Envelope<CodeDispatch>>("/auth/verify/phone/send", {
                  phone: phoneChanged ? phone.trim() : null,
                });
                return res.data.data!;
              }}
              onConfirm={async (code) => {
                const res = await api.post<Envelope<SecurityStatus>>(
                  "/auth/verify/phone/confirm",
                  { code },
                );
                const next = res.data.data!;
                setPhone(next.phone ?? "");
                onChange(next);
              }}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

/** Send a code, then confirm it. Shared by email and phone verification. */
function CodeVerifier({
  idPrefix,
  sendLabel,
  onSend,
  onConfirm,
}: {
  idPrefix: string;
  sendLabel: string;
  onSend: () => Promise<CodeDispatch>;
  onConfirm: (code: string) => Promise<void>;
}) {
  const [dispatch, setDispatch] = useState<CodeDispatch | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"send" | "confirm" | null>(null);

  async function send() {
    setError(null);
    setBusy("send");
    try {
      setDispatch(await onSend());
      setCode("");
    } catch (err) {
      setError(getErrorMessage(err, "Unable to send a code."));
    } finally {
      setBusy(null);
    }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy("confirm");
    try {
      await onConfirm(code.trim());
    } catch (err) {
      setError(getErrorMessage(err, "Unable to verify the code."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      {error && <Alert message={error} />}
      {dispatch && <SimulatedCodeNotice dispatch={dispatch} />}
      {dispatch ? (
        <form onSubmit={confirm} className="flex flex-wrap items-end gap-2">
          <div className="flex-1">
            <Field label="Verification code" htmlFor={`${idPrefix}-code`}>
              <Input
                id={`${idPrefix}-code`}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                maxLength={8}
              />
            </Field>
          </div>
          <Button type="submit" loading={busy === "confirm"} disabled={!code.trim()}>
            Confirm
          </Button>
          <Button type="button" variant="ghost" onClick={send} loading={busy === "send"}>
            Resend
          </Button>
        </form>
      ) : (
        <Button type="button" variant="secondary" onClick={send} loading={busy === "send"}>
          {sendLabel}
        </Button>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Two-factor authentication                                                   //
// --------------------------------------------------------------------------- //
type Mode = MfaMethod | "disable" | "regenerate" | null;

function TwoFactorCard({
  status,
  onChange,
}: {
  status: SecurityStatus;
  onChange: (s: SecurityStatus) => void;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  function handleCodes(result: RecoveryCodesResult) {
    setRecoveryCodes(result.recovery_codes);
    setMode(null);
    onChange(result.status);
  }

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Two-factor authentication
        </h3>
        <Badge value={status.mfa_enabled ? "on" : "off"} />
      </div>

      {recoveryCodes && (
        <RecoveryCodesPanel codes={recoveryCodes} onDone={() => setRecoveryCodes(null)} />
      )}

      {status.mfa_locked_reason ? (
        <Notice tone="warning">{status.mfa_locked_reason}</Notice>
      ) : (
        !recoveryCodes && (
          <div className="space-y-4">
            {status.mfa_enabled && status.mfa_method ? (
              <div className="space-y-1 text-sm">
                <p className="text-slate-700">
                  Sign-ins require a code from your{" "}
                  <span className="font-medium">{METHOD_LABELS[status.mfa_method]}</span>.
                </p>
                <p className="text-slate-500">
                  {status.recovery_codes_remaining} unused recovery code
                  {status.recovery_codes_remaining === 1 ? "" : "s"} left.
                </p>
              </div>
            ) : (
              <p className="text-sm text-slate-600">
                Add a second step at sign-in so a stolen password alone can't open your
                account.
              </p>
            )}

            {mode === null && (
              <MethodPicker status={status} onPick={(m) => setMode(m)} />
            )}

            {mode === "totp" && (
              <TotpSetupFlow onDone={handleCodes} onCancel={() => setMode(null)} />
            )}

            {(mode === "email" || mode === "sms") && (
              <PasswordPrompt
                description={`Confirm your password to use ${METHOD_LABELS[mode].toLowerCase()} for 2FA.`}
                submitLabel="Turn on"
                onCancel={() => setMode(null)}
                onSubmit={async (password) => {
                  const res = await api.post<Envelope<RecoveryCodesResult>>(
                    "/auth/mfa/enable",
                    { method: mode, password },
                  );
                  handleCodes(res.data.data!);
                }}
              />
            )}

            {mode === "regenerate" && (
              <PasswordPrompt
                description="New codes replace all existing ones. Confirm your password."
                submitLabel="Generate new codes"
                onCancel={() => setMode(null)}
                onSubmit={async (password) => {
                  const res = await api.post<Envelope<RecoveryCodesResult>>(
                    "/auth/mfa/recovery-codes",
                    { password },
                  );
                  handleCodes(res.data.data!);
                }}
              />
            )}

            {mode === "disable" && (
              <PasswordPrompt
                description="Your account will sign in with a password only. Confirm your password."
                submitLabel="Turn off 2FA"
                variant="danger"
                onCancel={() => setMode(null)}
                onSubmit={async (password) => {
                  const res = await api.post<Envelope<SecurityStatus>>("/auth/mfa/disable", {
                    password,
                  });
                  setMode(null);
                  onChange(res.data.data!);
                }}
              />
            )}

            {mode === null && status.mfa_enabled && (
              <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                <Button variant="secondary" onClick={() => setMode("regenerate")}>
                  New recovery codes
                </Button>
                <Button variant="ghost" onClick={() => setMode("disable")}>
                  Turn off 2FA
                </Button>
              </div>
            )}
          </div>
        )
      )}
    </Card>
  );
}

function MethodPicker({
  status,
  onPick,
}: {
  status: SecurityStatus;
  onPick: (m: MfaMethod) => void;
}) {
  const methods: MfaMethod[] = ["totp", "email", "sms"];
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-700">
        {status.mfa_enabled ? "Switch method" : "Choose a method"}
      </p>
      {methods.map((method) => {
        const current = status.mfa_method === method;
        const available = status.available_methods.includes(method);
        return (
          <div
            key={method}
            className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2"
          >
            <div className="text-sm">
              <p className="font-medium text-slate-800">{METHOD_LABELS[method]}</p>
              <p className="text-slate-500">{METHOD_HINTS[method]}</p>
            </div>
            {current && method !== "totp" ? (
              <span className="text-xs font-medium text-emerald-700">Current</span>
            ) : (
              <Button
                variant="secondary"
                onClick={() => onPick(method)}
                disabled={!available}
                title={available ? undefined : "Verify this contact method above first."}
              >
                {current ? "Re-link" : "Set up"}
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PasswordPrompt({
  description,
  submitLabel,
  variant = "primary",
  onSubmit,
  onCancel,
}: {
  description: string;
  submitLabel: string;
  variant?: "primary" | "danger";
  onSubmit: (password: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSubmit(password);
    } catch (err) {
      setError(getErrorMessage(err, "Something went wrong."));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg bg-slate-50 p-4">
      <p className="text-sm text-slate-600">{description}</p>
      {error && <Alert message={error} />}
      <Field label="Current password" htmlFor="confirm-password">
        <Input
          id="confirm-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" variant={variant} loading={busy} disabled={!password}>
          {submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function TotpSetupFlow({
  onDone,
  onCancel,
}: {
  onDone: (r: RecoveryCodesResult) => void;
  onCancel: () => void;
}) {
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!setup) {
    return (
      <PasswordPrompt
        description="Confirm your password to link an authenticator app."
        submitLabel="Continue"
        onCancel={onCancel}
        onSubmit={async (password) => {
          const res = await api.post<Envelope<TotpSetup>>("/auth/mfa/totp/setup", {
            password,
          });
          setSetup(res.data.data!);
        }}
      />
    );
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api.post<Envelope<RecoveryCodesResult>>("/auth/mfa/totp/confirm", {
        code: code.trim(),
      });
      onDone(res.data.data!);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to verify the code."));
      setBusy(false);
    }
  }

  const groupedSecret = setup.secret.match(/.{1,4}/g)?.join(" ") ?? setup.secret;

  return (
    <form onSubmit={confirm} className="space-y-4 rounded-lg bg-slate-50 p-4">
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
        <li>Open your authenticator app and add a new account.</li>
        <li>Scan this QR code, or enter the setup key manually.</li>
        <li>Type the 6-digit code the app shows to finish.</li>
      </ol>
      <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start">
        <img
          src={setup.qr_code_data_uri}
          alt="QR code for your authenticator app"
          className="h-44 w-44 rounded-lg border border-slate-200 bg-white p-2"
        />
        <div className="space-y-1 text-sm">
          <p className="text-slate-500">Setup key</p>
          <p className="break-all font-mono text-slate-800">{groupedSecret}</p>
          <p className="text-xs text-slate-500">
            Time-based, 6 digits, 30 seconds. This key expires in{" "}
            {Math.round(setup.expires_in_seconds / 60)} minutes if unused.
          </p>
        </div>
      </div>
      {error && <Alert message={error} />}
      <Field label="Code from your app" htmlFor="totp-code">
        <Input
          id="totp-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="123456"
          maxLength={6}
          autoFocus
        />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy} disabled={code.trim().length < 6}>
          Verify and turn on
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function RecoveryCodesPanel({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function download() {
    const blob = new Blob([`InsureCo recovery codes\n\n${text}\n`], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "insureco-recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mb-4 space-y-3">
      <Notice tone="success">
        Two-factor authentication is on. Save these recovery codes somewhere safe: each
        one lets you sign in once if you lose access to your 2FA method. They won't be
        shown again.
      </Notice>
      <ul className="grid grid-cols-2 gap-2 rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-sm text-slate-800">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button variant="secondary" onClick={download}>
          Download .txt
        </Button>
        <Button onClick={onDone}>I've saved them</Button>
      </div>
    </div>
  );
}
