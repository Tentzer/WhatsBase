"use client";

import { Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/locale";

export function ThemeToggle() {
  const { theme, toggleTheme } = useLocale();
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      className="size-9 rounded-full p-0"
    >
      {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
    </Button>
  );
}
