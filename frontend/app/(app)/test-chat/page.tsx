"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SendHorizonal, Sparkles } from "lucide-react";
import { ProductResultCard } from "@/components/product-result-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import type { TestChatMessage } from "@/lib/types";

export default function TestChatPage() {
  const router = useRouter();
  const { locale, t } = useLocale();
  const [messages, setMessages] = useState<TestChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    void api.getAgentStatus().then((status) => {
      if (status !== "live") {
        router.push("/onboarding/build");
      }
    });
    void api.getTestChatHistory().then((history) => setMessages(history));
  }, [router]);

  const placeholder = useMemo(
    () =>
      locale === "he"
        ? "לדוגמה: יש לכם ספה לבנה?"
        : "For example: Do you have a white sofa?",
    [locale],
  );

  const sendMessage = async () => {
    if (!input.trim()) return;
    const text = input.trim();
    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: `local_${Date.now()}`, role: "user", text, createdAt: new Date().toISOString() },
    ]);
    const response = await api.sendTestChatMessage(text);
    setMessages((prev) => [...prev, response.reply]);
    setSending(false);
  };

  return (
    <Card className="flex h-[calc(100vh-11rem)] flex-col">
      <CardHeader className="border-b">
        <CardTitle>{t("Test chat", "צ׳אט בדיקה")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden p-0">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.map((message) => (
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
                <p className="whitespace-pre-wrap">{message.text}</p>
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
          ))}
          {!messages.length ? (
            <p className="text-sm text-muted-foreground">
              {t(
                "Start by asking for a product, price, or delivery policy.",
                "אפשר להתחיל בשאלה על מוצר, מחיר או מדיניות משלוח.",
              )}
            </p>
          ) : null}
        </div>

        <div className="border-t p-4">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={placeholder}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <Button onClick={sendMessage} disabled={sending || !input.trim()}>
              <SendHorizonal className="size-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
