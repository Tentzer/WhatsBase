"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { SendHorizonal, Sparkles } from "lucide-react";
import { ChatTypingIndicator } from "@/components/chat-typing-indicator";
import { ProductResultCard } from "@/components/product-result-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { getMessageDirection, messageTextAlignClass } from "@/lib/text-direction";
import { cn } from "@/lib/utils";
import type { TestChatMessage } from "@/lib/types";

export default function TestChatPage() {
  const router = useRouter();
  const { locale, t } = useLocale();
  const [messages, setMessages] = useState<TestChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const initialScrollDone = useRef(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const container = scrollContainerRef.current;
    if (container) {
      container.scrollTo({ top: container.scrollHeight, behavior });
      return;
    }
    bottomRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  useEffect(() => {
    void api.getAgentStatus().then((status) => {
      if (status !== "live") {
        router.push("/onboarding/build");
      }
    });
    void api.getTestChatHistory().then((history) => {
      setMessages(history);
      setHistoryLoaded(true);
    });
  }, [router]);

  useEffect(() => {
    if (!historyLoaded) return;
    if (!messages.length && !sending) return;

    const behavior: ScrollBehavior = initialScrollDone.current ? "smooth" : "auto";
    initialScrollDone.current = true;

    const frame = requestAnimationFrame(() => {
      scrollToBottom(behavior);
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, sending, historyLoaded, scrollToBottom]);

  const placeholder = useMemo(
    () =>
      locale === "he"
        ? "לדוגמה: יש לכם ספה לבנה?"
        : "For example: Do you have a white sofa?",
    [locale],
  );

  const inputDir = getMessageDirection(input, locale);

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: `local_${Date.now()}`, role: "user", text, createdAt: new Date().toISOString() },
    ]);
    try {
      const response = await api.sendTestChatMessage(text);
      setMessages((prev) => [...prev, response.reply]);
    } finally {
      setSending(false);
    }
  };

  return (
    <Card className="flex h-[calc(100vh-11rem)] flex-col">
      <CardHeader className="border-b">
        <CardTitle>{t("Test chat", "צ׳אט בדיקה")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden p-0">
        <div
          ref={scrollContainerRef}
          dir="ltr"
          className="scrollbar-premium flex-1 space-y-4 overflow-y-auto p-4"
        >
          {messages.map((message) => {
            const messageDir = getMessageDirection(message.text, locale);

            return (
            <div
              key={message.id}
              className={`flex flex-col gap-3 ${message.role === "user" ? "items-end" : "items-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
                  message.role === "user"
                    ? "bg-emerald-600 text-white"
                    : "border border-border/60 bg-muted/80 text-foreground"
                }`}
              >
                <p
                  dir={messageDir}
                  className={cn(
                    "chat-message-text whitespace-pre-wrap",
                    messageTextAlignClass(messageDir),
                  )}
                >
                  {message.text}
                </p>
              </div>

              {message.role === "assistant" && message.cards?.length ? (
                <div className="w-full max-w-xl space-y-2.5">
                  <div className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted-foreground">
                    <Sparkles className="size-3.5 text-emerald-600 dark:text-emerald-400" />
                    <span>
                      {locale === "he"
                        ? message.cards.length === 1
                          ? "מוצר תואם אחד"
                          : `${message.cards.length} מוצרים תואמים`
                        : `${message.cards.length} matching product${message.cards.length === 1 ? "" : "s"}`}
                    </span>
                  </div>
                  <div className="grid gap-2.5">
                    {message.cards.map((card) => (
                      <ProductResultCard key={card.id} card={card} locale={locale} />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            );
          })}

          {sending ? (
            <div className="flex items-start">
              <ChatTypingIndicator />
            </div>
          ) : null}

          {!messages.length && !sending ? (
            <p className="text-sm text-muted-foreground">
              {t(
                "Start by asking for a product, price, or delivery policy.",
                "אפשר להתחיל בשאלה על מוצר, מחיר או מדיניות משלוח.",
              )}
            </p>
          ) : null}

          <div ref={bottomRef} className="h-px shrink-0" aria-hidden />
        </div>

        <div className="border-t p-4">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={placeholder}
              dir={inputDir}
              disabled={sending}
              className={cn("chat-message-text", messageTextAlignClass(inputDir))}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <Button onClick={() => void sendMessage()} disabled={sending || !input.trim()}>
              <SendHorizonal className="size-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
