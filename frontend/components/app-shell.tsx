"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { FloatingChat } from "@/components/floating-chat";
import { useLocale } from "@/lib/locale";
import { createClient } from "@/lib/supabase/client";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale, theme, toggleTheme, t } = useLocale();
  const router = useRouter();
  const supabase = createClient();

  const signOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <div className="min-h-screen text-foreground">
      <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/" className="text-xl font-extrabold tracking-tight text-emerald-700">
            WhatsBase
          </Link>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setLocale(locale === "en" ? "he" : "en")}
            >
              {locale === "en" ? "HE" : "EN"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={toggleTheme}
              aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            >
              {theme === "light" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Link
              href="/onboarding/business"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              {t("Onboarding", "אונבורדינג")}
            </Link>
            <Link href="/test-chat" className={buttonVariants({ variant: "outline", size: "sm" })}>
              {t("Test Chat", "צ׳אט בדיקה")}
            </Link>
            <Button type="button" size="sm" onClick={signOut}>
              {t("Sign out", "התנתקות")}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <FloatingChat />
    </div>
  );
}
