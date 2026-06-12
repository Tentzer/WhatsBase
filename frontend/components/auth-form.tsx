"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Eye, EyeOff, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

interface AuthFormProps {
  mode: "login" | "signup";
}

const features = [
  "Upload your catalog once, the AI does the rest",
  "Bot answers customers in Hebrew & English",
  "Goes live on WhatsApp in minutes",
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

    router.refresh();
    window.location.assign("/onboarding/business");
  };

  return (
    <div className="flex min-h-screen">
      {/* ── Left panel — brand ── */}
      <div className="relative hidden w-[45%] flex-col justify-between overflow-hidden bg-emerald-600 p-12 lg:flex">
        {/* Gradient overlays for depth */}
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-500 via-emerald-600 to-teal-700" />
        <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-white/10 blur-3xl" />
        <div className="absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-teal-400/20 blur-3xl" />

        {/* Top — wordmark */}
        <div className="relative z-10">
          <Link href="/" className="text-2xl font-extrabold tracking-tight text-white">
            WhatsBase
          </Link>
        </div>

        {/* Middle — headline + features */}
        <div className="relative z-10 space-y-8">
          <div>
            <h2 className="text-4xl font-extrabold leading-tight tracking-tight text-white">
              Your AI sales agent,<br />on WhatsApp.
            </h2>
            <p className="mt-4 text-lg text-emerald-100">
              Built for businesses that want to sell more without hiring more.
            </p>
          </div>

          <ul className="space-y-3">
            {features.map((f) => (
              <li key={f} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/20">
                  <Check className="size-3 stroke-[3] text-white" />
                </span>
                <span className="text-sm text-emerald-50">{f}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Bottom — social proof placeholder */}
        <div className="relative z-10">
          <p className="text-xs text-emerald-200/70">
            Powered by Claude &amp; GPT-4o
          </p>
        </div>
      </div>

      {/* ── Right panel — form ── */}
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 sm:px-12">
        {/* Mobile-only wordmark */}
        <Link
          href="/"
          className="mb-10 text-2xl font-extrabold tracking-tight text-emerald-700 lg:hidden"
        >
          WhatsBase
        </Link>

        <div className="w-full max-w-sm">
          {/* Heading */}
          <div className="mb-8">
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground">
              {isLogin ? "Welcome back" : "Get started free"}
            </h1>
            <p className="mt-2 text-muted-foreground">
              {isLogin
                ? "Sign in to your WhatsBase account."
                : "Create your account — no credit card needed."}
            </p>
          </div>

          {/* Form */}
          <form className="space-y-5" onSubmit={onSubmit}>
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
                  className="absolute end-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            {error ? (
              <p className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
                {error}
              </p>
            ) : null}

            {success ? (
              <p className="rounded-lg bg-emerald-50 px-4 py-2.5 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                {success}
              </p>
            ) : null}

            <Button
              type="submit"
              size="lg"
              disabled={loading}
              className="w-full bg-emerald-600 hover:bg-emerald-700"
            >
              {loading ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
            <Link
              className="font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-400 dark:hover:text-emerald-300"
              href={isLogin ? "/signup" : "/login"}
            >
              {isLogin ? "Sign up free" : "Sign in"}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
