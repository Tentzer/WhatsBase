import type {
  AgentStatus,
  BuildRun,
  BuildStatus,
  BusinessInfoBlock,
  LangfuseAnalytics,
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
  saveProducts: (products: ProductDraft[]) => Promise<ProductDraft[]>;
  createImageDraft: (file: File) => Promise<ProductImageDraft>;
  connectWhatsApp: (payload: WhatsAppConnectRequest) => Promise<WhatsAppConnection>;
  getWhatsAppStatus: () => Promise<WhatsAppConnection>;
  startBuild: () => Promise<BuildRun>;
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
  clearTestChatHistory: () => Promise<void>;
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
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    body?: unknown;
  },
): Promise<T> {
  const { token, userId, email } = await getSessionContext();
  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), 15000);
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
    throw new Error(
      isTimeout
        ? `API ${path} timed out after 15 s — check backend URL and tunnel`
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
    });
    return res.map((item) => mapApiProductToDraft(item));
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
  getBuildRun: async (buildRunId: string): Promise<BuildRun | undefined> => {
    const res = await requestJson<ApiBuildRun>(`/api/build-runs/${buildRunId}`);
    activeBuildRunId = res.id;
    return mapBuildRunFromApi(res);
  },
  getLatestBuildRun: async (): Promise<BuildRun | undefined> => {
    const res = await requestJson<ApiBuildRun | null>("/api/build-runs/latest");
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
  clearTestChatHistory: async (): Promise<void> => {
    await requestJson<void>("/api/test-chat/history", { method: "DELETE" });
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
    } as ApiClient)
  : realApi;
export { baseUrl };
