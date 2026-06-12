"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, Bot } from "lucide-react";
import { api } from "@/lib/api";
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
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    void api
      .getSetupAssistantHistory()
      .then((history) => {
        if (history.length > 0) {
          setMessages(history.map((h) => ({ id: h.id, role: h.role, text: h.text })));
        }
      })
      .catch(() => {
        // Keep local welcome message when API is unavailable.
      });
  }, []);

  useEffect(() => {
    if (open) {
      const unreadTimer = window.setTimeout(() => {
        setHasUnread(false);
      }, 0);
      setTimeout(() => inputRef.current?.focus(), 50);
      return () => window.clearTimeout(unreadTimer);
    }
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    setMessages((prev) => [...prev, { id: `u_${Date.now()}`, role: "user", text }]);
    try {
      const response = await api.sendSetupAssistantMessage(text);
      setMessages((prev) => [...prev, { id: response.reply.id, role: "assistant", text: response.reply.text }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `a_${Date.now()}`,
          role: "assistant",
          text: "I had trouble reaching the setup assistant. Please try again in a moment.",
        },
      ]);
    }
    setSending(false);
  };

  return (
    /*
     * Sits inline in the header flex row.
     * The panel is absolutely positioned below, aligned to whichever
     * edge matches the current language direction.
     */
    <div ref={wrapperRef} className="relative">
      {/* Toggle button — styled like the other header buttons */}
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close assistant" : "Open assistant"}
        className={cn(
          "relative inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-sm font-semibold tracking-tight transition-colors",
          open
            ? "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400"
            : "border-border bg-background text-foreground hover:bg-muted dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        )}
      >
        <MessageCircle className="size-3.5" />
        <span>Assistant</span>

        {/* Unread badge */}
        {hasUnread && !open && (
          <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white ring-2 ring-card">
            1
          </span>
        )}
      </button>

      {/* Panel — drops down from the button, aligned to the language-correct edge */}
      <div
        className={cn(
          "absolute top-full z-50 mt-2 flex w-[320px] flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-black/20 transition-all duration-200 dark:shadow-black/50",
          isRTL ? "left-0 origin-top-left" : "right-0 origin-top-right",
          open
            ? "opacity-100 scale-100 pointer-events-auto"
            : "opacity-0 scale-95 pointer-events-none",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between bg-emerald-600 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
              <Bot className="size-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold leading-none text-white">WhatsBase Assistant</p>
              <p className="mt-0.5 text-[10px] text-emerald-200">Setup guide · always here</p>
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
        <div className="space-y-3 overflow-y-auto p-4" style={{ maxHeight: 320 }}>
          {messages.map((msg) => (
            <div key={msg.id} className={cn("flex gap-2", msg.role === "user" ? "flex-row-reverse" : "flex-row")}>
              {msg.role === "assistant" && (
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60">
                  <Bot className="size-3.5 text-emerald-700 dark:text-emerald-400" />
                </div>
              )}
              <div className={cn(
                "max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                msg.role === "user"
                  ? "rounded-tr-sm bg-emerald-600 text-white"
                  : "rounded-tl-sm bg-muted text-foreground",
              )}>
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
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
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
