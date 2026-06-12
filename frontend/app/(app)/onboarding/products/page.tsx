"use client";

import Papa from "papaparse";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2, Upload } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { useOnboardingStore } from "@/lib/store";
import type { ProductDraft, ProductImageDraft } from "@/lib/types";

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

export default function ProductsOnboardingPage() {
  const router = useRouter();
  const { t } = useLocale();
  const { products, setProducts, catalogPhotos, setCatalogPhotos } = useOnboardingStore();
  const [rows, setRows] = useState<ProductDraft[]>(products);
  const [photoLibrary, setPhotoLibrary] = useState<ProductImageDraft[]>(catalogPhotos);
  const [saving, setSaving] = useState(false);
  const [bulkUploading, setBulkUploading] = useState(false);
  const [bulkUploadMessage, setBulkUploadMessage] = useState<string | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!products.length) {
      void api.getProducts().then((items) => setRows(items));
    }
  }, [products.length]);

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

  const autoAttachImages = (items: ProductDraft[], images: ProductImageDraft[]) => {
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

  const onImageUpload = async (index: number, file: File | null) => {
    if (!file) return;
    const imageDraft = await api.createImageDraft(file);
    const next = [...rows];
    next[index] = { ...next[index], image: imageDraft };
    setRows(next);
    setPhotoLibrary((prev) => mergePhotoLibrary(prev, [imageDraft]));
  };

  const onBulkImageUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (!imageFiles.length) {
      setBulkUploadMessage(t("No image files were selected.", "לא נבחרו קבצי תמונה."));
      return;
    }

    setBulkUploading(true);
    setBulkUploadMessage(null);

    const drafts = await Promise.all(imageFiles.map((file) => api.createImageDraft(file)));
    setPhotoLibrary((prev) => mergePhotoLibrary(prev, drafts));

    setRows((prev) => {
      const result = autoAttachImages(prev, drafts);
      setBulkUploadMessage(
        t(
          `Uploaded ${drafts.length} photos. Auto-attached ${result.attachedCount} to products without images.`,
          `הועלו ${drafts.length} תמונות. ${result.attachedCount} צורפו אוטומטית למוצרים בלי תמונה.`,
        ),
      );
      return result.items;
    });

    setBulkUploading(false);
  };

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
      const saved = await api.saveProducts(rows);
      setProducts(saved);
      setCatalogPhotos(photoLibrary);
      router.push("/onboarding/whatsapp");
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
              <Input type="file" accept=".csv" onChange={(event) => onCsvUpload(event.target.files?.[0] ?? null)} />
            </div>
            <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              {t(
                "CSV columns: stable_key, name_he, name_en, category, price, currency, in_stock, colors, materials, style, image.",
                "עמודות CSV: stable_key, name_he, name_en, category, price, currency, in_stock, colors, materials, style, image.",
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>{t("Upload many photos", "העלאת תמונות מרובות")}</Label>
              <Input
                type="file"
                accept="image/*"
                multiple
                onChange={(event) => onBulkImageUpload(event.target.files)}
                disabled={bulkUploading}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("Upload a full folder", "העלאת תיקייה מלאה")}</Label>
              <input
                ref={folderInputRef}
                type="file"
                multiple
                accept="image/*"
                onChange={(event) => onBulkImageUpload(event.target.files)}
                disabled={bulkUploading}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm text-foreground transition-colors outline-none file:hidden focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground sm:col-span-2">
              {t(
                "Use this for a full product photos folder. Uploaded images are kept in a photo library and also auto-attached to products that still miss an image.",
                "מיועד לתיקיית תמונות מלאה של המוצרים. התמונות נשמרות בספריית תמונות וגם משויכות אוטומטית למוצרים שחסרה להם תמונה.",
              )}
              {bulkUploadMessage ? <p className="mt-2 text-emerald-700">{bulkUploadMessage}</p> : null}
            </div>
          </div>

          <div className="space-y-3">
            {rows.map((row, index) => (
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
                <div className="flex flex-wrap items-center gap-2">
                  <Label className="cursor-pointer rounded-md border px-3 py-2 text-sm hover:bg-accent">
                    <Upload className="me-1 inline size-4" />
                    {t("Attach image", "הוספת תמונה")}
                    <Input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(event) => onImageUpload(index, event.target.files?.[0] ?? null)}
                    />
                  </Label>
                  <span className="text-sm text-muted-foreground">
                    {row.image?.fileName ?? t("No image selected", "לא נבחרה תמונה")}
                  </span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => removeProduct(row.id)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
            {!rows.length ? (
              <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                {t("Import a CSV to start adding products.", "ייבאו CSV כדי להתחיל להוסיף מוצרים.")}
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
            disabled={saving || rows.length === 0}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {saving ? t("Saving...", "שומר...") : t("Save and continue", "שמירה והמשך")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
