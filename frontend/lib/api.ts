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
  setBuildState: (
    status: BuildStatus,
    progressPct: number,
    currentStep?: BuildRun["currentStep"],
  ) => Promise<BuildRun | undefined>;
  getAgentStatus: () => Promise<AgentStatus>;
  getLangfuseAnalytics: () => Promise<LangfuseAnalytics>;
  sendTestChatMessage: (text: string) => Promise<TestChatResponse>;
  getTestChatHistory: () => Promise<TestChatMessage[]>;
}

const useMockApi = process.env.NEXT_PUBLIC_USE_MOCK_API !== "false";
const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function notWired(endpoint: string): Promise<never> {
  throw new Error(`Real API not wired yet for ${endpoint}. Set NEXT_PUBLIC_USE_MOCK_API=true.`);
}

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
    method?: "GET" | "POST" | "PATCH";
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

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const preview = await response.text();
    throw new Error(
      `API ${path} returned non-JSON (${response.status}): ${preview.slice(0, 200)}`,
    );
  }

  return (await response.json()) as T;
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
          public_url: product.image.previewUrl || null,
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
  createImageDraft: async (file: File) => {
    return mockApi.createImageDraft(file);
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
  startBuild: async (): Promise<BuildRun> => notWired("POST /api/build"),
  getBuildRun: async (buildRunId: string): Promise<BuildRun | undefined> => {
    void buildRunId;
    return notWired("GET /api/build-runs/:id");
  },
  setBuildState: async (status, progressPct, currentStep): Promise<BuildRun | undefined> => {
    void status;
    void progressPct;
    void currentStep;
    return notWired("PATCH /api/build-runs/:id");
  },
  getAgentStatus: async (): Promise<AgentStatus> => notWired("GET /api/agents/status"),
  getLangfuseAnalytics: async (): Promise<LangfuseAnalytics> => {
    const res = await requestJson<{
      total_cost_this_month_usd: number;
      cost_by_model: Array<{ model_name: string; calls: number; total_cost_usd: number }>;
      daily_usage_last_7_days: Array<{ date: string; calls: number }>;
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
    };
  },
  sendTestChatMessage: async (text: string): Promise<TestChatResponse> => {
    void text;
    return notWired("POST /api/test-chat");
  },
  getTestChatHistory: async (): Promise<TestChatMessage[]> => notWired("GET /api/test-chat/history"),
};

export const api: ApiClient = useMockApi
  ? ({
      ...(mockApi as ApiClient),
      getLangfuseAnalytics: async (): Promise<LangfuseAnalytics> => ({
        totalCostThisMonthUsd: 0,
        costByModel: [],
        dailyUsageLast7Days: [],
      }),
    } as ApiClient)
  : realApi;
export { baseUrl };
