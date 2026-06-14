"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Eye, EyeOff, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";
import { useOnboardingStore } from "@/lib/store";

interface AuthFormProps {
  mode: "login" | "signup";
}

const features = [
  "Upload catalog once",
  "AI builds the bot",
  "Live on WhatsApp",
];

export function AuthForm({ mode }: AuthFormProps) {
  const supabase = createClient();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const resetOnboarding = useOnboardingStore((state) => state.reset);

  const isLogin = mode === "login";

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    const result = isLogin
      ? await supabase.auth.signInWithPassword({ email, password })
      : await supabase.auth.signUp({ email, password });

    setLoading(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    if (!isLogin && !result.data.session) {
      setSuccess("Account created. Please verify your email, then sign in.");
      return;
    }

    resetOnboarding();
    if (result.data.session?.user?.id) {
      useOnboardingStore.getState().ensureUserSession(result.data.session.user.id);
    }
    router.refresh();
    window.location.assign("/onboarding/business");
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* ── Brand panel (left on desktop) ── */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-[var(--brand)] to-[color-mix(in_oklch,var(--brand),var(--brand-accent)_60%)] p-12 lg:flex lg:flex-col lg:justify-between">
        {/* Decorative glows */}
        <div className="absolute -left-16 -top-16 h-72 w-72 rounded-full bg-white/15 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-black/10 blur-3xl" />

        <Link
          href="/"
          className="relative font-heading text-2xl font-bold tracking-tight text-white"
        >
          WhatsBase
        </Link>

        <div className="relative max-w-md">
          <h2 className="font-heading text-4xl font-bold leading-tight tracking-tight text-white">
            {isLogin
              ? "Welcome back to your sales agent."
              : "Build a WhatsApp sales agent in minutes."}
          </h2>
          <p className="mt-4 text-white/80">
            Upload your catalog once. The AI answers customers instantly — with
            the right prices, photos, and tone, in Hebrew and English.
          </p>

          <div className="mt-8 space-y-3">
            {features.map((f) => (
              <div key={f} className="flex items-center gap-3 text-white">
                <span className="flex size-6 items-center justify-center rounded-full bg-white/20">
                  <Check className="size-3.5 stroke-[3]" />
                </span>
                <span className="text-sm font-medium">{f}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-sm text-white/60">
          Built for builders · Hebrew &amp; English support
        </p>
      </div>

      {/* ── Form panel (right) ── */}
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <Link
            href="/"
            className="mb-8 block text-center font-heading text-2xl font-bold tracking-tight lg:hidden"
          >
            Whats<span className="text-brand">Base</span>
          </Link>

          <Card className="shadow-elevated ring-hairline">
            <CardContent className="p-8">
              {/* Heading */}
              <div className="mb-6">
                <h1 className="font-heading text-2xl font-bold tracking-tight text-foreground">
                  {isLogin ? "Sign in" : "Create account"}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {isLogin
                    ? "Enter your credentials to continue."
                    : "No credit card required — get started free."}
                </p>
              </div>

              {/* Form */}
              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="font-semibold">
                    Email
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    className="h-11"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="password" className="font-semibold">
                    Password
                  </Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={isLogin ? "Your password" : "At least 6 characters"}
                      minLength={6}
                      required
                      className="h-11 pe-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      className="absolute end-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>

                {error ? (
                  <p className="rounded-lg bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
                    {error}
                  </p>
                ) : null}

                {success ? (
                  <p className="rounded-lg bg-brand/10 px-4 py-2.5 text-sm text-brand">
                    {success}
                  </p>
                ) : null}

                <Button
                  type="submit"
                  size="lg"
                  disabled={loading}
                  className="w-full shadow-soft"
                >
                  {loading ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
                </Button>
              </form>

              <p className="mt-6 text-center text-sm text-muted-foreground">
                {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
                <Link
                  className="font-semibold text-brand underline-offset-4 hover:underline"
                  href={isLogin ? "/signup" : "/login"}
                >
                  {isLogin ? "Sign up free" : "Sign in"}
                </Link>
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
