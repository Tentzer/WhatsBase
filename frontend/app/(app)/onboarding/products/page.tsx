"use client";

import Papa from "papaparse";
import { useEffect, useRef, useState, type RefObject } from "react";
import { useNavigate } from "@/components/navigation-progress";
import { Loader2, Trash2, Upload } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
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
          <div className="h-full w-1/3 animate-pulse rounded-full bg-emerald-600" />
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

  const removeProduct = (id: string) => {
    setRows((prev) => prev.filter((item) => item.id !== id));
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

          <div className="space-y-3">
            {rows.map((row) => (
              <div key={row.id} className="grid gap-3 rounded-lg border p-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    value={row.nameEn}
                    onChange={(event) => updateProduct(row.id, "nameEn", event.target.value)}
                    placeholder="Name (EN)"
                  />
                  <Input
                    value={row.nameHe}
                    onChange={(event) => updateProduct(row.id, "nameHe", event.target.value)}
                    placeholder="שם (HE)"
                  />
                  <Input
                    value={row.category}
                    onChange={(event) => updateProduct(row.id, "category", event.target.value)}
                    placeholder="Category"
                  />
                  <Input
                    type="number"
                    value={row.price}
                    onChange={(event) => updateProduct(row.id, "price", event.target.value)}
                    placeholder="Price"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Label
                      className={`cursor-pointer rounded-md border px-3 py-2 text-sm hover:bg-accent ${rowUploadingId === row.id ? "pointer-events-none opacity-60" : ""}`}
                    >
                      <Upload className="me-1 inline size-4" />
                      {rowUploadingId === row.id
                        ? t("Uploading...", "מעלה...")
                        : t("Attach image", "הוספת תמונה")}
                      <Input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        disabled={rowUploadingId === row.id || bulkUploading}
                        onChange={(event) => {
                          void onImageUpload(row.id, event.target.files?.[0] ?? null);
                          event.target.value = "";
                        }}
                      />
                    </Label>
                    <span className="text-sm text-muted-foreground">
                      {row.image?.fileName ?? t("No image selected", "לא נבחרה תמונה")}
                    </span>
                    <Button type="button" variant="ghost" size="sm" onClick={() => removeProduct(row.id)}>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                  {rowUploadingId === row.id ? (
                    <UploadProgressBar
                      label={t("Uploading image...", "מעלה תמונה...")}
                      value={0}
                      indeterminate
                    />
                  ) : null}
                </div>
              </div>
            ))}
            {!rows.length ? (
              <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                {photoLibrary.length
                  ? t(
                      "Photos are uploaded. Save and continue — the builder will caption them in the next step. Import a CSV anytime to add names and prices first.",
                      "התמונות הועלו. אפשר לשמור ולהמשיך — הבילדר יתאר אותן בשלב הבא. אפשר לייבא CSV בכל עת כדי להוסיף שמות ומחירים קודם.",
                    )
                  : t("Import a CSV or upload photos to start adding products.", "ייבאו CSV או העלו תמונות כדי להתחיל להוסיף מוצרים.")}
              </p>
            ) : null}
          </div>

          <div className="space-y-2 rounded-lg border p-4">
            <p className="text-sm font-medium">
              {t("Photo library", "ספריית תמונות")} ({photoLibrary.length})
            </p>
            {!photoLibrary.length ? (
              <p className="text-sm text-muted-foreground">
                {t("No photos uploaded yet.", "עדיין לא הועלו תמונות.")}
              </p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {photoLibrary.slice(0, 12).map((photo) => (
                  <p
                    key={photo.id}
                    className="truncate text-sm text-muted-foreground"
                    title={photo.relativePath ?? photo.fileName}
                  >
                    {photo.relativePath ?? photo.fileName}
                  </p>
                ))}
                {photoLibrary.length > 12 ? (
                  <p className="text-sm text-muted-foreground">
                    {t(`+ ${photoLibrary.length - 12} more photos`, `+ עוד ${photoLibrary.length - 12} תמונות`)}
                  </p>
                ) : null}
              </div>
            )}
          </div>

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
