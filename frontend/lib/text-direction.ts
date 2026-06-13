/** Hebrew, Arabic, and related RTL scripts. */
const RTL_CHAR =
  /[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

/** Strong LTR letters (Latin). */
const LTR_CHAR = /[A-Za-z\u00C0-\u024F]/;

/**
 * Infer reading direction from message content.
 * Falls back to "auto" when the text has no strong directional characters.
 */
export function getMessageDirection(text: string): "rtl" | "ltr" | "auto" {
  const trimmed = text.trim();
  if (!trimmed) return "auto";

  for (const char of trimmed) {
    if (/\s/.test(char) || /[0-9]/.test(char)) continue;
    if (RTL_CHAR.test(char)) return "rtl";
    if (LTR_CHAR.test(char)) return "ltr";
  }

  return "auto";
}
