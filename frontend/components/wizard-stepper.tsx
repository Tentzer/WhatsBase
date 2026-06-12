"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useLocale } from "@/lib/locale";

const steps = [
  { href: "/onboarding/business", en: "Business", he: "עסק" },
  { href: "/onboarding/products", en: "Products", he: "מוצרים" },
  { href: "/onboarding/whatsapp", en: "WhatsApp", he: "וואטסאפ" },
  { href: "/onboarding/build", en: "Build", he: "בנייה" },
];

export function WizardStepper() {
  const pathname = usePathname();
  const { t } = useLocale();

  return (
    <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {steps.map((step, index) => {
        const active = pathname === step.href;
        return (
          <Link
            key={step.href}
            href={step.href}
            className={cn(
              "rounded-lg border px-3 py-2 text-sm transition-colors",
              active
                ? "border-emerald-600 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
                : "bg-card hover:bg-accent",
            )}
          >
            <span className="me-1 text-muted-foreground">{index + 1}.</span>
            <span>{t(step.en, step.he)}</span>
          </Link>
        );
      })}
    </div>
  );
}
