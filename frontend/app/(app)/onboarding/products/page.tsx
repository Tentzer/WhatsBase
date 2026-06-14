"use client";

import Papa from "papaparse";
import { useEffect, useRef, useState, type RefObject } from "react";
import { useNavigate } from "@/components/navigation-progress";
import { ImageIcon, LayoutGrid, Loader2, Pencil, Trash2, Upload, X } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { useOnboardingStore } from "@/lib/store";
import type { ProductDraft, ProductImageDraft } from "@/lib/types";

type BulkUploadSource = "multi" | "folder";

interface BulkUploadProgress {
  source: BulkUploadSource;
  completed: number;
  total: number;
}

/** True if the id looks like a UUID (saved to the DB), false for local draft ids. */
function isDbId(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
}

/** The best human-readable name we can find for a product. */
function displayName(row: ProductDraft): string {
  return row.nameEn || row.nameHe || row.stableKey;
}

function LazyProductImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [loaded, setLoaded] = useState(false);
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.05 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`flex items-center justify-center overflow-hidden bg-muted ${className ?? ""}`}
    >
      {visible && src ? (
        <img
          src={src}
          alt={alt}
          className={`h-full w-full object-cover transition-opacity duration-300 ${loaded ? "opacity-100" : "opacity-0"}`}
          onLoad={() => setLoaded(true)}
        />
      ) : null}
      {(!visible || !src || !loaded) && (
        <ImageIcon className="size-8 text-muted-foreground/30" />
      )}
    </div>
  );
}

function UploadProgressBar({
  label,
  value,
  indeterminate = false,
}: {
  label: string;
  value: number;
  indeterminate?: boolean;
}) {
  return (
    <div className="space-y-1.5" aria-live="polite">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Loader2 className="size-3 animate-spin" />
          {label}
        </span>
        {!indeterminate ? <span className="tabular-nums">{Math.round(value)}%</span> : null}
      </div>
      {indeterminate ? (
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-brand" />
        </div>
      ) : (
        <Progress value={value} />
      )}
    </div>
  );
}

async function uploadImageFilesSequentially(
  files: File[],
  onProgress: (completed: number, total: number) => void,
): Promise<ProductImageDraft[]> {
  const drafts: ProductImageDraft[] = [];
  for (let index = 0; index < files.length; index += 1) {
    drafts.push(await api.createImageDraft(files[index]));
    onProgress(index + 1, files.length);
  }
  return drafts;
}

interface CsvRow {
  stable_key: string;
  name_he: string;
  name_en: string;
  category: string;
  price: string;
  currency: "ILS";
  in_stock: string;
  colors: string;
  materials: string;
  style: string;
  image: string;
}

function productFromCsv(row: CsvRow): ProductDraft {
  return {
    id: row.stable_key,
    stableKey: row.stable_key,
    nameHe: row.name_he,
    nameEn: row.name_en,
    category: row.category,
    price: Number(row.price || 0),
    currency: "ILS",
    inStock: row.in_stock === "true",
    colors: row.colors,
    materials: row.materials,
    style: row.style,
    image: row.image
      ? {
          id: `img_${row.stable_key}`,
          fileName: row.image,
          previewUrl: "",
          storagePath: `mock/uploads/${row.image}`,
        }
      : undefined,
  };
}

function stableKeyFromImage(image: ProductImageDraft): string {
  const path = image.relativePath ?? image.fileName;
  const baseName = path.split(/[/\\]/).pop() ?? image.fileName;
  return baseName.replace(/\.[^.]+$/i, "").toLowerCase();
}

function productDraftFromImage(image: ProductImageDraft, stableKey: string): ProductDraft {
  return {
    id: stableKey,
    stableKey,
    nameHe: "",
    nameEn: "",
    category: "",
    price: 0,
    currency: "ILS",
    inStock: true,
    colors: "",
    materials: "",
    style: "",
    image,
  };
}

function mergeUploadedPhotosIntoRows(
  items: ProductDraft[],
  images: ProductImageDraft[],
): { items: ProductDraft[]; attachedCount: number; createdCount: number } {
  if (!images.length) {
    return { items, attachedCount: 0, createdCount: 0 };
  }

  const attached = autoAttachImages(items, images);
  const usedKeys = new Set(attached.items.map((row) => row.stableKey));
  const linkedImageIds = new Set(
    attached.items.flatMap((row) => (row.image ? [row.image.id] : [])),
  );

  const created: ProductDraft[] = [];
  for (const image of images) {
    if (linkedImageIds.has(image.id)) continue;

    let stableKey = stableKeyFromImage(image);
    let suffix = 1;
    const baseKey = stableKey;
    while (usedKeys.has(stableKey)) {
      stableKey = `${baseKey}-${suffix}`;
      suffix += 1;
    }
    usedKeys.add(stableKey);
    created.push(productDraftFromImage(image, stableKey));
  }

  return {
    items: [...attached.items, ...created],
    attachedCount: attached.attachedCount,
    createdCount: created.length,
  };
}

function autoAttachImages(items: ProductDraft[], images: ProductImageDraft[]) {
  if (!images.length) return { items, attachedCount: 0 };
  const nextItems = [...items];
  let photoIndex = 0;
  let attachedCount = 0;
  for (let index = 0; index < nextItems.length && photoIndex < images.length; index += 1) {
    if (nextItems[index]?.image) continue;
    nextItems[index] = { ...nextItems[index], image: images[photoIndex] };
    photoIndex += 1;
    attachedCount += 1;
  }
  return { items: nextItems, attachedCount };
}

function imagesFromProducts(items: ProductDraft[]): ProductImageDraft[] {
  return items.map((item) => item.image).filter(Boolean) as ProductImageDraft[];
}

// ── Catalog dialog ────────────────────────────────────────────────────────────

interface CatalogDialogProps {
  rows: ProductDraft[];
  deletingId: string | null;
  rowUploadingId: string | null;
  bulkUploading: boolean;
  t: (en: string, he: string) => string;
  onUpdate: (id: string, field: keyof ProductDraft, value: string | number) => void;
  onRemove: (id: string) => Promise<void>;
  onImageUpload: (rowId: string, file: File | null) => Promise<void>;
}

function CatalogDialog({
  rows,
  deletingId,
  rowUploadingId,
  bulkUploading,
  t,
  onUpdate,
  onRemove,
  onImageUpload,
}: CatalogDialogProps) {
  const [editingId, setEditingId] = useState<string | null>(null);

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            type="button"
            variant="outline"
            className="gap-2"
          />
        }
      >
        <LayoutGrid className="size-4" />
        {t(`View catalog (${rows.length})`, `צפייה בקטלוג (${rows.length})`)}
      </DialogTrigger>

      <DialogContent
        showCloseButton
        className="flex max-h-[92vh] w-[95vw] max-w-[95vw] flex-col gap-0 overflow-hidden p-0"
      >
        <DialogHeader className="flex-none border-b px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            <LayoutGrid className="size-4 text-brand" />
            {t("Product Catalog", "קטלוג מוצרים")}
            <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
              {rows.length}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto overscroll-contain p-6">
          {rows.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-12">
              {t("No products yet.", "אין מוצרים עדיין.")}
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {rows.map((row) => {
                const name = displayName(row);
                const isEditing = editingId === row.id;
                const isDeleting = deletingId === row.id;
                const hasImage = Boolean(row.image?.previewUrl || row.image?.storagePath);
                const imgSrc = row.image?.previewUrl ?? "";

                return (
                  <div
                    key={row.id}
                    className="group overflow-hidden rounded-xl border bg-card shadow-soft transition-shadow hover:shadow-elevated"
                  >
                    {/* Product image */}
                    <div className="relative aspect-square w-full overflow-hidden bg-muted">
                      <LazyProductImage src={imgSrc} alt={name} className="absolute inset-0 h-full w-full" />

                      {/* Action buttons overlay */}
                      <div className="absolute right-2 top-2 flex gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={() => setEditingId(isEditing ? null : row.id)}
                          className="flex h-7 w-7 items-center justify-center rounded-full bg-background/90 text-foreground shadow-sm backdrop-blur-sm transition hover:bg-background"
                          aria-label={t("Edit", "עריכה")}
                        >
                          {isEditing ? <X className="size-3.5" /> : <Pencil className="size-3.5" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => void onRemove(row.id)}
                          disabled={isDeleting}
                          className="flex h-7 w-7 items-center justify-center rounded-full bg-background/90 text-destructive shadow-sm backdrop-blur-sm transition hover:bg-destructive hover:text-white disabled:opacity-50"
                          aria-label={t("Delete", "מחיקה")}
                        >
                          {isDeleting ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="size-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Info / edit area */}
                    <div className="p-3">
                      {!isEditing ? (
                        /* View mode */
                        <div className="space-y-1">
                          <p className="truncate text-sm font-semibold leading-snug" title={name}>
                            {name}
                          </p>
                          <div className="flex items-center justify-between gap-2">
                            {row.category ? (
                              <span className="truncate text-xs text-muted-foreground">{row.category}</span>
                            ) : (
                              <span className="text-xs text-muted-foreground/40">—</span>
                            )}
                            {row.price > 0 ? (
                              <span className="shrink-0 rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">
                                ₪{row.price.toLocaleString()}
                              </span>
                            ) : null}
                          </div>
                          {!hasImage && (
                            <Label
                              className={`mt-2 flex cursor-pointer items-center gap-1.5 rounded-md border border-dashed px-2.5 py-2 text-xs text-muted-foreground hover:bg-accent ${rowUploadingId === row.id ? "pointer-events-none opacity-60" : ""}`}
                            >
                              <Upload className="size-3.5" />
                              {rowUploadingId === row.id
                                ? t("Uploading…", "מעלה…")
                                : t("Attach image", "הוספת תמונה")}
                              <Input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                disabled={rowUploadingId === row.id || bulkUploading}
                                onChange={(e) => {
                                  void onImageUpload(row.id, e.target.files?.[0] ?? null);
                                  e.target.value = "";
                                }}
                              />
                            </Label>
                          )}
                        </div>
                      ) : (
                        /* Edit mode */
                        <div className="space-y-2">
                          <Input
                            value={row.nameEn}
                            onChange={(e) => onUpdate(row.id, "nameEn", e.target.value)}
                            placeholder={t(`Name (EN) — e.g. ${row.stableKey}`, `שם באנגלית`)}
                            className="h-8 text-xs"
                          />
                          <Input
                            value={row.nameHe}
                            onChange={(e) => onUpdate(row.id, "nameHe", e.target.value)}
                            placeholder={t("Name (HE)", "שם בעברית")}
                            className="h-8 text-xs"
                          />
                          <div className="grid grid-cols-2 gap-2">
                            <Input
                              value={row.category}
                              onChange={(e) => onUpdate(row.id, "category", e.target.value)}
                              placeholder={t("Category", "קטגוריה")}
                              className="h-8 text-xs"
                            />
                            <Input
                              type="number"
                              value={row.price || ""}
                              onChange={(e) => onUpdate(row.id, "price", e.target.value)}
                              placeholder={t("Price ₪", "מחיר")}
                              className="h-8 text-xs"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="w-full rounded-md bg-brand/10 py-1.5 text-xs font-medium text-brand hover:bg-brand/20 transition-colors"
                          >
                            {t("Done", "סיום")}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProductsOnboardingPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const { setProducts, setCatalogPhotos } = useOnboardingStore();
  const [rows, setRows] = useState<ProductDraft[]>([]);
  const [photoLibrary, setPhotoLibrary] = useState<ProductImageDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkUploadProgress, setBulkUploadProgress] = useState<BulkUploadProgress | null>(null);
  const [bulkUploadMessage, setBulkUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [rowUploadingId, setRowUploadingId] = useState<string | null>(null);
  const [syncingUploads, setSyncingUploads] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const multiInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void (async () => {
      setSyncingUploads(true);
      setUploadError(null);
      setBulkUploadMessage(null);
      setRows([]);
      setPhotoLibrary([]);
      setProducts([]);
      setCatalogPhotos([]);

      try {
        const fromDb = await api.getProducts();
        if (fromDb.length > 0) {
          const images = imagesFromProducts(fromDb);
          setRows(fromDb);
          setProducts(fromDb);
          setPhotoLibrary(images);
          setCatalogPhotos(images);
          return;
        }

        const items = await api.syncProductsFromUploads();
        const images = imagesFromProducts(items);
        setRows(items);
        setProducts(items);
        setPhotoLibrary(images);
        setCatalogPhotos(images);
        if (items.length) {
          setBulkUploadMessage(
            t(
              `Recovered ${items.length} products from your uploaded photos.`,
              `שוחזרו ${items.length} מוצרים מהתמונות שהועלו.`,
            ),
          );
        }
      } catch (err) {
        setProducts([]);
        setCatalogPhotos([]);
        setRows([]);
        setPhotoLibrary([]);
        setUploadError(
          err instanceof Error
            ? err.message
            : t("Could not recover uploaded photos.", "לא ניתן לשחזר את התמונות שהועלו."),
        );
      } finally {
        setSyncingUploads(false);
      }
    })();
  }, [setCatalogPhotos, setProducts, t]);

  useEffect(() => {
    const folderInput = folderInputRef.current;
    if (!folderInput) return;
    folderInput.setAttribute("webkitdirectory", "");
    folderInput.setAttribute("directory", "");
  }, []);

  const mergePhotoLibrary = (
    existing: ProductImageDraft[],
    incoming: ProductImageDraft[],
  ): ProductImageDraft[] => {
    const deduped = new Map<string, ProductImageDraft>();
    for (const image of existing) {
      const key = `${image.storagePath}:${image.fileName}:${image.relativePath ?? ""}`;
      deduped.set(key, image);
    }
    for (const image of incoming) {
      const key = `${image.storagePath}:${image.fileName}:${image.relativePath ?? ""}`;
      deduped.set(key, image);
    }
    return Array.from(deduped.values());
  };

  const onCsvUpload = (file: File | null) => {
    if (!file) return;
    Papa.parse<CsvRow>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const parsed = results.data
          .filter((row) => row.stable_key && row.name_en)
          .map((row) => productFromCsv(row));
        setRows(parsed);
      },
    });
  };

  const onImageUpload = async (rowId: string, file: File | null) => {
    if (!file) return;
    setRowUploadingId(rowId);
    setUploadError(null);
    try {
      const imageDraft = await api.createImageDraft(file);
      setRows((prev) =>
        prev.map((row) => (row.id === rowId ? { ...row, image: imageDraft } : row)),
      );
      setPhotoLibrary((prev) => mergePhotoLibrary(prev, [imageDraft]));
    } catch (err) {
      setUploadError(
        err instanceof Error
          ? err.message
          : t("Image upload failed.", "העלאת התמונה נכשלה."),
      );
    } finally {
      setRowUploadingId(null);
    }
  };

  const onBulkImageUpload = async (
    files: FileList | null,
    source: BulkUploadSource,
    inputRef?: RefObject<HTMLInputElement | null>,
  ) => {
    if (!files?.length) return;
    const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) {
      setBulkUploadMessage(t("No image files were selected.", "לא נבחרו קבצי תמונה."));
      return;
    }

    setBulkUploading(true);
    setBulkUploadMessage(null);
    setUploadError(null);
    setBulkUploadProgress({ source, completed: 0, total: imageFiles.length });

    let completedCount = 0;
    try {
      const drafts = await uploadImageFilesSequentially(imageFiles, (completed, total) => {
        completedCount = completed;
        setBulkUploadProgress({ source, completed, total });
      });
      setPhotoLibrary((prev) => mergePhotoLibrary(prev, drafts));

      setRows((prev) => {
        const result = mergeUploadedPhotosIntoRows(prev, drafts);
        const parts = [
          t(`Uploaded ${drafts.length} photos.`, `הועלו ${drafts.length} תמונות.`),
          result.attachedCount > 0
            ? t(
                `Attached ${result.attachedCount} to existing products.`,
                `צורפו ${result.attachedCount} למוצרים קיימים.`,
              )
            : null,
          result.createdCount > 0
            ? t(
                `Created ${result.createdCount} product rows from filenames.`,
                `נוצרו ${result.createdCount} שורות מוצר משמות הקבצים.`,
              )
            : null,
        ].filter(Boolean);
        setBulkUploadMessage(parts.join(" "));
        return result.items;
      });
    } catch (err) {
      setUploadError(
        err instanceof Error
          ? err.message
          : t(
              `Upload failed after ${completedCount} of ${imageFiles.length} photos.`,
              `ההעלאה נכשלה אחרי ${completedCount} מתוך ${imageFiles.length} תמונות.`,
            ),
      );
    } finally {
      setBulkUploading(false);
      setBulkUploadProgress(null);
      if (inputRef?.current) {
        inputRef.current.value = "";
      }
    }
  };

  const bulkProgressPercent =
    bulkUploadProgress && bulkUploadProgress.total > 0
      ? (bulkUploadProgress.completed / bulkUploadProgress.total) * 100
      : 0;

  const removeProduct = async (id: string) => {
    setDeletingId(id);
    try {
      if (isDbId(id)) {
        await api.deleteProduct(id);
      }
      setRows((prev) => prev.filter((item) => item.id !== id));
    } catch (err) {
      setUploadError(
        err instanceof Error
          ? err.message
          : t("Failed to delete product.", "מחיקת המוצר נכשלה."),
      );
    } finally {
      setDeletingId(null);
    }
  };

  const updateProduct = (id: string, field: keyof ProductDraft, value: string | number) => {
    setRows((prev) =>
      prev.map((item) => {
        if (item.id !== id) return item;
        if (field === "price") {
          return { ...item, price: Number(value || 0) };
        }
        return { ...item, [field]: value };
      }),
    );
  };

  const [saveError, setSaveError] = useState<string | null>(null);

  const saveAndContinue = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const rowsToSave =
        rows.length > 0 ? rows : mergeUploadedPhotosIntoRows([], photoLibrary).items;
      const saved = await api.saveProducts(rowsToSave);
      setProducts(saved);
      setCatalogPhotos(photoLibrary);
      navigate("/onboarding/build");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <WizardStepper />
      <Card>
        <CardHeader>
          <CardTitle>{t("Products and media", "מוצרים ותמונות")}</CardTitle>
          <CardDescription>
            {t(
              "Upload product photos and prices, or import from CSV.",
              "העלאת תמונות ומחירים או ייבוא מקובץ CSV.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* CSV import */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>{t("Import CSV", "ייבוא CSV")}</Label>
              <Input
                type="file"
                accept=".csv"
                disabled={syncingUploads || bulkUploading}
                onChange={(event) => onCsvUpload(event.target.files?.[0] ?? null)}
              />
            </div>
            <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              {t(
                "CSV columns: stable_key, name_he, name_en, category, price, currency, in_stock, colors, materials, style, image.",
                "עמודות CSV: stable_key, name_he, name_en, category, price, currency, in_stock, colors, materials, style, image.",
              )}
            </div>
          </div>

          {syncingUploads ? (
            <UploadProgressBar
              label={t("Recovering your uploaded photos...", "משחזר את התמונות שהועלו...")}
              value={0}
              indeterminate
            />
          ) : null}

          {/* Bulk photo upload */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>{t("Upload many photos", "העלאת תמונות מרובות")}</Label>
              <Input
                ref={multiInputRef}
                type="file"
                accept="image/*"
                multiple
                onChange={(event) => void onBulkImageUpload(event.target.files, "multi", multiInputRef)}
                disabled={syncingUploads || bulkUploading}
              />
              {bulkUploadProgress?.source === "multi" ? (
                <UploadProgressBar
                  label={t(
                    `Uploading photo ${bulkUploadProgress.completed} of ${bulkUploadProgress.total}...`,
                    `מעלה תמונה ${bulkUploadProgress.completed} מתוך ${bulkUploadProgress.total}...`,
                  )}
                  value={bulkProgressPercent}
                />
              ) : null}
            </div>
            <div className="space-y-2">
              <Label>{t("Upload a full folder", "העלאת תיקייה מלאה")}</Label>
              <input
                ref={folderInputRef}
                type="file"
                multiple
                accept="image/*"
                onChange={(event) => void onBulkImageUpload(event.target.files, "folder", folderInputRef)}
                disabled={syncingUploads || bulkUploading}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm text-foreground transition-colors outline-none file:hidden focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
              />
              {bulkUploadProgress?.source === "folder" ? (
                <UploadProgressBar
                  label={t(
                    `Uploading photo ${bulkUploadProgress.completed} of ${bulkUploadProgress.total}...`,
                    `מעלה תמונה ${bulkUploadProgress.completed} מתוך ${bulkUploadProgress.total}...`,
                  )}
                  value={bulkProgressPercent}
                />
              ) : null}
            </div>
            <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground sm:col-span-2">
              {t(
                "Use this for a full product photos folder. Uploaded images are kept in a photo library and also auto-attached to products that still miss an image.",
                "מיועד לתיקיית תמונות מלאה של המוצרים. התמונות נשמרות בספריית תמונות וגם משויכות אוטומטית למוצרים שחסרה להם תמונה.",
              )}
              {bulkUploadMessage ? <p className="mt-2 text-emerald-700">{bulkUploadMessage}</p> : null}
              {uploadError ? <p className="mt-2 text-red-700">{uploadError}</p> : null}
            </div>
          </div>

          {/* Catalog status row */}
          {rows.length > 0 ? (
            <div className="flex items-center gap-3 rounded-lg border bg-muted/30 px-4 py-3">
              <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand/15">
                <LayoutGrid className="size-4 text-brand" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">
                  {t(`${rows.length} products in catalog`, `${rows.length} מוצרים בקטלוג`)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t("Click to view, edit or delete products.", "לחצו לצפייה, עריכה או מחיקה.")}
                </p>
              </div>
              <CatalogDialog
                rows={rows}
                deletingId={deletingId}
                rowUploadingId={rowUploadingId}
                bulkUploading={bulkUploading}
                t={t}
                onUpdate={updateProduct}
                onRemove={removeProduct}
                onImageUpload={onImageUpload}
              />
            </div>
          ) : (
            !syncingUploads && (
              <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                {photoLibrary.length
                  ? t(
                      "Photos are uploaded. Save and continue — the builder will caption them in the next step. Import a CSV anytime to add names and prices first.",
                      "התמונות הועלו. אפשר לשמור ולהמשיך — הבילדר יתאר אותן בשלב הבא. אפשר לייבא CSV בכל עת כדי להוסיף שמות ומחירים קודם.",
                    )
                  : t("Import a CSV or upload photos to start adding products.", "ייבאו CSV או העלו תמונות כדי להתחיל להוסיף מוצרים.")}
              </p>
            )
          )}

          {saveError ? (
            <p className="rounded-lg border border-red-500 bg-red-50 p-3 text-sm text-red-700">
              {saveError}
            </p>
          ) : null}
          <Button
            type="button"
            onClick={saveAndContinue}
            disabled={saving || syncingUploads || (rows.length === 0 && photoLibrary.length === 0)}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {saving ? t("Saving...", "שומר...") : t("Save and continue", "שמירה והמשך")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
