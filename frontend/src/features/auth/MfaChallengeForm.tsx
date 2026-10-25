import { useState, type FormEvent } from "react";
import { api, getErrorMessage } from "../../lib/api";
import { Alert, Button, Field, Input } from "../../components/ui";
import { SimulatedCodeNotice } from "../security/SimulatedCodeNotice";
import type { CodeDispatch, Envelope, LoginResult, MfaChallenge } from "../../types";

const METHOD_PROMPT: Record<MfaChallenge["method"], string> = {
  totp: "Enter the 6-digit code from your authenticator app.",
  email: "Enter the 6-digit code we sent to your email.",
  sms: "Enter the 6-digit code we sent to your phone.",
};

interface Props {
  challenge: MfaChallenge;
  onSuccess: (result: LoginResult) => void;
  onCancel: () => void;
}

/** Second sign-in step: exchanges the short-lived mfa_token + a code for a session. */
export function MfaChallengeForm({ challenge, onSuccess, onCancel }: Props) {
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [dispatch, setDispatch] = useState<CodeDispatch | null>(challenge.dispatch ?? null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!code.trim()) {
      setError("Enter your code.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.post<Envelope<LoginResult>>("/auth/mfa/verify", {
        mfa_token: challenge.mfa_token,
        code: code.trim(),
      });
      if (res.data.data) onSuccess(res.data.data);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to verify the code."));
    } finally {
      setSubmitting(false);
    }
  }

  async function resend() {
    setError(null);
    setResending(true);
    try {
      const res = await api.post<Envelope<CodeDispatch>>("/auth/mfa/resend", {
        mfa_token: challenge.mfa_token,
      });
      if (res.data.data) setDispatch(res.data.data);
    } catch (err) {
      setError(getErrorMessage(err, "Unable to resend the code."));
    } finally {
      setResending(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
    >
      <div>
        <h2 className="text-lg font-semibold text-slate-800">Two-step verification</h2>
        <p className="text-sm text-slate-500">
          {useRecovery
            ? "Enter one of the recovery codes you saved when you set up 2FA. Each code works once."
            : METHOD_PROMPT[challenge.method]}
        </p>
      </div>
      {error && <Alert message={error} />}
      {!useRecovery && dispatch && <SimulatedCodeNotice dispatch={dispatch} />}
      <Field label={useRecovery ? "Recovery code" : "Code"} htmlFor="mfa-code">
        <Input
          id="mfa-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="one-time-code"
          inputMode={useRecovery ? "text" : "numeric"}
          placeholder={useRecovery ? "xxxxx-xxxxx" : "123456"}
          maxLength={16}
          autoFocus
        />
      </Field>
      <Button type="submit" loading={submitting}>
        Verify and sign in
      </Button>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <button
          type="button"
          className="font-medium text-indigo-600 hover:underline"
          onClick={() => {
            setUseRecovery((v) => !v);
            setCode("");
            setError(null);
          }}
        >
          {useRecovery ? "Use my verification code" : "Use a recovery code"}
        </button>
        {!useRecovery && challenge.method !== "totp" && (
          <button
            type="button"
            className="font-medium text-indigo-600 hover:underline disabled:opacity-60"
            onClick={resend}
            disabled={resending}
          >
            {resending ? "Sending…" : "Resend code"}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="text-center text-sm text-slate-500 hover:underline"
      >
        ← Back to sign in
      </button>
    </form>
  );
}
