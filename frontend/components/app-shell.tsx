"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { FloatingChat } from "@/components/floating-chat";
import { LangfusePanel } from "@/components/langfuse-panel";
import { NavigationProgressProvider } from "@/components/navigation-progress";
import { useLocale } from "@/lib/locale";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale, theme, toggleTheme, t } = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const supabase = createClient();
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const analyticsRef = useRef<HTMLDivElement>(null);

  const isOnboarding = pathname.startsWith("/onboarding");
  const isTestChat = pathname.startsWith("/test-chat");
  const canViewAnalytics = userEmail === "roytentzer@gmail.com";

  useEffect(() => {
    let mounted = true;
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      if (mounted) {
        setUserEmail(data.user?.email ?? null);
      }
    };
    void loadUser();
    return () => {
      mounted = false;
    };
  }, [supabase]);

  useEffect(() => {
    if (!analyticsOpen) return;
    const handleOutsideClick = (event: MouseEvent) => {
      if (analyticsRef.current && !analyticsRef.current.contains(event.target as Node)) {
        setAnalyticsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [analyticsOpen]);

  const signOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <NavigationProgressProvider>
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
            {canViewAnalytics ? (
              <div ref={analyticsRef} className="relative">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(
                    analyticsOpen &&
                      "border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400",
                  )}
                  onClick={() => setAnalyticsOpen((prev) => !prev)}
                >
                  📊 Analytics
                </Button>
                {analyticsOpen ? <LangfusePanel isOpen={analyticsOpen} /> : null}
              </div>
            ) : null}
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
              className={cn(
                buttonVariants({ size: "sm" }),
                isOnboarding
                  ? "border-emerald-500 bg-emerald-50 text-emerald-700 shadow-none dark:bg-emerald-950/50 dark:text-emerald-400"
                  : "border-border bg-background text-foreground hover:bg-muted dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
                "border",
              )}
            >
              {t("Onboarding", "אונבורדינג")}
            </Link>
            <Link
              href="/test-chat"
              className={cn(
                buttonVariants({ size: "sm" }),
                isTestChat
                  ? "border-emerald-500 bg-emerald-50 text-emerald-700 shadow-none dark:bg-emerald-950/50 dark:text-emerald-400"
                  : "border-border bg-background text-foreground hover:bg-muted dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
                "border",
              )}
            >
              {t("Test Chat", "צ׳אט בדיקה")}
            </Link>
            <FloatingChat />
            <Button type="button" size="sm" onClick={signOut}>
              {t("Sign out", "התנתקות")}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
    </NavigationProgressProvider>
  );
}
