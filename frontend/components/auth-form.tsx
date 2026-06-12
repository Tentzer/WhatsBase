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
    <div className="flex min-h-screen flex-col">
      {/* ── Top green band ── */}
      <div className="relative overflow-hidden bg-gradient-to-br from-emerald-500 via-emerald-600 to-teal-700 px-6 py-10 text-center">
        {/* Decorative glows */}
        <div className="absolute -top-20 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-white/10 blur-3xl" />
        <div className="absolute -bottom-10 -right-10 h-48 w-48 rounded-full bg-teal-400/20 blur-2xl" />

        <div className="relative z-10">
          <Link href="/" className="text-3xl font-extrabold tracking-tight text-white">
            WhatsBase
          </Link>
          <p className="mt-2 text-emerald-100">
            {isLogin ? "Good to have you back." : "Your AI sales agent on WhatsApp."}
          </p>

          {/* Feature pills — visible on md+ */}
          <div className="mt-5 hidden justify-center gap-3 md:flex">
            {features.map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white backdrop-blur-sm"
              >
                <Check className="size-3 stroke-[3]" />
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Form — centered in remaining space ── */}
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <Card className="shadow-2xl shadow-emerald-900/10 dark:shadow-emerald-900/30">
            <CardContent className="p-8">
              {/* Heading */}
              <div className="mb-6">
                <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
                  {isLogin ? "Sign in" : "Create account"}
                </h1>
                <p className="mt-1 text-sm text-muted-foreground">
                  {isLogin
                    ? "Enter your credentials to continue."
                    : "No credit card required."}
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

              <p className="mt-5 text-center text-sm text-muted-foreground">
                {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
                <Link
                  className="font-semibold text-emerald-700 hover:text-emerald-800 dark:text-emerald-400 dark:hover:text-emerald-300"
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
