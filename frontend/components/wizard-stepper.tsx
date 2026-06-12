"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/lib/locale";

const steps = [
  { href: "/onboarding/business", en: "Business", he: "עסק" },
  { href: "/onboarding/products", en: "Products", he: "מוצרים" },
  { href: "/onboarding/build", en: "Build", he: "בנייה" },
  { href: "/onboarding/whatsapp", en: "WhatsApp", he: "וואטסאפ" },
];

export function WizardStepper() {
  const pathname = usePathname();
  const { t } = useLocale();

  const currentIndex = steps.findIndex((s) => s.href === pathname);

  return (
    <nav aria-label="Onboarding progress" className="mb-8">
      <ol className="relative flex items-start justify-between">
        {/* Background track — from center of step 1 to center of step N */}
        <li
          aria-hidden
          className="pointer-events-none absolute top-4 h-px bg-border"
          style={{
            left: `calc(100% / ${steps.length * 2})`,
            right: `calc(100% / ${steps.length * 2})`,
          }}
        />

        {/* Filled progress line — grows to center of current step */}
        {currentIndex > 0 && (
          <li
            aria-hidden
            className="pointer-events-none absolute top-4 h-px bg-emerald-500 transition-all duration-500"
            style={{
              left: `calc(100% / ${steps.length * 2})`,
              width: `calc(${currentIndex} * 100% / ${steps.length})`,
            }}
          />
        )}

        {steps.map((step, index) => {
          const isCompleted = index < currentIndex;
          const isActive = index === currentIndex;

          return (
            <li key={step.href} className="relative flex flex-1 flex-col items-center gap-2">
              <Link
                href={step.href}
                aria-current={isActive ? "step" : undefined}
                className="group flex flex-col items-center gap-2 focus-visible:outline-none"
              >
                {/* Circle */}
                <span
                  className={cn(
                    "relative z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold transition-all duration-200",
                    isCompleted &&
                      "border-emerald-600 bg-emerald-600 text-white",
                    isActive &&
                      "border-emerald-600 bg-white text-emerald-700 shadow-lg shadow-emerald-200/60 dark:bg-emerald-950 dark:shadow-emerald-900/50",
                    !isCompleted &&
                      !isActive &&
                      "border-border bg-card text-muted-foreground group-hover:border-emerald-400 group-hover:text-emerald-600",
                  )}
                >
                  {isCompleted ? (
                    <Check className="size-4 stroke-[2.5]" />
                  ) : (
                    <span>{index + 1}</span>
                  )}

                  {/* Pulse ring on active step */}
                  {isActive && (
                    <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400/25" />
                  )}
                </span>

                {/* Label */}
                <span
                  className={cn(
                    "text-xs font-medium transition-colors",
                    isActive && "text-emerald-700 dark:text-emerald-400",
                    isCompleted && "text-emerald-600 dark:text-emerald-500",
                    !isCompleted && !isActive && "text-muted-foreground",
                  )}
                >
                  {t(step.en, step.he)}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
