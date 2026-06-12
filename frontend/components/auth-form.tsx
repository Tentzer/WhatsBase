"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

interface AuthFormProps {
  mode: "login" | "signup";
}

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
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      {/* Brand mark */}
      <div className="mb-8 flex flex-col items-center gap-2">
        <Link href="/" className="text-3xl font-extrabold tracking-tight text-emerald-700">
          WhatsBase
        </Link>
        <p className="text-sm text-muted-foreground">
          {isLogin ? "Welcome back" : "Your WhatsApp sales agent awaits"}
        </p>
      </div>

      {/* Card */}
      <Card className="w-full max-w-md shadow-xl shadow-emerald-100/40 dark:shadow-emerald-900/20">
        <CardHeader className="space-y-1 pb-4">
          <CardTitle className="text-xl">
            {isLogin ? "Sign in to your account" : "Create your account"}
          </CardTitle>
          <CardDescription>
            {isLogin
              ? "Enter your email and password to continue."
              : "Start building your WhatsApp agent in minutes."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={isLogin ? "Your password" : "At least 6 characters"}
                  minLength={6}
                  required
                  className="pe-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            {error ? (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
                {error}
              </p>
            ) : null}

            {success ? (
              <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
                {success}
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={loading}
              className="w-full bg-emerald-600 hover:bg-emerald-700"
            >
              {loading ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-muted-foreground">
            {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
            <Link
              className="font-medium text-emerald-700 hover:text-emerald-800 dark:text-emerald-400 dark:hover:text-emerald-300"
              href={isLogin ? "/signup" : "/login"}
            >
              {isLogin ? "Sign up free" : "Sign in"}
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
