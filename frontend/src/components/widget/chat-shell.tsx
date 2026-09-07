"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import type { TicketStatus, WidgetPosition } from "@/lib/api";

const MAX_MESSAGE_LENGTH = 10_000;

type WidgetPublicConfig = {
  project_id: string;
  display_name: string;
  welcome_message: string;
  position: WidgetPosition;
  enabled: boolean;
};

type WidgetMessage = {
  id: string;
  sequence_number: number;
  sender_type: "customer" | "ai" | "human";
  content: string;
  created_at: string;
};

type WidgetConversation = {
  session_id: string;
  status: TicketStatus;
  messages: WidgetMessage[];
};

type WidgetMessageEvent = {
  type: string;
  config?: unknown;
  conversation?: unknown;
  message?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isProjectId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[a-z0-9][a-z0-9_-]{0,63}$/i.test(value)
  );
}

function isTicketStatus(value: unknown): value is TicketStatus {
  return (
    value === "open" ||
    value === "ai_processing" ||
    value === "waiting_customer" ||
    value === "human_review" ||
    value === "resolved" ||
    value === "closed"
  );
}

function isWidgetConfig(value: unknown): value is WidgetPublicConfig {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isProjectId(value.project_id) &&
    typeof value.display_name === "string" &&
    typeof value.welcome_message === "string" &&
    (value.position === "bottom-left" || value.position === "bottom-right") &&
    typeof value.enabled === "boolean"
  );
}

function isWidgetMessage(value: unknown): value is WidgetMessage {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.sequence_number === "number" &&
    value.sequence_number >= 1 &&
    (value.sender_type === "customer" ||
      value.sender_type === "ai" ||
      value.sender_type === "human") &&
    typeof value.content === "string" &&
    value.content.length > 0 &&
    typeof value.created_at === "string"
  );
}

function isWidgetConversation(value: unknown): value is WidgetConversation {
  if (!isRecord(value) || !isProjectId(value.session_id)) {
    return false;
  }

  return (
    isTicketStatus(value.status) &&
    Array.isArray(value.messages) &&
    value.messages.every(isWidgetMessage)
  );
}

function formatMessageTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function getParentOrigin(): string | null {
  if (typeof document === "undefined" || !document.referrer) {
    return null;
  }

  try {
    return new URL(document.referrer).origin;
  } catch {
    return null;
  }
}

function senderLabel(senderType: WidgetMessage["sender_type"]): string {
  if (senderType === "customer") {
    return "You";
  }

  if (senderType === "human") {
    return "Support";
  }

  return "AgentDesk";
}

function MessageBubble({ message }: { message: WidgetMessage }) {
  const isCustomer = message.sender_type === "customer";

  return (
    <li className={`flex ${isCustomer ? "justify-end" : "justify-start"}`}>
      <article
        className={`max-w-[86%] rounded-2xl px-4 py-3 ${
          isCustomer
            ? "rounded-br-md bg-zinc-100 text-zinc-950"
            : "rounded-bl-md border border-zinc-800 bg-zinc-900 text-zinc-200"
        }`}
      >
        <div className="flex items-center justify-between gap-4 text-[11px]">
          <span
            className={isCustomer ? "text-zinc-600" : "text-zinc-500"}
          >
            {senderLabel(message.sender_type)}
          </span>
          <time
            dateTime={message.created_at}
            className={isCustomer ? "text-zinc-500" : "text-zinc-600"}
          >
            {formatMessageTime(message.created_at)}
          </time>
        </div>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6">
          {message.content}
        </p>
      </article>
    </li>
  );
}

function EmptyConversation({ welcomeMessage }: { welcomeMessage: string }) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center px-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-zinc-100 text-sm font-bold text-zinc-950">
        AD
      </div>
      <p className="mt-5 max-w-xs text-sm leading-6 text-zinc-400">
        {welcomeMessage}
      </p>
    </div>
  );
}

export default function WidgetChatShell({
  projectId,
}: {
  projectId: string;
}) {
  const [config, setConfig] = useState<WidgetPublicConfig | null>(null);
  const [messages, setMessages] = useState<WidgetMessage[]>([]);
  const [status, setStatus] = useState<TicketStatus | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const parentOrigin = getParentOrigin();

    async function connectToLoader() {
      await Promise.resolve();

      if (cancelled) {
        return;
      }

      if (window.parent === window) {
        setLoading(false);
        setError("Open this page through the AgentDesk embed script.");
        return;
      }

      if (parentOrigin === null) {
        setLoading(false);
        setError("This support chat could not verify its embedding page.");
        return;
      }

      function handleMessage(event: MessageEvent<unknown>) {
        if (
          event.source !== window.parent ||
          event.origin !== parentOrigin ||
          !isRecord(event.data) ||
          typeof event.data.type !== "string"
        ) {
          return;
        }

        const data = event.data as WidgetMessageEvent;

        if (data.type === "agentdesk:init" && isWidgetConfig(data.config)) {
          if (data.config.project_id !== projectId) {
            setError("This widget project is invalid.");
            setLoading(false);
            return;
          }

          setConfig(data.config);
          setError(null);
        } else if (
          data.type === "agentdesk:conversation" &&
          isWidgetConversation(data.conversation)
        ) {
          setMessages(data.conversation.messages);
          setStatus(data.conversation.status);
          setLoading(false);
          setSending(false);
          setError(null);
        } else if (data.type === "agentdesk:sending") {
          setSending(true);
        } else if (data.type === "agentdesk:send-complete") {
          setSending(false);
        } else if (
          data.type === "agentdesk:error" &&
          typeof data.message === "string"
        ) {
          setLoading(false);
          setSending(false);
          setError(data.message);
        }
      }

      window.addEventListener("message", handleMessage);
      window.parent.postMessage(
        {
          type: "agentdesk:ready",
          project_id: projectId,
        },
        parentOrigin,
      );

      return () => {
        window.removeEventListener("message", handleMessage);
      };
    }

    let removeListener: (() => void) | undefined;
    void connectToLoader().then((cleanup) => {
      removeListener = cleanup;
    });

    return () => {
      cancelled = true;
      removeListener?.();
    };
  }, [projectId]);

  function closeChat() {
    const parentOrigin = getParentOrigin();
    if (window.parent !== window && parentOrigin !== null) {
      window.parent.postMessage(
        { type: "agentdesk:close" },
        parentOrigin,
      );
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = input.trim();

    if (!normalized) {
      setError("Enter a message before sending.");
      return;
    }

    if (normalized.length > MAX_MESSAGE_LENGTH) {
      setError(
        `Messages must be ${MAX_MESSAGE_LENGTH.toLocaleString()} characters or fewer.`,
      );
      return;
    }

    if (sending || loading || !config) {
      return;
    }

    setError(null);
    setSending(true);
    setInput("");
    const parentOrigin = getParentOrigin();
    if (parentOrigin === null) {
      setSending(false);
      setError("This support chat could not verify its embedding page.");
      return;
    }

    window.parent.postMessage(
      {
        type: "agentdesk:send",
        content: normalized,
      },
      parentOrigin,
    );
  }

  const title = config?.display_name ?? "AgentDesk Support";
  const welcomeMessage =
    config?.welcome_message ?? "Hi! How can we help?";

  return (
    <main className="flex min-h-screen flex-col bg-zinc-950 text-white">
      <header className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-[10px] font-bold text-zinc-950">
            AD
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{title}</p>
            <p className="text-xs text-zinc-600">Support chat</p>
          </div>
        </div>
        <button
          type="button"
          onClick={closeChat}
          aria-label="Close support chat"
          className="rounded-md px-2 py-1 text-xl leading-none text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
        >
          ×
        </button>
      </header>

      <section
        aria-label="Conversation messages"
        aria-live="polite"
        className="flex-1 overflow-y-auto px-4 py-5"
      >
        {loading ? (
          <p className="flex min-h-56 items-center justify-center text-sm text-zinc-500">
            Loading conversation...
          </p>
        ) : messages.length === 0 ? (
          <EmptyConversation welcomeMessage={welcomeMessage} />
        ) : (
          <ol className="space-y-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </ol>
        )}
      </section>

      {status === "human_review" ? (
        <p className="border-t border-amber-900/50 bg-amber-950/20 px-5 py-3 text-xs leading-5 text-amber-200">
          A support teammate will review this conversation.
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="border-t border-red-900/60 bg-red-950/20 px-5 py-3 text-xs leading-5 text-red-200"
        >
          {error}
        </p>
      ) : null}

      <form
        onSubmit={handleSubmit}
        className="border-t border-zinc-800 bg-zinc-950 p-4"
      >
        <div className="flex items-end gap-2 rounded-xl border border-zinc-800 bg-zinc-900/60 p-2 focus-within:border-zinc-600">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Type a message..."
            aria-label="Message"
            maxLength={MAX_MESSAGE_LENGTH}
            rows={1}
            disabled={loading || sending || !config}
            className="max-h-32 min-h-10 flex-1 resize-y bg-transparent px-2 py-2 text-sm text-white outline-none placeholder:text-zinc-600 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || sending || !config}
            aria-label="Send message"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-lg text-zinc-950 transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {sending ? "…" : "↑"}
          </button>
        </div>
        <p className="mt-2 text-[10px] text-zinc-700">
          Responses use the company&apos;s configured support knowledge.
        </p>
      </form>
    </main>
  );
}
