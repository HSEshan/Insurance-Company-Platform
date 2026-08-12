import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle, Send, X } from "lucide-react";
import { api, getErrorMessage } from "../../lib/api";
import { useAuthStore } from "../../stores/authStore";
import { Button } from "../../components/ui";
import type {
  ChatMessage,
  ChatMessageReply,
  ChatSession,
  Envelope,
  PublicConfig,
} from "../../types";

type ChatContext = "landing" | "customer_dashboard";

interface ChatWidgetProps {
  context: ChatContext;
}

const TYPING_MS = 650;

export function ChatWidget({ context }: ChatWidgetProps) {
  const user = useAuthStore((s) => s.user);
  const { data: config } = useQuery({
    queryKey: ["public-config"],
    queryFn: async () => {
      const res = await api.get<Envelope<PublicConfig>>("/public/config");
      return res.data.data!;
    },
    staleTime: 60_000,
  });

  if (!config?.chat_widget_enabled) {
    return null;
  }
  // Spec §6.12: visitors on `/`, customers on dashboard — never staff.
  if (user && user.role !== "customer") {
    return null;
  }

  return <ChatPanel context={context} />;
}

function ChatPanel({ context }: ChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<ChatSession | null>(null);
  const sessionRef = useRef<ChatSession | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const startPromiseRef = useRef<Promise<ChatSession> | null>(null);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, typing, open]);

  async function ensureSession(): Promise<ChatSession> {
    if (sessionRef.current) return sessionRef.current;
    if (startPromiseRef.current) return startPromiseRef.current;

    const promise = (async () => {
      const res = await api.post<Envelope<ChatSession>>("/chat/sessions", {
        context,
      });
      const created = res.data.data!;
      setSession(created);
      sessionRef.current = created;
      return created;
    })();

    startPromiseRef.current = promise;
    try {
      return await promise;
    } finally {
      startPromiseRef.current = null;
    }
  }

  async function openChat() {
    setOpen(true);
    setError(null);
    if (sessionRef.current) return;
    setBusy(true);
    try {
      await ensureSession();
    } catch (err) {
      setError(getErrorMessage(err, "Could not start chat."));
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || busy || typing) return;

    setError(null);
    setBusy(true);
    setDraft("");
    try {
      const current = await ensureSession();
      const optimistic: ChatMessage = {
        id: `local-${Date.now()}`,
        role: "user",
        body: text,
        sender_kind: null,
        created_at: new Date().toISOString(),
      };
      setSession((prev) =>
        prev ? { ...prev, messages: [...prev.messages, optimistic] } : prev,
      );

      setTyping(true);
      const res = await api.post<Envelope<ChatMessageReply>>(
        `/chat/sessions/${current.id}/messages`,
        { body: text },
      );
      const payload = res.data.data!;
      await new Promise((r) => setTimeout(r, TYPING_MS));
      setSession(payload.session);
    } catch (err) {
      setError(getErrorMessage(err, "Could not send message."));
      const id = sessionRef.current?.id;
      if (id) {
        try {
          const res = await api.get<Envelope<ChatSession>>(
            `/chat/sessions/${id}`,
          );
          setSession(res.data.data!);
        } catch {
          /* keep optimistic state */
        }
      }
    } finally {
      setTyping(false);
      setBusy(false);
    }
  }

  async function escalate() {
    if (!sessionRef.current || busy) return;
    setBusy(true);
    setError(null);
    try {
      setTyping(true);
      const res = await api.post<Envelope<ChatSession>>(
        `/chat/sessions/${sessionRef.current.id}/escalate`,
      );
      await new Promise((r) => setTimeout(r, TYPING_MS));
      setSession(res.data.data!);
    } catch (err) {
      setError(getErrorMessage(err, "Could not connect to a representative."));
    } finally {
      setTyping(false);
      setBusy(false);
    }
  }

  const mode = session?.mode ?? "ai";
  const agentLabel =
    mode === "human"
      ? (session?.agent_name ?? "Member Services")
      : "Virtual assistant";

  return (
    <div className="fixed bottom-4 right-4 z-40 flex flex-col items-end gap-3">
      {open && (
        <div className="flex h-[min(28rem,70vh)] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
          <header className="flex items-start justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2.5">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-800">
                InsureCo Chat
              </p>
              <p className="truncate text-xs text-slate-500">
                {mode === "human" ? `Connected to ${agentLabel}` : agentLabel}
              </p>
            </div>
            <button
              type="button"
              className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-3">
            {(session?.messages ?? []).map((msg) => (
              <ChatBubble key={msg.id} role={msg.role} body={msg.body} />
            ))}
            {typing && (
              <p className="text-xs text-slate-400">
                {mode === "human" ? "Alex is typing…" : "Assistant is typing…"}
              </p>
            )}
            {error && (
              <p className="rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700">
                {error}
              </p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-slate-200 px-3 py-2">
            {mode === "ai" && (
              <button
                type="button"
                className="mb-2 text-xs font-medium text-indigo-600 hover:underline disabled:opacity-50"
                onClick={() => void escalate()}
                disabled={busy || !session}
              >
                Talk to a representative
              </button>
            )}
            <form className="flex gap-2" onSubmit={(e) => void sendMessage(e)}>
              <input
                className="min-w-0 flex-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-800 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                placeholder="Type a message…"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={busy && !session}
                maxLength={2000}
              />
              <Button
                type="submit"
                className="px-2.5 py-1.5"
                disabled={!draft.trim() || typing}
                loading={busy && !!session}
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </div>
      )}

      {!open && (
        <button
          type="button"
          onClick={() => void openChat()}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-3.5 py-2.5 text-sm font-medium text-white shadow-md hover:bg-indigo-700"
          aria-label="Open chat"
        >
          <MessageCircle className="h-4 w-4" />
          Chat
        </button>
      )}
    </div>
  );
}

function ChatBubble({ role, body }: { role: string; body: string }) {
  if (role === "system") {
    return (
      <p className="text-center text-[11px] leading-snug text-slate-400">
        {body}
      </p>
    );
  }
  const mine = role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-md px-2.5 py-1.5 text-sm leading-snug ${
          mine ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
        }`}
      >
        {body}
      </div>
    </div>
  );
}
