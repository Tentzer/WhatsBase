"use client";

import { usePathname } from "next/navigation";
import { Check } from "lucide-react";
import { useNavigate } from "@/components/navigation-progress";
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
  const navigate = useNavigate();
  const { t } = useLocale();

  const currentIndex = steps.findIndex((s) => s.href === pathname);

  return (
    <nav aria-label="Onboarding progress" className="mb-10">
      <ol className="relative flex items-start justify-between">
        {/* Background track — from center of step 1 to center of step N */}
        <li
          aria-hidden
          className="pointer-events-none absolute top-5 h-0.5 rounded-full bg-border"
          style={{
            left: `calc(100% / ${steps.length * 2})`,
            right: `calc(100% / ${steps.length * 2})`,
          }}
        />

        {/* Filled progress line — grows to center of current step */}
        {currentIndex > 0 && (
          <li
            aria-hidden
            className="pointer-events-none absolute top-5 h-0.5 rounded-full bg-gradient-to-r from-[var(--brand)] to-[var(--brand-accent)] transition-all duration-500"
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
            <li key={step.href} className="relative flex flex-1 flex-col items-center gap-2.5">
              <button
                type="button"
                onClick={() => navigate(step.href)}
                aria-current={isActive ? "step" : undefined}
                className="group flex flex-col items-center gap-2.5 focus-visible:outline-none"
              >
                {/* Circle */}
                <span
                  className={cn(
                    "relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 text-sm font-semibold transition-all duration-200",
                    isCompleted && "border-brand bg-brand text-brand-foreground",
                    isActive &&
                      "border-brand bg-card text-brand shadow-glow",
                    !isCompleted &&
                      !isActive &&
                      "border-border bg-card text-muted-foreground group-hover:border-brand/50 group-hover:text-brand",
                  )}
                >
                  {isCompleted ? (
                    <Check className="size-4 stroke-[2.5]" />
                  ) : (
                    <span>{index + 1}</span>
                  )}

                  {/* Pulse ring on active step */}
                  {isActive && (
                    <span className="absolute inset-0 animate-ping rounded-full bg-brand/20" />
                  )}
                </span>

                {/* Label */}
                <span
                  className={cn(
                    "font-heading text-xs font-medium transition-colors",
                    isActive && "text-brand",
                    isCompleted && "text-brand/80",
                    !isCompleted && !isActive && "text-muted-foreground",
                  )}
                >
                  {t(step.en, step.he)}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
