import type { Locale } from "@/lib/types";

/** Hebrew, Arabic, and related RTL scripts. */
const RTL_CHAR =
  /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

/** Strong LTR letters (Latin). */
const LTR_CHAR = /[A-Za-z\u00C0-\u024F]/;

/** Invisible marks that can force the wrong direction in mixed text. */
const BIDI_MARKS = /[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g;

function stripBidiMarks(text: string): string {
  return text.replace(BIDI_MARKS, "");
}

/**
 * Infer reading direction from message content.
 * Prefers RTL when Hebrew is present; falls back to UI locale.
 */
export function getMessageDirection(text: string, locale: Locale = "en"): "rtl" | "ltr" {
  const trimmed = stripBidiMarks(text).trim();
  if (!trimmed) return locale === "he" ? "rtl" : "ltr";

  let rtlCount = 0;
  let ltrCount = 0;

  for (const char of trimmed) {
    if (/\s/.test(char) || /[0-9]/.test(char)) continue;
    if (RTL_CHAR.test(char)) rtlCount += 1;
    else if (LTR_CHAR.test(char)) ltrCount += 1;
  }

  if (rtlCount > 0 && ltrCount === 0) return "rtl";
  if (ltrCount > 0 && rtlCount === 0) return "ltr";
  if (rtlCount > ltrCount) return "rtl";
  if (ltrCount > rtlCount) return "ltr";
  if (rtlCount > 0) return "rtl";

  return locale === "he" ? "rtl" : "ltr";
}

export function messageTextAlignClass(direction: "rtl" | "ltr"): string {
  return direction === "rtl" ? "text-right" : "text-left";
}
