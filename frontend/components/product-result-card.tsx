"use client";

import { ImageOff } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ProductCard } from "@/lib/types";

function formatPrice(price: number, currency: string, locale: "he" | "en") {
  try {
    return new Intl.NumberFormat(locale === "he" ? "he-IL" : "en-US", {
      style: "currency",
      currency: currency || "ILS",
      maximumFractionDigits: 0,
    }).format(price);
  } catch {
    return `${price} ${currency}`;
  }
}

export function ProductResultCard({
  card,
  locale,
  className,
}: {
  card: ProductCard;
  locale: "he" | "en";
  className?: string;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const name =
    (locale === "he" ? card.nameHe : card.nameEn) ||
    card.nameEn ||
    card.nameHe ||
    (locale === "he" ? "מוצר" : "Product");
  const showImage = Boolean(card.imageUrl) && !imageFailed;

  return (
    <article
      className={cn(
        "group overflow-hidden rounded-2xl border border-border/60 bg-card shadow-sm",
        "ring-1 ring-black/5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        "dark:ring-white/10",
        className,
      )}
    >
      <div className="flex gap-0 sm:gap-0">
        <div className="relative h-28 w-28 shrink-0 overflow-hidden bg-muted/60 sm:h-32 sm:w-32">
          {showImage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={card.imageUrl}
              alt={name}
              className="size-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <div className="flex size-full flex-col items-center justify-center gap-1 text-muted-foreground">
              <ImageOff className="size-5 opacity-70" />
              <span className="text-[10px] font-medium uppercase tracking-wide opacity-70">
                {locale === "he" ? "ללא תמונה" : "No image"}
              </span>
            </div>
          )}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/15 via-transparent to-transparent" />
        </div>

        <div className="flex min-w-0 flex-1 flex-col justify-center gap-1.5 p-3 sm:p-4">
          {card.category ? (
            <Badge
              variant="secondary"
              className="w-fit max-w-full truncate text-[10px] font-medium uppercase tracking-wide"
            >
              {card.category}
            </Badge>
          ) : null}
          <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-foreground">{name}</h3>
          <p className="text-base font-semibold tracking-tight text-emerald-600 dark:text-emerald-400">
            {formatPrice(card.price, card.currency, locale)}
          </p>
        </div>
      </div>
    </article>
  );
}
