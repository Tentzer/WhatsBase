"use client";

import { cn } from "@/lib/utils";

export function ChatTypingIndicator({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-2xl border border-border/60 bg-muted/80 px-4 py-3 shadow-sm",
        className,
      )}
      role="status"
      aria-label="Agent is typing"
    >
      <span className="chat-typing-dot" />
      <span className="chat-typing-dot animation-delay-150" />
      <span className="chat-typing-dot animation-delay-300" />
    </div>
  );
}
