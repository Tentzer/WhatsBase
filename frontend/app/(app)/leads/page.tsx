"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { cn } from "@/lib/utils";
import type {
  Lead,
  LeadAutomationSettings,
  LeadCreatePayload,
  LeadStatus,
  ProductDraft,
} from "@/lib/types";

const LEAD_STATUSES: LeadStatus[] = [
  "pending",
  "contacted",
  "qualified",
  "not_interested",
  "success",
];

export default function LeadsPage() {
  const { t } = useLocale();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [products, setProducts] = useState<ProductDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LeadStatus | "all">("all");
  const [productFilter, setProductFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [automationSettings, setAutomationSettings] = useState<LeadAutomationSettings>({
    autoReplyEnabled: true,
    reengagementEnabled: false,
  });
  const [automationSaving, setAutomationSaving] = useState<"autoReply" | "reengagement" | null>(
    null,
  );
  const [newProductId, setNewProductId] = useState<string>("");
  const [newLead, setNewLead] = useState<LeadCreatePayload>({
    fullName: "",
    phoneNumber: "",
    status: "pending",
    didBuy: false,
    source: "manual",
    notes: "",
    productIds: [],
  });

  const productNameById = useMemo(
    () =>
      new Map(
        products.map((product) => [
          product.id,
          product.nameEn || product.nameHe || product.stableKey,
        ]),
      ),
    [products],
  );

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [leadRows, productRows] = await Promise.all([
        api.getLeads({
          status: statusFilter === "all" ? undefined : statusFilter,
          q: search || undefined,
          productId: productFilter === "all" ? undefined : productFilter,
        }),
        api.getProducts(),
      ]);
      setLeads(leadRows);
      setProducts(productRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  // Automation settings are an optional enhancement: load them separately so a
  // failure here (e.g. backend not yet redeployed/migrated) never blocks the
  // core leads list from rendering.
  const loadAutomationSettings = async () => {
    try {
      const settings = await api.getLeadAutomationSettings();
      setAutomationSettings(settings);
    } catch {
      // Keep defaults; toggles simply won't reflect/persist until the backend
      // exposes the endpoint. Do not surface a page-level error for this.
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, productFilter]);

  useEffect(() => {
    void loadAutomationSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createLead = async () => {
    if (!newLead.fullName.trim() || !newLead.phoneNumber.trim()) {
      setError(t("Name and phone are required.", "שם וטלפון הם שדות חובה."));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.createLead({
        ...newLead,
        fullName: newLead.fullName.trim(),
        phoneNumber: newLead.phoneNumber.trim(),
      });
      setLeads((prev) => [created, ...prev]);
      setNewLead({
        fullName: "",
        phoneNumber: "",
        status: "pending",
        didBuy: false,
        source: "manual",
        notes: "",
        productIds: [],
      });
      setNewProductId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (leadId: string, status: LeadStatus) => {
    try {
      const updated = await api.updateLead(leadId, { status });
      setLeads((prev) => prev.map((lead) => (lead.id === leadId ? updated : lead)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const updateDidBuy = (leadId: string, didBuy: boolean) => {
    const previous = leads.find((row) => row.id === leadId);
    if (!previous || previous.didBuy === didBuy) return;

    setLeads((prev) =>
      prev.map((row) => (row.id === leadId ? { ...row, didBuy } : row)),
    );

    void api.updateLead(leadId, { didBuy }).catch((err) => {
      setLeads((prev) =>
        prev.map((row) => (row.id === leadId ? previous : row)),
      );
      setError(err instanceof Error ? err.message : String(err));
    });
  };

  const removeLead = async (leadId: string) => {
    try {
      await api.deleteLead(leadId);
      setLeads((prev) => prev.filter((lead) => lead.id !== leadId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const setAutoReplyEnabled = (nextValue: boolean) => {
    const previous = automationSettings;
    setAutomationSaving("autoReply");
    setAutomationSettings((prev) => ({ ...prev, autoReplyEnabled: nextValue }));
    void api
      .updateLeadAutomationSettings({ autoReplyEnabled: nextValue })
      .then((updated) => {
        setAutomationSettings(updated);
      })
      .catch((err) => {
        setAutomationSettings(previous);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setAutomationSaving(null));
  };

  const setReengagementEnabled = (nextValue: boolean) => {
    const previous = automationSettings;
    setAutomationSaving("reengagement");
    setAutomationSettings((prev) => ({ ...prev, reengagementEnabled: nextValue }));
    void api
      .updateLeadAutomationSettings({ reengagementEnabled: nextValue })
      .then((updated) => {
        setAutomationSettings(updated);
      })
      .catch((err) => {
        setAutomationSettings(previous);
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setAutomationSaving(null));
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("Leads", "לידים")}</CardTitle>
          <CardDescription>
            {t(
              "Manage customer leads, pipeline status, interest, and close outcomes.",
              "ניהול לידים, סטטוס פייפליין, תחומי עניין ותוצאות סגירה.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-5">
            <div className="space-y-1">
              <Label>{t("Search", "חיפוש")}</Label>
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("Name / phone", "שם / טלפון")}
              />
            </div>
            <div className="space-y-1">
              <Label>{t("Status", "סטטוס")}</Label>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as LeadStatus | "all")}
                className="h-9 w-full rounded-md border border-input bg-background text-foreground px-3 text-sm"
              >
                <option value="all">{t("All", "הכל")}</option>
                {LEAD_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label>{t("Interested product", "מוצר מתעניין")}</Label>
              <select
                value={productFilter}
                onChange={(event) => setProductFilter(event.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background text-foreground px-3 text-sm"
              >
                <option value="all">{t("All products", "כל המוצרים")}</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.nameEn || product.nameHe || product.stableKey}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2 flex items-end">
              <Button type="button" variant="outline" onClick={() => void loadData()}>
                {t("Apply filters", "החל מסננים")}
              </Button>
            </div>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 text-sm font-medium">
              {t("Automation controls", "בקרות אוטומציה")}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <button
                type="button"
                onClick={() => setReengagementEnabled(!automationSettings.reengagementEnabled)}
                disabled={automationSaving === "reengagement"}
                className={cn(
                  "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                  automationSettings.reengagementEnabled
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : "border-border bg-muted/20",
                )}
              >
                <div className="font-medium">
                  {t("Re-engage after 2 months", "יצירת קשר מחדש אחרי חודשיים")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {automationSettings.reengagementEnabled
                    ? t("Enabled", "פעיל")
                    : t("Disabled", "כבוי")}
                  {automationSaving === "reengagement" ? (
                    <Loader2 className="ml-2 inline size-3 animate-spin" />
                  ) : null}
                </div>
              </button>

              <button
                type="button"
                onClick={() => setAutoReplyEnabled(!automationSettings.autoReplyEnabled)}
                disabled={automationSaving === "autoReply"}
                className={cn(
                  "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                  automationSettings.autoReplyEnabled
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : "border-border bg-muted/20",
                )}
              >
                <div className="font-medium">
                  {t("Agent auto-reply on WhatsApp", "מענה אוטומטי בוואטסאפ")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {automationSettings.autoReplyEnabled
                    ? t("Enabled", "פעיל")
                    : t("Disabled", "כבוי")}
                  {automationSaving === "autoReply" ? (
                    <Loader2 className="ml-2 inline size-3 animate-spin" />
                  ) : null}
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium">
              <Plus className="size-4" />
              {t("Add new lead", "הוספת ליד חדש")}
            </div>
            <div className="grid gap-3 md:grid-cols-5">
              <Input
                value={newLead.fullName}
                onChange={(event) =>
                  setNewLead((prev) => ({ ...prev, fullName: event.target.value }))
                }
                placeholder={t("Full name", "שם מלא")}
              />
              <Input
                value={newLead.phoneNumber}
                onChange={(event) =>
                  setNewLead((prev) => ({ ...prev, phoneNumber: event.target.value }))
                }
                placeholder={t("Phone number", "מספר טלפון")}
              />
              <select
                value={newLead.status}
                onChange={(event) =>
                  setNewLead((prev) => ({ ...prev, status: event.target.value as LeadStatus }))
                }
                className="h-9 rounded-md border border-input bg-background text-foreground px-3 text-sm"
              >
                {LEAD_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              <Input
                value={newLead.notes}
                onChange={(event) =>
                  setNewLead((prev) => ({ ...prev, notes: event.target.value }))
                }
                placeholder={t("Quick note", "הערה קצרה")}
              />
              <Button type="button" onClick={createLead} disabled={saving}>
                {saving ? <Loader2 className="size-4 animate-spin" /> : null}
                {t("Create lead", "צור ליד")}
              </Button>
            </div>
            <div className="mt-3 space-y-1">
              <Label>{t("Interested products", "מוצרים מעניינים")}</Label>
              <div className="flex gap-2">
                <select
                  value={newProductId}
                  onChange={(event) => setNewProductId(event.target.value)}
                  className="h-9 flex-1 rounded-md border border-input bg-background text-foreground px-3 text-sm"
                >
                  <option value="">{t("Select product", "בחר מוצר")}</option>
                  {products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.nameEn || product.nameHe || product.stableKey}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    if (!newProductId) return;
                    setNewLead((prev) => ({
                      ...prev,
                      productIds: prev.productIds.includes(newProductId)
                        ? prev.productIds
                        : [...prev.productIds, newProductId],
                    }));
                    setNewProductId("");
                  }}
                >
                  {t("Add", "הוסף")}
                </Button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {newLead.productIds.map((id) => (
                  <Badge key={id} variant="outline" className="gap-1 pr-1">
                    {productNameById.get(id) ?? id.slice(0, 8)}
                    <button
                      type="button"
                      onClick={() =>
                        setNewLead((prev) => ({
                          ...prev,
                          productIds: prev.productIds.filter((pid) => pid !== id),
                        }))
                      }
                      aria-label={t("Remove product", "הסר מוצר")}
                    >
                      <X className="size-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          {error ? (
            <p className="rounded-lg border border-red-400 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </p>
          ) : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("Name", "שם")}</TableHead>
                <TableHead>{t("Phone", "טלפון")}</TableHead>
                <TableHead>{t("Status", "סטטוס")}</TableHead>
                <TableHead>{t("Interested in", "מתעניין ב")}</TableHead>
                <TableHead>{t("Bought?", "נסגר?")}</TableHead>
                <TableHead>{t("Last message", "הודעה אחרונה")}</TableHead>
                <TableHead>{t("Re-engagement", "מעורבות מחדש")}</TableHead>
                <TableHead>{t("Last summary", "סיכום שיחה")}</TableHead>
                <TableHead>{t("Actions", "פעולות")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground">
                    <Loader2 className="mx-auto size-4 animate-spin" />
                  </TableCell>
                </TableRow>
              ) : leads.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground">
                    {t("No leads yet.", "אין לידים עדיין.")}
                  </TableCell>
                </TableRow>
              ) : (
                leads.map((lead) => (
                  <TableRow key={lead.id}>
                    <TableCell className="font-medium">{lead.fullName}</TableCell>
                    <TableCell>{lead.phoneNumber}</TableCell>
                    <TableCell>
                      <select
                        value={lead.status}
                        onChange={(event) =>
                          void updateStatus(lead.id, event.target.value as LeadStatus)
                        }
                        className="h-8 rounded-md border border-input bg-background text-foreground px-2 text-xs"
                      >
                        {LEAD_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {status}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                    <TableCell className="max-w-56 whitespace-normal">
                      {lead.productIds.length ? (
                        <div className="flex flex-wrap gap-1">
                          {lead.productIds.map((id) => (
                            <Badge key={id} variant="outline">
                              {productNameById.get(id) ?? id.slice(0, 8)}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() => updateDidBuy(lead.id, !lead.didBuy)}
                        className={cn(
                          "inline-flex h-8 min-w-[5.5rem] items-center justify-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors",
                          lead.didBuy
                            ? "bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 hover:bg-emerald-500/20"
                            : "bg-muted/60 text-muted-foreground ring-1 ring-border hover:bg-muted",
                        )}
                        aria-pressed={lead.didBuy}
                        aria-label={
                          lead.didBuy
                            ? t("Marked as sold", "סומן כנסגר")
                            : t("Mark as sold", "סמן כנסגר")
                        }
                      >
                        {lead.didBuy ? <Check className="size-3.5 shrink-0" /> : null}
                        {lead.didBuy ? t("Sold", "נסגר") : t("Not yet", "טרם")}
                      </button>
                    </TableCell>
                    <TableCell>
                      {lead.lastMessageSentAt
                        ? new Date(lead.lastMessageSentAt).toLocaleString()
                        : "—"}
                    </TableCell>
                    <TableCell className="max-w-44 whitespace-normal text-xs text-muted-foreground">
                      <div>{lead.lastReengagementDecision ?? "—"}</div>
                      <div>
                        {t("Attempts", "ניסיונות")}: {lead.reengagementAttemptCount ?? 0}
                      </div>
                      <div>
                        {t("Cooldown", "השהיה")}:{" "}
                        {lead.reengagementCooldownUntil
                          ? new Date(lead.reengagementCooldownUntil).toLocaleDateString()
                          : "—"}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-80 whitespace-normal text-xs text-muted-foreground">
                      {lead.lastConversationSummary || "—"}
                    </TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void removeLead(lead.id)}
                      >
                        {t("Delete", "מחיקה")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

