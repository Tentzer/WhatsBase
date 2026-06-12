import Link from "next/link";
import { redirect } from "next/navigation";
import { Package, Zap, MessageCircle, ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session) {
    redirect("/onboarding");
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* ── Nav ── */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-card/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <span className="text-lg font-bold tracking-tight text-emerald-700">
            WhatsBase
          </span>
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className={cn(
                buttonVariants({ size: "sm" }),
                "bg-emerald-600 hover:bg-emerald-700",
              )}
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center gap-16 px-6 py-20 lg:flex-row lg:py-32">
        {/* Left — copy */}
        <div className="flex flex-1 flex-col items-start gap-6">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            Now in beta
          </span>

          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            Build a WhatsApp{" "}
            <span className="bg-gradient-to-r from-emerald-600 to-teal-500 bg-clip-text text-transparent">
              sales agent
            </span>{" "}
            in minutes
          </h1>

          <p className="max-w-lg text-lg text-muted-foreground">
            Upload your product catalog, connect your WhatsApp number, and
            launch an AI assistant that answers customers instantly — in Hebrew
            and English.
          </p>

          <div className="flex flex-wrap gap-3">
            <Link
              href="/signup"
              className={cn(
                buttonVariants({ size: "lg" }),
                "bg-emerald-600 hover:bg-emerald-700",
              )}
            >
              Get started free
              <ArrowRight className="ms-2 size-4" />
            </Link>
            <Link
              href="/login"
              className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
            >
              Sign in
            </Link>
          </div>

          <p className="text-sm text-muted-foreground">
            No credit card required &middot; Hebrew &amp; English support
          </p>
        </div>

        {/* Right — phone mockup (CSS only) */}
        <div className="flex flex-1 items-center justify-center">
          <div className="relative">
            {/* Glow behind phone */}
            <div className="absolute inset-0 -m-8 rounded-full bg-emerald-400/20 blur-3xl dark:bg-emerald-500/15" />

            {/* Phone frame */}
            <div className="relative mx-auto w-64 overflow-hidden rounded-[2.5rem] border-[3px] border-foreground/10 bg-card shadow-2xl">
              {/* Notch */}
              <div className="absolute left-1/2 top-0 z-10 h-5 w-24 -translate-x-1/2 rounded-b-2xl bg-foreground/8" />

              {/* WhatsApp header */}
              <div className="flex items-center gap-3 bg-emerald-600 px-4 pb-3 pt-7">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-xs font-bold text-white">
                  SB
                </div>
                <div>
                  <p className="text-xs font-semibold text-white">Store Bot</p>
                  <p className="text-[10px] text-emerald-200">online</p>
                </div>
              </div>

              {/* Chat area */}
              <div className="space-y-2 bg-[#e5ddd5] p-3 dark:bg-[#1a2228]" style={{ minHeight: 300 }}>
                {/* Customer message */}
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-lg rounded-tr-sm bg-[#dcf8c6] px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#025c4c] dark:text-white">
                    Do you have red sneakers in size 42?
                  </div>
                </div>

                {/* Bot reply */}
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-lg rounded-tl-sm bg-white px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#202c33] dark:text-white">
                    <p className="font-semibold text-emerald-700 dark:text-emerald-400">
                      Red Air Max — ₪299
                    </p>
                    <p className="mt-0.5 text-gray-600 dark:text-gray-300">
                      Yes! Size 42 is in stock. Free shipping over ₪200 🎉
                    </p>
                  </div>
                </div>

                {/* Customer message 2 */}
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-lg rounded-tr-sm bg-[#dcf8c6] px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#025c4c] dark:text-white">
                    How do I order?
                  </div>
                </div>

                {/* Typing indicator */}
                <div className="flex justify-start">
                  <div className="rounded-lg rounded-tl-sm bg-white px-3 py-2.5 shadow-sm dark:bg-[#202c33]">
                    <div className="flex items-center gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: "0ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: "160ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500" style={{ animationDelay: "320ms" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Input bar */}
              <div className="flex items-center gap-2 border-t border-border/40 bg-card px-3 py-2">
                <div className="h-7 flex-1 rounded-full bg-muted" />
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600">
                  <svg className="size-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="border-t border-border/50 bg-card/40 backdrop-blur-sm">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="mb-12 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              How it works
            </h2>
            <p className="mt-3 text-muted-foreground">
              From catalog to live bot in three steps.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-3">
            {[
              {
                icon: Package,
                step: "1",
                title: "Upload your catalog",
                description:
                  "Add products with photos, prices, and descriptions in English and Hebrew.",
              },
              {
                icon: Zap,
                step: "2",
                title: "AI builds your bot",
                description:
                  "The Builder agent learns your business, generates a system prompt, and indexes everything.",
              },
              {
                icon: MessageCircle,
                step: "3",
                title: "Customers chat, bot sells",
                description:
                  "Real-time answers with correct prices and photos — directly on WhatsApp.",
              },
            ].map(({ icon: Icon, step, title, description }) => (
              <div
                key={step}
                className="relative rounded-2xl border bg-card p-6 shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-400">
                    <Icon className="size-5" />
                  </div>
                  <span className="text-3xl font-bold text-border">{step}</span>
                </div>
                <h3 className="mb-2 font-semibold text-foreground">{title}</h3>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border/50 bg-card/30">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5 text-sm text-muted-foreground">
          <span className="font-semibold text-emerald-700">WhatsBase</span>
          <span>Built for builders.</span>
        </div>
      </footer>
    </div>
  );
}
