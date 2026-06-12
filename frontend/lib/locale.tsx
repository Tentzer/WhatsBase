"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { Locale } from "@/lib/types";

interface LocaleContextValue {
  locale: Locale;
  dir: "ltr" | "rtl";
  theme: "light" | "dark";
  setLocale: (locale: Locale) => void;
  toggleTheme: () => void;
  t: (en: string, he?: string) => string;
}

const LocaleContext = createContext<LocaleContextValue | undefined>(undefined);
const LOCALE_STORAGE_KEY = "whatsbase.locale";
const THEME_STORAGE_KEY = "whatsbase.theme";

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window === "undefined") return "en";
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return stored === "en" || stored === "he" ? stored : "en";
  });
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  });

  useEffect(() => {
    const dir = locale === "he" ? "rtl" : "ltr";
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }, [locale]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      dir: locale === "he" ? "rtl" : "ltr",
      theme,
      setLocale: setLocaleState,
      toggleTheme: () => setTheme((prev) => (prev === "light" ? "dark" : "light")),
      t: (en, he) => (locale === "he" ? he ?? en : en),
    }),
    [locale, theme],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within LocaleProvider.");
  }
  return context;
}
