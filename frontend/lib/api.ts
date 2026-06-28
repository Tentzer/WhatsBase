import type {
  AgentStatus,
  BuildRun,
  BuildStatus,
  BusinessInfoBlock,
  LangfuseAnalytics,
  Lead,
  LeadAutomationEvent,
  LeadAutomationSettings,
  LeadCreatePayload,
  LeadMessage,
  LeadStatus,
  MeResponse,
  ProductDraft,
  ProductImageDraft,
  Tenant,
  TestChatMessage,
  TestChatResponse,
  WhatsAppConnectRequest,
  WhatsAppConnection,
} from "@/lib/types";
import { mockApi } from "@/lib/mock/handlers";
import { createClient } from "@/lib/supabase/client";

interface ApiClient {
  getMe: (email: string) => Promise<MeResponse>;
  createTenant: (name: string, description?: string) => Promise<Tenant>;
  getBusinessInfo: () => Promise<BusinessInfoBlock[]>;
  saveBusinessInfo: (payload: BusinessInfoBlock[]) => Promise<BusinessInfoBlock[]>;
  getProducts: () => Promise<ProductDraft[]>;
  getLeads: (params?: { status?: LeadStatus; q?: string; productId?: string }) => Promise<Lead[]>;
  createLead: (payload: LeadCreatePayload) => Promise<Lead>;
  updateLead: (
    id: string,
    payload: Partial<
      Omit<LeadCreatePayload, "productIds"> & {
        lastConversationSummary: string;
        lastMessageSentAt: string;
      }
    >,
  ) => Promise<Lead>;
  setLeadProducts: (id: string, productIds: string[]) => Promise<Lead>;
  deleteLead: (id: string) => Promise<void>;
  getLeadAutomationEvents: (id: string, limit?: number) => Promise<LeadAutomationEvent[]>;
  getLeadMessages: (leadId: string) => Promise<LeadMessage[]>;
  getLeadAutomationSettings: () => Promise<LeadAutomationSettings>;
  updateLeadAutomationSettings: (payload: {
    autoReplyEnabled?: boolean;
    reengagementEnabled?: boolean;
  }) => Promise<LeadAutomationSettings>;
  syncProductsFromUploads: () => Promise<ProductDraft[]>;
  saveProducts: (products: ProductDraft[]) => Promise<ProductDraft[]>;
  deleteProduct: (id: string) => Promise<void>;
  createImageDraft: (file: File) => Promise<ProductImageDraft>;
  connectWhatsApp: (payload: WhatsAppConnectRequest) => Promise<WhatsAppConnection>;
  getWhatsAppStatus: () => Promise<WhatsAppConnection>;
  startBuild: () => Promise<BuildRun>;
  startIncrementalBuild: () => Promise<BuildRun>;
  getBuildRun: (buildRunId: string) => Promise<BuildRun | undefined>;
  getLatestBuildRun: () => Promise<BuildRun | undefined>;
  setBuildState: (
    status: BuildStatus,
    progressPct: number,
    currentStep?: BuildRun["currentStep"],
  ) => Promise<BuildRun | undefined>;
  getAgentStatus: () => Promise<AgentStatus>;
  getLangfuseAnalytics: () => Promise<LangfuseAnalytics>;
  sendTestChatMessage: (text: string) => Promise<TestChatResponse>;
  getTestChatHistory: () => Promise<TestChatMessage[]>;
  clearTestChatHistory: () => Promise<number>;
  sendSetupAssistantMessage: (text: string) => Promise<TestChatResponse>;
  getSetupAssistantHistory: () => Promise<TestChatMessage[]>;
}

const useMockApi = process.env.NEXT_PUBLIC_USE_MOCK_API !== "false";
const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
let activeBuildRunId: string | null = null;

function toBackendUrl(path: string): string {
  const normalizedBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
  return `${normalizedBase}${path}`;
}

async function getSessionContext(): Promise<{
  token: string | null;
  userId: string | null;
  email: string | null;
}> {
  const supabase = createClient();
  // getSession() is synchronous/cached — avoids an extra Supabase network round-trip.
  // session.user contains the same JWT-decoded identity as getUser() but without
  // the extra verification call that can fail in flaky tunnel environments.
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return {
    token: session?.access_token ?? null,
    userId: session?.user?.id ?? null,
    email: session?.user?.email ?? null,
  };
}

async function requestJson<T>(
  path: string,
  init?: {
    method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
    body?: unknown;
    timeoutMs?: number;
  },
): Promise<T> {
  const { token, userId, email } = await getSessionContext();
  const abortController = new AbortController();
  const timeoutMs = init?.timeoutMs ?? 15000;
  const timeout = setTimeout(() => abortController.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(toBackendUrl(path), {
      method: init?.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        // bypass-tunnel-reminder: prevents localtunnel from returning its HTML
        // confirmation page instead of the actual API response.
        "bypass-tunnel-reminder": "true",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(userId ? { "X-Supabase-User-Id": userId } : {}),
        ...(email ? { "X-Supabase-Email": email } : {}),
      },
      signal: abortController.signal,
      body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch (err) {
    const isTimeout = err instanceof DOMException && err.name === "AbortError";
    const timeoutSec = Math.round(timeoutMs / 1000);
    throw new Error(
      isTimeout
        ? `API ${path} timed out after ${timeoutSec} s — check backend URL and tunnel`
        : `API ${path} network error — backend unreachable: ${String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("text/html")) {
      // localtunnel confirmation page or reverse-proxy error page
      throw new Error(
        `API ${path} returned HTML (${response.status}) — localtunnel may need a browser visit to bypass, or the tunnel URL is stale`,
      );
    }
    const text = await response.text();
    throw new Error(`API ${path} failed (${response.status}): ${text}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const preview = await response.text();
    throw new Error(
      `API ${path} returned non-JSON (${response.status}): ${preview.slice(0, 200)}`,
    );
  }

  return (await response.json()) as T;
}

async function requestFormData<T>(path: string, form: FormData): Promise<T> {
  const { token, userId, email } = await getSessionContext();
  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), 30000);
  let response: Response;
  try {
    response = await fetch(toBackendUrl(path), {
      method: "POST",
      headers: {
        "bypass-tunnel-reminder": "true",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(userId ? { "X-Supabase-User-Id": userId } : {}),
        ...(email ? { "X-Supabase-Email": email } : {}),
      },
      signal: abortController.signal,
      body: form,
    });
  } catch (err) {
    const isTimeout = err instanceof DOMException && err.name === "AbortError";
    throw new Error(
      isTimeout
        ? `API ${path} timed out after 30 s — check backend URL and tunnel`
        : `API ${path} network error — backend unreachable: ${String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${path} failed (${response.status}): ${text}`);
  }

  return (await response.json()) as T;
}

type ApiProductCard = {
  id: string;
  image_url?: string | null;
  name_he: string;
  name_en: string;
  price: number;
  currency: string;
  category?: string | null;
};

function mapProductCard(card: ApiProductCard) {
  return {
    id: card.id,
    imageUrl: card.image_url ?? undefined,
    nameHe: card.name_he,
    nameEn: card.name_en,
    price: Number(card.price || 0),
    currency: card.currency,
    category: card.category ?? undefined,
  };
}

function mapApiLeadToLead(lead: {
  id: string;
  full_name: string;
  phone_number: string;
  status: LeadStatus;
  did_buy: boolean;
  business_name?: string | null;
  source: string;
  notes?: string | null;
  next_follow_up_at?: string | null;
  last_message_sent_at?: string | null;
  last_conversation_summary?: string | null;
  last_reengagement_at?: string | null;
  last_reengagement_decision?: "message_again" | "do_not_message" | "uncertain" | null;
  reengagement_attempt_count?: number;
  reengagement_cooldown_until?: string | null;
  product_ids: string[];
  created_at: string;
  updated_at: string;
}): Lead {
  return {
    id: lead.id,
    fullName: lead.full_name,
    phoneNumber: lead.phone_number,
    status: lead.status,
    didBuy: lead.did_buy,
    businessName: lead.business_name ?? undefined,
    source: lead.source,
    notes: lead.notes ?? undefined,
    nextFollowUpAt: lead.next_follow_up_at ?? undefined,
    lastMessageSentAt: lead.last_message_sent_at ?? undefined,
    lastConversationSummary: lead.last_conversation_summary ?? undefined,
    lastReengagementAt: lead.last_reengagement_at ?? undefined,
    lastReengagementDecision: lead.last_reengagement_decision ?? undefined,
    reengagementAttemptCount: Number(lead.reengagement_attempt_count || 0),
    reengagementCooldownUntil: lead.reengagement_cooldown_until ?? undefined,
    productIds: lead.product_ids ?? [],
    createdAt: lead.created_at,
    updatedAt: lead.updated_at,
  };
}

type ApiBuildRun = {
  id: string;
  status: BuildStatus;
  current_step?: BuildRun["currentStep"] | null;
  progress_pct: number;
  report?: {
    products_detected: number;
    products_created: number;
    assumptions: string[];
    self_test: Array<{ question: string; answer_summary: string; passed: boolean }>;
  } | null;
  created_at: string;
  updated_at: string;
};

function mapBuildRunFromApi(res: ApiBuildRun): BuildRun {
  return {
    id: res.id,
    status: res.status,
    currentStep: res.current_step ?? undefined,
    progressPct: Number(res.progress_pct || 0),
    report: res.report
      ? {
          productsDetected: Number(res.report.products_detected || 0),
          productsCreated: Number(res.report.products_created || 0),
          assumptions: res.report.assumptions ?? [],
          selfTest: (res.report.self_test ?? []).map((item) => ({
            question: item.question,
            answerSummary: item.answer_summary,
            passed: Boolean(item.passed),
          })),
        }
      : undefined,
    createdAt: res.created_at,
    updatedAt: res.updated_at,
  };
}

function mapProductToApiPayload(product: ProductDraft) {
  return {
    stable_key: product.stableKey,
    name_he: product.nameHe,
    name_en: product.nameEn,
    category: product.category,
    price: product.price,
    currency: product.currency,
    in_stock: product.inStock,
    colors: product.colors,
    materials: product.materials,
    style: product.style,
    image: product.image
      ? {
          file_name: product.image.fileName,
          storage_path: product.image.storagePath,
          public_url: product.image.previewUrl?.startsWith("blob:")
            ? null
            : product.image.previewUrl || null,
        }
      : null,
  };
}

function mapApiProductToDraft(product: {
  id: string;
  stable_key: string;
  name_he: string;
  name_en: string;
  category: string;
  price: number;
  currency: "ILS";
  in_stock: boolean;
  colors: string;
  materials: string;
  style: string;
  image?: { file_name?: string | null; storage_path: string; public_url?: string | null } | null;
}): ProductDraft {
  return {
    id: product.id,
    stableKey: product.stable_key,
    nameHe: product.name_he,
    nameEn: product.name_en,
    category: product.category,
    price: Number(product.price || 0),
    currency: product.currency,
    inStock: product.in_stock,
    colors: product.colors,
    materials: product.materials,
    style: product.style,
    image: product.image
      ? {
          id: `img_${product.id}`,
          fileName: product.image.file_name ?? "product.jpg",
          previewUrl: product.image.public_url ?? "",
          storagePath: product.image.storage_path,
        }
      : undefined,
  };
}

const realApi: ApiClient = {
  getMe: async (email: string): Promise<MeResponse> => {
    void email;
    const res = await requestJson<{
      user: { user_id: string; email: string; tenant_id: string | null };
      tenant: { id: string; name: string; description?: string; created_at: string } | null;
    }>("/api/me");
    return {
      user: {
        userId: res.user.user_id,
        email: res.user.email,
        tenantId: res.user.tenant_id ?? undefined,
      },
      tenant: res.tenant
        ? {
            id: res.tenant.id,
            name: res.tenant.name,
            description: res.tenant.description,
            createdAt: res.tenant.created_at,
          }
        : undefined,
    };
  },
  createTenant: async (name: string, description?: string) => {
    const res = await requestJson<{ id: string; name: string; description?: string; created_at: string }>(
      "/api/tenants",
      {
        method: "POST",
        body: { name, description },
      },
    );
    return {
      id: res.id,
      name: res.name,
      description: res.description,
      createdAt: res.created_at,
    };
  },
  getBusinessInfo: async (): Promise<BusinessInfoBlock[]> => {
    const res = await requestJson<Array<{ topic: BusinessInfoBlock["topic"]; content_he: string; content_en: string }>>(
      "/api/business-info",
    );
    return res.map((item) => ({
      topic: item.topic,
      content_he: item.content_he,
      content_en: item.content_en,
    }));
  },
  saveBusinessInfo: async (payload: BusinessInfoBlock[]) => {
    const res = await requestJson<Array<{ topic: BusinessInfoBlock["topic"]; content_he: string; content_en: string }>>(
      "/api/business-info",
      {
        method: "POST",
        body: payload,
      },
    );
    return res.map((item) => ({
      topic: item.topic,
      content_he: item.content_he,
      content_en: item.content_en,
    }));
  },
  getProducts: async (): Promise<ProductDraft[]> => {
    const res = await requestJson<
      Array<{
        id: string;
        stable_key: string;
        name_he: string;
        name_en: string;
        category: string;
        price: number;
        currency: "ILS";
        in_stock: boolean;
        colors: string;
        materials: string;
        style: string;
        image?: { file_name?: string | null; storage_path: string; public_url?: string | null } | null;
      }>
    >("/api/products");
    return res.map((item) => mapApiProductToDraft(item));
  },
  getLeads: async (params): Promise<Lead[]> => {
    const search = new URLSearchParams();
    if (params?.status) {
      search.set("status", params.status);
    }
    if (params?.q?.trim()) {
      search.set("q", params.q.trim());
    }
    if (params?.productId) {
      search.set("product_id", params.productId);
    }
    const qs = search.toString();
    const res = await requestJson<
      Array<{
        id: string;
        full_name: string;
        phone_number: string;
        status: LeadStatus;
        did_buy: boolean;
        business_name?: string | null;
        source: string;
        notes?: string | null;
        next_follow_up_at?: string | null;
        last_message_sent_at?: string | null;
        last_conversation_summary?: string | null;
        last_reengagement_at?: string | null;
        last_reengagement_decision?: "message_again" | "do_not_message" | "uncertain" | null;
        reengagement_attempt_count?: number;
        reengagement_cooldown_until?: string | null;
        product_ids: string[];
        created_at: string;
        updated_at: string;
      }>
    >(`/api/leads${qs ? `?${qs}` : ""}`);
    return res.map((item) => mapApiLeadToLead(item));
  },
  createLead: async (payload: LeadCreatePayload): Promise<Lead> => {
    const res = await requestJson<{
      id: string;
      full_name: string;
      phone_number: string;
      status: LeadStatus;
      did_buy: boolean;
      business_name?: string | null;
      source: string;
      notes?: string | null;
      next_follow_up_at?: string | null;
      last_message_sent_at?: string | null;
      last_conversation_summary?: string | null;
      last_reengagement_at?: string | null;
      last_reengagement_decision?: "message_again" | "do_not_message" | "uncertain" | null;
      reengagement_attempt_count?: number;
      reengagement_cooldown_until?: string | null;
      product_ids: string[];
      created_at: string;
      updated_at: string;
    }>("/api/leads", {
      method: "POST",
      body: {
        full_name: payload.fullName,
        phone_number: payload.phoneNumber,
        status: payload.status,
        did_buy: payload.didBuy,
        business_name: payload.businessName ?? null,
        source: payload.source ?? "manual",
        notes: payload.notes ?? null,
        next_follow_up_at: payload.nextFollowUpAt ?? null,
        product_ids: payload.productIds,
      },
    });
    return mapApiLeadToLead(res);
  },
  updateLead: async (id, payload): Promise<Lead> => {
    const res = await requestJson<{
      id: string;
      full_name: string;
      phone_number: string;
      status: LeadStatus;
      did_buy: boolean;
      business_name?: string | null;
      source: string;
      notes?: string | null;
      next_follow_up_at?: string | null;
      last_message_sent_at?: string | null;
      last_conversation_summary?: string | null;
      last_reengagement_at?: string | null;
      last_reengagement_decision?: "message_again" | "do_not_message" | "uncertain" | null;
      reengagement_attempt_count?: number;
      reengagement_cooldown_until?: string | null;
      product_ids: string[];
      created_at: string;
      updated_at: string;
    }>(`/api/leads/${id}`, {
      method: "PATCH",
      body: {
        ...(payload.fullName !== undefined ? { full_name: payload.fullName } : {}),
        ...(payload.phoneNumber !== undefined ? { phone_number: payload.phoneNumber } : {}),
        ...(payload.status !== undefined ? { status: payload.status } : {}),
        ...(payload.didBuy !== undefined ? { did_buy: payload.didBuy } : {}),
        ...(payload.businessName !== undefined ? { business_name: payload.businessName } : {}),
        ...(payload.source !== undefined ? { source: payload.source } : {}),
        ...(payload.notes !== undefined ? { notes: payload.notes } : {}),
        ...(payload.nextFollowUpAt !== undefined ? { next_follow_up_at: payload.nextFollowUpAt } : {}),
        ...(payload.lastConversationSummary !== undefined
          ? { last_conversation_summary: payload.lastConversationSummary }
          : {}),
        ...(payload.lastMessageSentAt !== undefined
          ? { last_message_sent_at: payload.lastMessageSentAt }
          : {}),
      },
    });
    return mapApiLeadToLead(res);
  },
  setLeadProducts: async (id, productIds): Promise<Lead> => {
    const res = await requestJson<{
      id: string;
      full_name: string;
      phone_number: string;
      status: LeadStatus;
      did_buy: boolean;
      business_name?: string | null;
      source: string;
      notes?: string | null;
      next_follow_up_at?: string | null;
      last_message_sent_at?: string | null;
      last_conversation_summary?: string | null;
      product_ids: string[];
      created_at: string;
      updated_at: string;
    }>(`/api/leads/${id}/products`, {
      method: "PUT",
      body: { product_ids: productIds },
    });
    return mapApiLeadToLead(res);
  },
  deleteLead: async (id: string): Promise<void> => {
    await requestJson<void>(`/api/leads/${id}`, { method: "DELETE" });
  },
  getLeadAutomationEvents: async (id: string, limit = 20): Promise<LeadAutomationEvent[]> => {
    const search = new URLSearchParams();
    search.set("limit", String(limit));
    const res = await requestJson<
      Array<{
        id: string;
        lead_id: string;
        automation_type: string;
        decision: "message_again" | "do_not_message" | "uncertain";
        reason?: string | null;
        scheduled_for?: string | null;
        sent_at?: string | null;
        idempotency_key: string;
        payload_json?: Record<string, unknown> | null;
        created_at: string;
      }>
    >(`/api/leads/${id}/automation-events?${search.toString()}`);
    return res.map((row) => ({
      id: row.id,
      leadId: row.lead_id,
      automationType: row.automation_type,
      decision: row.decision,
      reason: row.reason ?? undefined,
      scheduledFor: row.scheduled_for ?? undefined,
      sentAt: row.sent_at ?? undefined,
      idempotencyKey: row.idempotency_key,
      payloadJson: row.payload_json ?? {},
      createdAt: row.created_at,
    }));
  },
  getLeadMessages: async (leadId: string): Promise<LeadMessage[]> => {
    const res = await requestJson<
      Array<{
        id: string;
        direction: "inbound" | "outbound";
        type: "text" | "image";
        content: string | null;
        media_url: string | null;
        created_at: string;
      }>
    >(`/api/leads/${leadId}/messages`);
    return res.map((row) => ({
      id: row.id,
      direction: row.direction,
      type: row.type,
      content: row.content,
      mediaUrl: row.media_url,
      createdAt: row.created_at,
    }));
  },
  getLeadAutomationSettings: async (): Promise<LeadAutomationSettings> => {
    const res = await requestJson<{
      auto_reply_enabled: boolean;
      reengagement_enabled: boolean;
    }>("/api/leads/automation/settings");
    return {
      autoReplyEnabled: res.auto_reply_enabled,
      reengagementEnabled: res.reengagement_enabled,
    };
  },
  updateLeadAutomationSettings: async (payload): Promise<LeadAutomationSettings> => {
    const res = await requestJson<{
      auto_reply_enabled: boolean;
      reengagement_enabled: boolean;
    }>("/api/leads/automation/settings", {
      method: "PATCH",
      body: {
        ...(payload.autoReplyEnabled !== undefined
          ? { auto_reply_enabled: payload.autoReplyEnabled }
          : {}),
        ...(payload.reengagementEnabled !== undefined
          ? { reengagement_enabled: payload.reengagementEnabled }
          : {}),
      },
    });
    return {
      autoReplyEnabled: res.auto_reply_enabled,
      reengagementEnabled: res.reengagement_enabled,
    };
  },
  syncProductsFromUploads: async (): Promise<ProductDraft[]> => {
    const res = await requestJson<
      Array<{
        id: string;
        stable_key: string;
        name_he: string;
        name_en: string;
        category: string;
        price: number;
        currency: "ILS";
        in_stock: boolean;
        colors: string;
        materials: string;
        style: string;
        image?: { file_name?: string | null; storage_path: string; public_url?: string | null } | null;
      }>
    >("/api/products/sync-uploads", { method: "POST", timeoutMs: 120000 });
    return res.map((item) => mapApiProductToDraft(item));
  },
  saveProducts: async (products: ProductDraft[]) => {
    const res = await requestJson<
      Array<{
        id: string;
        stable_key: string;
        name_he: string;
        name_en: string;
        category: string;
        price: number;
        currency: "ILS";
        in_stock: boolean;
        colors: string;
        materials: string;
        style: string;
        image?: { file_name?: string | null; storage_path: string; public_url?: string | null } | null;
      }>
    >("/api/products", {
      method: "POST",
      body: products.map((item) => mapProductToApiPayload(item)),
      timeoutMs: 120000,
    });
    return res.map((item) => mapApiProductToDraft(item));
  },
  deleteProduct: async (id: string): Promise<void> => {
    await requestJson<void>(`/api/products/${id}`, { method: "DELETE" });
  },
  createImageDraft: async (file: File): Promise<ProductImageDraft> => {
    const form = new FormData();
    form.append("file", file);
    const res = await requestFormData<{
      file_name: string;
      storage_path: string;
      public_url: string;
    }>("/api/products/upload-image", form);
    return {
      id: `img_${Date.now()}`,
      fileName: res.file_name,
      previewUrl: res.public_url,
      storagePath: res.storage_path,
    };
  },
  connectWhatsApp: async (payload: WhatsAppConnectRequest): Promise<WhatsAppConnection> => {
    const res = await requestJson<{
      connected: boolean;
      phone: string | null;
      intake_mode: "polling" | "webhook";
      checked_at: string | null;
    }>("/api/whatsapp/connect", {
      method: "POST",
      body: {
        instance_id: payload.instanceId,
        token: payload.token,
      },
    });
    return {
      connected: res.connected,
      phone: res.phone ?? undefined,
      intakeMode: res.intake_mode,
      checkedAt: res.checked_at ?? undefined,
    };
  },
  getWhatsAppStatus: async (): Promise<WhatsAppConnection> => {
    const res = await requestJson<{
      connected: boolean;
      phone: string | null;
      intake_mode: "polling" | "webhook";
      checked_at: string | null;
    }>("/api/whatsapp/status");
    return {
      connected: res.connected,
      phone: res.phone ?? undefined,
      intakeMode: res.intake_mode,
      checkedAt: res.checked_at ?? undefined,
    };
  },
  startBuild: async (): Promise<BuildRun> => {
    const res = await requestJson<ApiBuildRun>("/api/build", { method: "POST" });
    activeBuildRunId = res.id;
    return mapBuildRunFromApi(res);
  },
  startIncrementalBuild: async (): Promise<BuildRun> => {
    const res = await requestJson<ApiBuildRun>("/api/build/incremental", { method: "POST" });
    activeBuildRunId = res.id;
    return mapBuildRunFromApi(res);
  },
  getBuildRun: async (buildRunId: string): Promise<BuildRun | undefined> => {
    const res = await requestJson<ApiBuildRun>(`/api/build-runs/${buildRunId}`, {
      timeoutMs: 30000,
    });
    activeBuildRunId = res.id;
    return mapBuildRunFromApi(res);
  },
  getLatestBuildRun: async (): Promise<BuildRun | undefined> => {
    const res = await requestJson<ApiBuildRun | null>("/api/build-runs/latest", {
      timeoutMs: 30000,
    });
    if (!res) return undefined;
    activeBuildRunId = res.id;
    return mapBuildRunFromApi(res);
  },
  setBuildState: async (status, progressPct, currentStep): Promise<BuildRun | undefined> => {
    const currentBuildId = activeBuildRunId;
    if (!currentBuildId) {
      return undefined;
    }
    const res = await requestJson<ApiBuildRun>(`/api/build-runs/${currentBuildId}`, {
      method: "PATCH",
      body: {
        status,
        progress_pct: progressPct,
        current_step: currentStep ?? null,
      },
    });
    return mapBuildRunFromApi(res);
  },
  getAgentStatus: async (): Promise<AgentStatus> => {
    const res = await requestJson<{ status: AgentStatus }>("/api/agents/status");
    return res.status;
  },
  getLangfuseAnalytics: async (): Promise<LangfuseAnalytics> => {
    const res = await requestJson<{
      total_cost_this_month_usd: number;
      cost_by_model: Array<{ model_name: string; calls: number; total_cost_usd: number }>;
      daily_usage_last_7_days: Array<{ date: string; calls: number }>;
      latency_by_name: Array<{ name: string; p50_ms: number; p95_ms: number; calls: number }>;
    }>("/api/langfuse/analytics");
    return {
      totalCostThisMonthUsd: Number(res.total_cost_this_month_usd || 0),
      costByModel: res.cost_by_model.map((item) => ({
        modelName: item.model_name,
        calls: Number(item.calls || 0),
        totalCostUsd: Number(item.total_cost_usd || 0),
      })),
      dailyUsageLast7Days: res.daily_usage_last_7_days.map((item) => ({
        date: item.date,
        calls: Number(item.calls || 0),
      })),
      latencyByName: (res.latency_by_name ?? []).map((item) => ({
        name: item.name,
        p50Ms: Number(item.p50_ms || 0),
        p95Ms: Number(item.p95_ms || 0),
        calls: Number(item.calls || 0),
      })),
    };
  },
  sendTestChatMessage: async (text: string): Promise<TestChatResponse> => {
    const res = await requestJson<{
      reply: {
        id: string;
        role: "assistant";
        text: string;
        created_at: string;
        cards?: ApiProductCard[] | null;
      };
    }>("/api/test-chat", {
      method: "POST",
      body: { text },
    });
    return {
      reply: {
        id: res.reply.id,
        role: "assistant",
        text: res.reply.text,
        createdAt: res.reply.created_at,
        cards: (res.reply.cards ?? []).map(mapProductCard),
      },
    };
  },
  getTestChatHistory: async (): Promise<TestChatMessage[]> => {
    const res = await requestJson<
      Array<{
        id: string;
        role: "user" | "assistant";
        text: string;
        created_at: string;
        cards?: ApiProductCard[] | null;
      }>
    >("/api/test-chat/history");
    return res.map((item) => ({
      id: item.id,
      role: item.role,
      text: item.text,
      createdAt: item.created_at,
      cards: item.cards?.map(mapProductCard),
    }));
  },
  clearTestChatHistory: async (): Promise<number> => {
    const res = await requestJson<{ deleted: number }>("/api/test-chat/clear", {
      method: "POST",
    });
    return res.deleted;
  },
  sendSetupAssistantMessage: async (text: string): Promise<TestChatResponse> => {
    const res = await requestJson<{
      reply: {
        id: string;
        role: "assistant";
        text: string;
        created_at: string;
      };
    }>("/api/setup-assistant/chat", {
      method: "POST",
      body: { text },
    });
    return {
      reply: {
        id: res.reply.id,
        role: "assistant",
        text: res.reply.text,
        createdAt: res.reply.created_at,
      },
    };
  },
  getSetupAssistantHistory: async (): Promise<TestChatMessage[]> => {
    const res = await requestJson<
      Array<{
        id: string;
        role: "user" | "assistant";
        text: string;
        created_at: string;
      }>
    >("/api/setup-assistant/history");
    return res.map((item) => ({
      id: item.id,
      role: item.role,
      text: item.text,
      createdAt: item.created_at,
    }));
  },
};

export const api: ApiClient = useMockApi
  ? ({
      ...(mockApi as ApiClient),
      getLangfuseAnalytics: async (): Promise<LangfuseAnalytics> => ({
        totalCostThisMonthUsd: 0,
        costByModel: [],
        dailyUsageLast7Days: [],
        latencyByName: [],
      }),
      getLeadAutomationSettings: async (): Promise<LeadAutomationSettings> => ({
        autoReplyEnabled: true,
        reengagementEnabled: false,
      }),
      updateLeadAutomationSettings: async (payload): Promise<LeadAutomationSettings> => ({
        autoReplyEnabled: payload.autoReplyEnabled ?? true,
        reengagementEnabled: payload.reengagementEnabled ?? false,
      }),
      getLeadMessages: async (): Promise<LeadMessage[]> => [],
    } as ApiClient)
  : realApi;
export { baseUrl };
