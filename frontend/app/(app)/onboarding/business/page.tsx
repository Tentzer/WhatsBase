"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "@/components/navigation-progress";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { DEFAULT_BUSINESS_INFO_BLOCKS, normalizeBusinessInfoBlocks } from "@/lib/business-info";
import { useLocale } from "@/lib/locale";
import { createClient } from "@/lib/supabase/client";
import { useOnboardingStore } from "@/lib/store";
import type { BusinessInfoBlock } from "@/lib/types";

function classifyApiError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("timed out")) return "Request timed out — backend may be slow or unreachable.";
  if (msg.includes("network error") || msg.includes("Failed to fetch"))
    return "Network error — backend is unreachable. Check that the tunnel is running and NEXT_PUBLIC_API_URL is current.";
  if (msg.includes("returned HTML"))
    return "Tunnel confirmation page intercepted the request. Open the backend URL in your browser once to bypass it, then retry.";
  if (msg.includes("401")) return "Authentication failed (401). Make sure you are logged in.";
  if (msg.includes("403")) return "Tenant not initialized (403). Try saving again — the first save creates the tenant.";
  return msg;
}

export default function BusinessOnboardingPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const supabase = useMemo(() => createClient(), []);
  const { setTenant, setBusinessInfo } = useOnboardingStore();
  const [tenantName, setTenantName] = useState("");
  const [tenantDescription, setTenantDescription] = useState("");
  const [blocks, setBlocks] = useState<BusinessInfoBlock[]>(DEFAULT_BUSINESS_INFO_BLOCKS);
  const [saving, setSaving] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const bootstrap = useCallback(async () => {
    setHydrating(true);
    setLoadError(null);
    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.user?.email) {
        navigate("/login");
        return;
      }
      const me = await api.getMe(session.user.email);
      if (me.tenant) {
        setTenant(me.tenant);
        setTenantName(me.tenant.name ?? "");
        setTenantDescription(me.tenant.description ?? "");
      }
      if (me.tenant) {
        const info = await api.getBusinessInfo();
        const normalized = normalizeBusinessInfoBlocks(info);
        setBlocks(normalized);
        setBusinessInfo(normalized);
      }
    } catch (error) {
      console.error("Failed to load onboarding business data:", error);
      setLoadError(classifyApiError(error));
    } finally {
      setHydrating(false);
    }
  }, [navigate, setBusinessInfo, setTenant, supabase]);

  useEffect(() => {
    const bootstrapTimer = window.setTimeout(() => {
      void bootstrap();
    }, 0);
    return () => window.clearTimeout(bootstrapTimer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveAndContinue = async () => {
    if (!tenantName.trim()) return;
    setSaving(true);
    setSaveError(null);
    try {
      const resolvedTenant = await api.createTenant(tenantName.trim(), tenantDescription.trim());
      setTenant(resolvedTenant);
      const saved = await api.saveBusinessInfo(normalizeBusinessInfoBlocks(blocks));
      const normalized = normalizeBusinessInfoBlocks(saved);
      setBusinessInfo(normalized);
      setBlocks(normalized);
      navigate("/onboarding/products");
    } catch (error) {
      console.error("Failed to save business onboarding data:", error);
      setSaveError(classifyApiError(error));
    } finally {
      setSaving(false);
    }
  };

  const updateBlock = (topic: BusinessInfoBlock["topic"], field: "content_en" | "content_he", value: string) => {
    setBlocks((prev) =>
      prev.map((item) => (item.topic === topic ? { ...item, [field]: value } : item)),
    );
  };

  if (hydrating) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      <WizardStepper />
      <Card>
        <CardHeader>
          <CardTitle>{t("Business context", "פרטי העסק")}</CardTitle>
          <CardDescription>
            {t(
              "Add your business details in English and Hebrew so the bot can answer accurately.",
              "הוסיפו מידע עסקי בעברית ובאנגלית כדי שהבוט יענה בצורה מדויקת.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="tenantName">{t("Business name", "שם העסק")}</Label>
            <Input
              id="tenantName"
              value={tenantName}
              onChange={(event) => setTenantName(event.target.value)}
              placeholder={t("Example: Urban Living", "דוגמה: אורבן ליווינג")}
            />
          </div>

          {loadError ? (
            <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                <p className="font-medium">{t("Could not load saved data", "לא ניתן לטעון נתונים שמורים")}</p>
                <p className="mt-0.5 text-xs opacity-80">{loadError}</p>
                <p className="mt-1 text-xs opacity-70">
                  {t("You can still fill in the form and save.", "ניתן להמשיך למלא את הטופס ולשמור.")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void bootstrap()}
                className="ml-1 shrink-0 rounded p-1 hover:bg-amber-100 dark:hover:bg-amber-900/40"
                title={t("Retry loading", "נסה שוב")}
              >
                <RefreshCw className="size-3.5" />
              </button>
            </div>
          ) : null}

          {saveError ? (
            <div className="flex items-start gap-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="flex-1">
                <p className="font-medium">{t("Save failed", "השמירה נכשלה")}</p>
                <p className="mt-0.5 text-xs opacity-80">{saveError}</p>
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="tenantDescription">
              {t("Business description", "תיאור העסק")}
            </Label>
            <Textarea
              id="tenantDescription"
              value={tenantDescription}
              onChange={(event) => setTenantDescription(event.target.value)}
              placeholder={t(
                "Write a few words about your business, audience, and what you sell.",
                "כתבו בכמה מילים על העסק, קהל היעד ומה אתם מוכרים.",
              )}
            />
            <p className="text-xs text-muted-foreground">
              {t(
                "This helps the Builder generate a stronger system prompt for your customer-facing agent.",
                "זה עוזר ל-Builder לייצר פרומפט מערכת איכותי יותר לסוכן שמדבר עם הלקוחות.",
              )}
            </p>
          </div>

          {blocks.map((block) => (
            <div key={block.topic} className="grid gap-3 rounded-lg border p-4">
              <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">{block.topic}</p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t("English", "אנגלית")}</Label>
                  <Textarea
                    value={block.content_en}
                    onChange={(event) => updateBlock(block.topic, "content_en", event.target.value)}
                    placeholder={t("Write in English...", "כתיבה באנגלית...")}
                  />
                </div>
                <div className="space-y-2">
                  <Label>{t("Hebrew", "עברית")}</Label>
                  <Textarea
                    value={block.content_he}
                    onChange={(event) => updateBlock(block.topic, "content_he", event.target.value)}
                    placeholder={t("Write in Hebrew...", "כתיבה בעברית...")}
                  />
                </div>
              </div>
            </div>
          ))}

          <Button
            type="button"
            onClick={saveAndContinue}
            disabled={saving || !tenantName.trim()}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            {saving ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                {t("Saving...", "שומר...")}
              </>
            ) : (
              t("Save and continue", "שמירה והמשך")
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
