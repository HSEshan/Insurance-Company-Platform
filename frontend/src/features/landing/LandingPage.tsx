import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ClipboardList,
  ExternalLink,
  FileText,
  MessageCircle,
  Scale,
  ShieldCheck,
  Users,
} from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Alert, Button, Card } from "../../components/ui";
import { ChatWidget } from "../chat/ChatWidget";
import type { AuthResult, Envelope, PublicConfig } from "../../types";

const CAPABILITIES = [
  {
    title: "Policy lifecycle",
    body: "Rate, quote, underwrite, bind, endorse, cancel, and reinstate across auto, home, and life.",
    icon: ShieldCheck,
  },
  {
    title: "Claims adjudication",
    body: "Full claim state machine with fraud scoring, notes, payouts, and decision letters.",
    icon: ClipboardList,
  },
  {
    title: "Rating engine",
    body: "Deterministic, explainable premiums with itemized factors and hard-decline rules.",
    icon: Scale,
  },
  {
    title: "RBAC & audit",
    body: "Role-gated APIs, append-only audit trail, and Super Admin staff management.",
    icon: Users,
  },
  {
    title: "Documents & billing",
    body: "MinIO uploads, generated PDFs, premium schedules, payments, and Celery jobs.",
    icon: FileText,
  },
  {
    title: "Live chat assistant",
    body: "AI-first FAQ widget with simulated handoff to a Member Services representative.",
    icon: MessageCircle,
  },
];

const STACK = ["FastAPI", "React", "PostgreSQL", "Redis", "MinIO", "Docker"];

export function LandingPage() {
  const navigate = useNavigate();
  const { isAuthenticated, setAuth, clearAuth } = useAuthStore();
  const [demoError, setDemoError] = useState<string | null>(null);
  const [busyRole, setBusyRole] = useState<string | null>(null);

  const { data: config } = useQuery({
    queryKey: ["public-config"],
    queryFn: async () => {
      const res = await api.get<Envelope<PublicConfig>>("/public/config");
      return res.data.data!;
    },
    staleTime: 60_000,
  });

  async function demoLogin(email: string, password: string, role: string) {
    setDemoError(null);
    setBusyRole(role);
    try {
      // Clear any stale session so the demo persona replaces it cleanly.
      clearAuth();
      const res = await api.post<Envelope<AuthResult>>("/auth/login", {
        email,
        password,
      });
      const result = res.data.data;
      if (!result) throw new Error("Login returned no data.");
      setAuth(
        result.user,
        result.tokens.access_token,
        result.tokens.refresh_token,
      );
      navigate(
        result.user.must_reset_password ? "/change-password" : "/dashboard",
        { replace: true },
      );
    } catch (error) {
      setDemoError(
        getErrorMessage(
          error,
          "Demo login failed. Is the API up and has the seed been run?",
        ),
      );
    } finally {
      setBusyRole(null);
    }
  }

  const apiDocs =
    (import.meta.env.VITE_API_DOCS_URL as string | undefined) ??
    "http://localhost:8000/api/docs";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2 font-semibold text-slate-800">
            <ShieldCheck className="h-6 w-6 text-indigo-600" />
            InsureCo
          </div>
          <div className="flex items-center gap-3 text-sm">
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="font-medium text-indigo-600 hover:underline"
              >
                Go to dashboard
              </Link>
            ) : (
              <>
                <Link to="/login" className="text-slate-600 hover:text-slate-900">
                  Sign in
                </Link>
                <Link to="/register">
                  <Button className="px-3 py-1.5 text-sm">Register</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-12 px-6 py-12">
        <section className="space-y-4">
          <p className="text-sm font-medium uppercase tracking-wide text-indigo-600">
            Portfolio project
          </p>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Full-stack insurance management platform
          </h1>
          <p className="max-w-2xl text-base text-slate-600">
            A back-office system for quoting, underwriting, policy servicing,
            claims, billing, documents, and compliance — modeled on the
            workflows carriers use day to day.
          </p>
          <div className="flex flex-wrap gap-2">
            {STACK.map((item) => (
              <span
                key={item}
                className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
              >
                {item}
              </span>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link to="/register">
              <Button>Customer? Register</Button>
            </Link>
            <Link to="/login">
              <Button variant="secondary">Staff sign in</Button>
            </Link>
            <a href={apiDocs} target="_blank" rel="noreferrer">
              <Button variant="ghost">
                API docs
                <ExternalLink className="h-4 w-4" />
              </Button>
            </a>
            {config?.github_repo_url && (
              <a
                href={config.github_repo_url}
                target="_blank"
                rel="noreferrer"
              >
                <Button variant="ghost">
                  GitHub
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </a>
            )}
          </div>
        </section>

        {config?.demo_mode_enabled && (
          <section className="space-y-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                One-click demo logins
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Explore every role instantly using seeded accounts. Requires{" "}
                <code className="rounded bg-slate-200 px-1 text-xs">
                  python -m scripts.seed
                </code>{" "}
                against a running API.
              </p>
            </div>
            {demoError && <Alert message={demoError} />}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(config.personas ?? []).map((persona) => (
                <Card key={persona.role} className="flex flex-col">
                  <p className="text-sm font-semibold text-slate-800">
                    {persona.label}
                  </p>
                  <p className="mt-1 flex-1 text-xs text-slate-500">
                    {persona.description}
                  </p>
                  <p className="mt-2 font-mono text-[11px] text-slate-400">
                    {persona.email}
                  </p>
                  <Button
                    className="mt-3 w-full"
                    variant="secondary"
                    loading={busyRole === persona.role}
                    onClick={() =>
                      demoLogin(persona.email, persona.password, persona.role)
                    }
                  >
                    Enter as {persona.role.replace(/_/g, " ")}
                  </Button>
                </Card>
              ))}
            </div>
          </section>
        )}

        <section className="space-y-4">
          <h2 className="text-xl font-semibold text-slate-900">Capabilities</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map(({ title, body, icon: Icon }) => (
              <Card key={title}>
                <Icon className="h-5 w-5 text-indigo-600" />
                <p className="mt-3 text-sm font-semibold text-slate-800">
                  {title}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  {body}
                </p>
              </Card>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h2 className="text-sm font-semibold text-slate-800">
            Getting started
          </h2>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
            <li>
              Use a demo login, then try Quotes → Policies → Claims for that
              role.
            </li>
            <li>
              Managers: Reports and Audit log. Super Admin: Staff admin.
            </li>
            <li>
              Local extras: MailHog at{" "}
              <code className="text-xs">:8025</code>, MinIO console at{" "}
              <code className="text-xs">:9001</code>, OpenAPI at{" "}
              <code className="text-xs">/api/docs</code>.
            </li>
          </ul>
        </section>
      </main>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400">
        {config?.app_name ?? "Insurance Management Platform"} — local demo
      </footer>

      <ChatWidget context="landing" />
    </div>
  );
}
