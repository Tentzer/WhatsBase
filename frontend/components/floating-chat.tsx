"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/lib/locale";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
}

const WELCOME: Message = {
  id: "welcome",
  role: "assistant",
  text: "Hi! I'm your WhatsBase setup assistant 👋\n\nI can walk you through building your WhatsApp bot — uploading products, connecting your number, and going live. What would you like help with?",
};

// ─── Placeholder reply logic ──────────────────────────────────────────────────
// Replace this function with a real API call when the guide agent is ready.
async function getReply(userText: string): Promise<string> {
  await new Promise((r) => setTimeout(r, 900));
  const t = userText.toLowerCase();
  if (t.includes("product") || t.includes("catalog") || t.includes("מוצר"))
    return "Go to the Products step in the onboarding wizard. You can add product names, prices, and photos there — the AI will learn from them automatically.";
  if (t.includes("whatsapp") || t.includes("number") || t.includes("מספר"))
    return "After the Products step, the WhatsApp step will ask you to connect your Green API instance. You'll need your instance ID and token from green-api.com.";
  if (t.includes("build") || t.includes("agent") || t.includes("bot"))
    return "Once you've filled in your business info and products, hit Build in the last onboarding step. The AI will read your catalog and generate a custom bot for you.";
  if (t.includes("hello") || t.includes("hi") || t.includes("hey") || t.includes("שלום"))
    return "Hey there! 👋 Ask me anything about setting up your WhatsApp bot — I'm here to help.";
  return "I'm still learning, but a real AI assistant will be connected here soon to help you set up your WhatsBase bot. Try the onboarding wizard — it walks you through every step!";
}
// ─────────────────────────────────────────────────────────────────────────────

export function FloatingChat() {
  const { dir } = useLocale();
  const isRTL = dir === "rtl";

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [hasUnread, setHasUnread] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open) {
      setHasUnread(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: `u_${Date.now()}`, role: "user", text },
    ]);
    const replyText = await getReply(text);
    setMessages((prev) => [
      ...prev,
      { id: `a_${Date.now()}`, role: "assistant", text: replyText },
    ]);
    setSending(false);
  };

  return (
    /*
     * Root: fixed to the viewport, sitting just below the sticky header (top-20),
     * on the inline-end edge — right in LTR, left in RTL.
     * The panel opens below the toggle button, aligned to the same edge.
     */
    <div
      className={cn(
        "fixed top-20 z-50 flex flex-col gap-2",
        isRTL ? "left-4 items-start" : "right-4 items-end",
      )}
    >
      {/* ── Toggle button ── */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close assistant" : "Open assistant"}
        className={cn(
          "relative flex h-12 w-12 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-700/30 transition-all hover:bg-emerald-700 hover:scale-105 active:scale-95",
          open && "rotate-90",
        )}
      >
        {open ? (
          <X className="size-5" />
        ) : (
          <MessageCircle className="size-5" />
        )}

        {/* Unread badge */}
        {hasUnread && !open && (
          <span className="absolute right-0 top-0 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white ring-2 ring-card">
            1
          </span>
        )}

        {/* Pulse ring */}
        {!open && (
          <span className="absolute inset-0 animate-ping rounded-full bg-emerald-500/30" />
        )}
      </button>

      {/* ── Chat panel — drops below the button, aligned to same edge ── */}
      <div
        className={cn(
          "flex w-[320px] flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-black/20 transition-all duration-300 dark:shadow-black/50",
          isRTL ? "origin-top-left" : "origin-top-right",
          open
            ? "max-h-[480px] opacity-100 scale-100"
            : "max-h-0 opacity-0 scale-95 pointer-events-none",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between bg-emerald-600 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
              <Bot className="size-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold leading-none text-white">
                WhatsBase Assistant
              </p>
              <p className="mt-0.5 text-[10px] text-emerald-200">
                Setup guide · always here
              </p>
            </div>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="rounded-full p-1 text-white/70 transition-colors hover:bg-white/15 hover:text-white"
            aria-label="Close chat"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Messages */}
        <div
          className="flex-1 space-y-3 overflow-y-auto p-4"
          style={{ maxHeight: 300 }}
        >
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex gap-2",
                msg.role === "user" ? "flex-row-reverse" : "flex-row",
              )}
            >
              {msg.role === "assistant" && (
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60">
                  <Bot className="size-3.5 text-emerald-700 dark:text-emerald-400" />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                  msg.role === "user"
                    ? "rounded-tr-sm bg-emerald-600 text-white"
                    : "rounded-tl-sm bg-muted text-foreground",
                )}
              >
                {msg.text}
              </div>
            </div>
          ))}

          {sending && (
            <div className="flex gap-2">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60">
                <Bot className="size-3.5 text-emerald-700 dark:text-emerald-400" />
              </div>
              <div className="rounded-2xl rounded-tl-sm bg-muted px-3 py-2.5">
                <div className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "0ms" }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "160ms" }} />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/50" style={{ animationDelay: "320ms" }} />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t p-3">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              placeholder="Ask me anything…"
              className="flex-1 rounded-xl border bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/30"
              disabled={sending}
            />
            <button
              onClick={() => void send()}
              disabled={sending || !input.trim()}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white transition-all hover:bg-emerald-700 disabled:opacity-40"
              aria-label="Send"
            >
              <Send className="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
