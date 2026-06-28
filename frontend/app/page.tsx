import Link from "next/link";
import { redirect } from "next/navigation";
import {
  Package,
  Zap,
  MessageCircle,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  Globe,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

const steps = [
  {
    icon: Package,
    step: "01",
    title: "Upload your catalog",
    description:
      "Add products with photos, prices, and descriptions in English and Hebrew — or drop a CSV and let the agent structure it.",
  },
  {
    icon: Zap,
    step: "02",
    title: "AI builds your bot",
    description:
      "The Builder agent learns your business, captions products with vision, generates a system prompt, and indexes everything.",
  },
  {
    icon: MessageCircle,
    step: "03",
    title: "Customers chat, bot sells",
    description:
      "Real-time answers with correct prices and photos — right inside WhatsApp, 24/7, in your customer's language.",
  },
];

const highlights = [
  { icon: Globe, label: "Hebrew & English", sub: "Native RTL, mirrors the customer" },
  { icon: ShieldCheck, label: "Never invents prices", sub: "Answers grounded in your catalog" },
  { icon: Zap, label: "Live in minutes", sub: "No code, no integrations to wire" },
];

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) {
    redirect("/onboarding");
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* ── Nav ── */}
      <header className="sticky top-0 z-40 glass border-b border-border/50">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
          <span className="font-heading text-xl font-bold tracking-tight">
            Whats<span className="text-brand">Base</span>
          </span>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link
              href="/login"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className={cn(buttonVariants({ size: "sm" }), "shadow-soft")}
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center gap-16 px-6 py-20 lg:flex-row lg:items-center lg:py-28">
        {/* Left — copy */}
        <div className="flex flex-1 flex-col items-start gap-7 animate-rise-in">
          <span className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-card/60 px-3.5 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur-sm ring-hairline">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-brand" />
            </span>
            Now in beta
            <Sparkles className="size-3.5 text-brand" />
          </span>

          <h1 className="font-heading text-[2.75rem] font-bold leading-[1.05] tracking-tight text-foreground sm:text-6xl lg:text-[4.25rem]">
            Your WhatsApp,
            <br />
            answered by an{" "}
            <span className="text-gradient-brand">AI that sells</span>
          </h1>

          <p className="max-w-lg text-lg leading-relaxed text-muted-foreground">
            Upload your product catalog, connect your number, and launch an
            assistant that answers customers instantly — with the right prices,
            photos, and tone, in Hebrew and English.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/signup"
              className={cn(
                buttonVariants({ size: "lg" }),
                "group shadow-glow",
              )}
            >
              Get started free
              <ArrowRight className="ms-1 size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/login"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "backdrop-blur-sm",
              )}
            >
              Sign in
            </Link>
          </div>

          <p className="text-sm text-muted-foreground">
            No credit card required · Hebrew &amp; English support
          </p>
        </div>

        {/* Right — phone mockup (CSS only) */}
        <div className="flex flex-1 items-center justify-center">
          <div className="relative animate-float-slow">
            {/* Glow behind phone */}
            <div className="absolute inset-0 -m-10 rounded-[3rem] bg-brand/25 blur-3xl" />
            <div className="absolute -right-6 top-10 -z-10 h-24 w-24 rounded-full bg-[var(--brand-accent)]/30 blur-2xl" />

            {/* Phone frame */}
            <div className="relative mx-auto w-[17rem] overflow-hidden rounded-[2.75rem] border-[3px] border-foreground/10 bg-card shadow-elevated">
              {/* Notch */}
              <div className="absolute left-1/2 top-0 z-10 h-5 w-24 -translate-x-1/2 rounded-b-2xl bg-foreground/10" />

              {/* WhatsApp header */}
              <div className="flex items-center gap-3 bg-gradient-to-r from-[var(--brand)] to-[color-mix(in_oklch,var(--brand),var(--brand-accent)_55%)] px-4 pb-3 pt-7">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20 text-xs font-bold text-white">
                  SB
                </div>
                <div>
                  <p className="text-xs font-semibold text-white">Store Bot</p>
                  <p className="text-[10px] text-white/70">online</p>
                </div>
              </div>

              {/* Chat area */}
              <div
                className="space-y-2 bg-[#e7ded5] p-3 dark:bg-[#0e1611]"
                style={{ minHeight: 308 }}
              >
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-[#dcf8c6] px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#0a4a3c] dark:text-white">
                    Do you have red sneakers in size 42?
                  </div>
                </div>

                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#1d2a25] dark:text-white">
                    <p className="font-semibold text-brand">Red Air Max — ₪299</p>
                    <p className="mt-0.5 text-gray-600 dark:text-gray-300">
                      Yes! Size 42 is in stock. Free shipping over ₪200 🎉
                    </p>
                  </div>
                </div>

                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-[#dcf8c6] px-3 py-2 text-[11px] leading-snug shadow-sm dark:bg-[#0a4a3c] dark:text-white">
                    How do I order?
                  </div>
                </div>

                <div className="flex justify-start">
                  <div className="rounded-2xl rounded-tl-sm bg-white px-3 py-2.5 shadow-sm dark:bg-[#1d2a25]">
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
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand">
                  <svg className="size-3.5 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Highlights strip ── */}
      <section className="border-y border-border/50 bg-card/40 backdrop-blur-sm">
        <div className="mx-auto grid max-w-6xl gap-px sm:grid-cols-3">
          {highlights.map(({ icon: Icon, label, sub }) => (
            <div key={label} className="flex items-center gap-4 px-6 py-6">
              <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand ring-hairline">
                <Icon className="size-5" />
              </div>
              <div>
                <p className="font-heading text-sm font-semibold text-foreground">
                  {label}
                </p>
                <p className="text-sm text-muted-foreground">{sub}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="mx-auto w-full max-w-6xl px-6 py-24">
        <div className="mb-14 max-w-2xl">
          <span className="font-heading text-sm font-semibold uppercase tracking-[0.18em] text-brand">
            How it works
          </span>
          <h2 className="mt-3 font-heading text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            From catalog to live bot in three steps
          </h2>
        </div>

        <div className="grid gap-5 sm:grid-cols-3">
          {steps.map(({ icon: Icon, step, title, description }) => (
            <div
              key={step}
              className="card-lift group relative overflow-hidden rounded-2xl border border-border/70 bg-card p-7 shadow-soft"
            >
              {/* Step number watermark */}
              <span className="pointer-events-none absolute -right-2 -top-4 font-heading text-7xl font-bold text-foreground/[0.04] transition-colors group-hover:text-brand/10">
                {step}
              </span>

              <div className="mb-5 flex size-12 items-center justify-center rounded-xl bg-brand/10 text-brand ring-hairline">
                <Icon className="size-6" />
              </div>
              <h3 className="mb-2 font-heading text-lg font-semibold text-foreground">
                {title}
              </h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-24">
        <div className="relative overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-[var(--brand)] to-[color-mix(in_oklch,var(--brand),var(--brand-accent)_60%)] px-8 py-14 text-center shadow-glow sm:px-16">
          <div className="absolute -left-10 -top-10 h-48 w-48 rounded-full bg-white/15 blur-3xl" />
          <div className="absolute -bottom-12 -right-8 h-56 w-56 rounded-full bg-black/10 blur-3xl" />
          <div className="relative">
            <h2 className="font-heading text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Launch your AI sales agent today
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-white/85">
              Set up your catalog once. The bot handles the rest — answering,
              recommending, and selling around the clock.
            </p>
            <Link
              href="/signup"
              className={cn(
                buttonVariants({ size: "lg" }),
                "group mt-7 bg-white text-brand hover:bg-white/90",
              )}
            >
              Get started free
              <ArrowRight className="ms-1 size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-border/50 bg-card/30">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-6 py-6 text-sm text-muted-foreground sm:flex-row">
          <span className="font-heading font-semibold text-foreground">
            Whats<span className="text-brand">Base</span>
          </span>
          <span>Built for builders.</span>
        </div>
      </footer>
    </div>
  );
}
