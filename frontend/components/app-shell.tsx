"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Moon, Sun, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FloatingChat } from "@/components/floating-chat";
import { LangfusePanel } from "@/components/langfuse-panel";
import { NavigationProgressProvider } from "@/components/navigation-progress";
import { OnboardingSessionGuard } from "@/components/onboarding-session-guard";
import { useLocale } from "@/lib/locale";
import { createClient } from "@/lib/supabase/client";
import { useOnboardingStore } from "@/lib/store";
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
  const isLeads = pathname.startsWith("/leads");
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

  const resetOnboarding = useOnboardingStore((state) => state.reset);

  const signOut = async () => {
    resetOnboarding();
    await supabase.auth.signOut();
    router.push("/login");
  };

  return (
    <NavigationProgressProvider>
    <OnboardingSessionGuard />
    <div className="min-h-screen text-foreground">
      <header className="sticky top-0 z-40 glass border-b border-border/50">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-5">
            <Link
              href="/"
              className="font-heading text-lg font-bold tracking-tight"
            >
              Whats<span className="text-brand">Base</span>
            </Link>

            {/* Primary nav — segmented pill */}
            <nav className="hidden items-center gap-1 rounded-xl border border-border/60 bg-card/50 p-1 ring-hairline sm:flex">
              <Link
                href="/onboarding/business"
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  isOnboarding
                    ? "bg-brand/10 text-brand"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t("Onboarding", "אונבורדינג")}
              </Link>
              <Link
                href="/test-chat"
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  isTestChat
                    ? "bg-brand/10 text-brand"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t("Test Chat", "צ׳אט בדיקה")}
              </Link>
              <Link
                href="/leads"
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  isLeads
                    ? "bg-brand/10 text-brand"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t("Leads", "לידים")}
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="font-mono text-xs"
              onClick={() => setLocale(locale === "en" ? "he" : "en")}
              aria-label="Toggle language"
            >
              {locale === "en" ? "HE" : "EN"}
            </Button>
            {canViewAnalytics ? (
              <div ref={analyticsRef} className="relative">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className={cn(
                    analyticsOpen && "bg-brand/10 text-brand",
                  )}
                  onClick={() => setAnalyticsOpen((prev) => !prev)}
                  aria-label="Analytics"
                >
                  <BarChart3 className="size-4" />
                </Button>
                {analyticsOpen ? <LangfusePanel isOpen={analyticsOpen} /> : null}
              </div>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={toggleTheme}
              aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            >
              {theme === "light" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <FloatingChat />
            <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
            <Button type="button" variant="outline" size="sm" onClick={signOut}>
              {t("Sign out", "התנתקות")}
            </Button>
          </div>
        </div>

        {/* Mobile nav */}
        <nav className="flex items-center gap-1 border-t border-border/50 px-4 py-2 sm:hidden">
          <Link
            href="/onboarding/business"
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 text-center text-sm font-medium transition-colors",
              isOnboarding ? "bg-brand/10 text-brand" : "text-muted-foreground",
            )}
          >
            {t("Onboarding", "אונבורדינג")}
          </Link>
          <Link
            href="/test-chat"
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 text-center text-sm font-medium transition-colors",
              isTestChat ? "bg-brand/10 text-brand" : "text-muted-foreground",
            )}
          >
            {t("Test Chat", "צ׳אט בדיקה")}
          </Link>
          <Link
            href="/leads"
            className={cn(
              "flex-1 rounded-lg px-3 py-1.5 text-center text-sm font-medium transition-colors",
              isLeads ? "bg-brand/10 text-brand" : "text-muted-foreground",
            )}
          >
            {t("Leads", "לידים")}
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
    </NavigationProgressProvider>
  );
}
