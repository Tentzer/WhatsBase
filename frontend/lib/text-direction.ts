import type { CSSProperties } from "react";
import type { Locale } from "@/lib/types";

/** Hebrew, Arabic, and related RTL scripts. */
const RTL_CHAR =
  /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

/** Strong LTR letters (Latin). */
const LTR_CHAR = /[A-Za-z\u00C0-\u024F]/;

/** Invisible marks that can force the wrong direction in mixed text. */
const BIDI_MARKS = /[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g;

/** Right-to-left mark — forces RTL when the first visible chars are neutral (!, digits, etc.). */
const RTL_MARK = "\u200F";

function stripBidiMarks(text: string): string {
  return text.replace(BIDI_MARKS, "");
}

/**
 * Infer reading direction from message content.
 * Prefers RTL when Hebrew is present; falls back to UI locale.
 */
export function getMessageDirection(text: string, locale: Locale = "en"): "rtl" | "ltr" {
  if (locale === "he") return "rtl";

  const trimmed = stripBidiMarks(text).trim();
  if (!trimmed) return "ltr";

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

  return "ltr";
}

/** Normalize text for display and prepend an RTL mark when needed. */
export function formatMessageText(text: string, direction: "rtl" | "ltr"): string {
  const cleaned = stripBidiMarks(text);
  if (direction !== "rtl") return cleaned;
  if (cleaned.startsWith(RTL_MARK)) return cleaned;
  return `${RTL_MARK}${cleaned}`;
}

export function messageTextStyle(direction: "rtl" | "ltr"): CSSProperties {
  return {
    direction,
    textAlign: direction === "rtl" ? "right" : "left",
    unicodeBidi: "isolate",
  };
}
