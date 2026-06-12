"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SendHorizonal } from "lucide-react";
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
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                message.role === "user"
                  ? "ms-auto bg-emerald-600 text-white"
                  : "bg-muted text-foreground"
              }`}
            >
              <p>{message.text}</p>
              {message.cards?.length ? (
                <div className="mt-3 space-y-2">
                  {message.cards.map((card) => (
                    <div key={card.id} className="rounded-md border bg-card p-2 text-foreground">
                      <p className="font-medium">{locale === "he" ? card.nameHe : card.nameEn}</p>
                      <p className="text-xs text-muted-foreground">
                        {card.price} {card.currency}
                      </p>
                    </div>
                  ))}
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
