import type {
  AgentStatus,
  BuildRun,
  BuildStatus,
  BusinessInfoBlock,
  MeResponse,
  ProductDraft,
  ProductImageDraft,
  Tenant,
  TestChatMessage,
  TestChatResponse,
  UserProfile,
  WhatsAppConnectRequest,
} from "@/lib/types";
import { DEMO_SELF_TEST_RESULTS } from "@/lib/mock/data";
import { loadState, randomId, updateState } from "@/lib/mock/storage";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function nowIso(): string {
  return new Date().toISOString();
}

function buildAgentReply(text: string): TestChatMessage {
  const state = loadState();
  const normalized = text.toLowerCase();
  const isHebrew = /[\u0590-\u05FF]/.test(text);

  const whiteMatches = state.products.filter((p) => {
    const source = `${p.nameEn} ${p.nameHe} ${p.colors}`.toLowerCase();
    return source.includes("white") || source.includes("לבנ");
  });

  const priceMatch = state.products.find((p) => {
    const source = `${p.nameEn} ${p.nameHe}`.toLowerCase();
    return source.includes("white") || source.includes("לבנ");
  });

  if (normalized.includes("white") || normalized.includes("לבנ")) {
    return {
      id: randomId("msg"),
      role: "assistant",
      text: isHebrew
        ? "בהחלט, הנה כמה אפשרויות בצבע לבן מהקטלוג:"
        : "Absolutely, here are white options from the catalog:",
      createdAt: nowIso(),
      cards: whiteMatches.slice(0, 3).map((product) => ({
        id: product.id,
        imageUrl: product.image?.previewUrl,
        nameHe: product.nameHe,
        nameEn: product.nameEn,
        price: product.price,
        currency: product.currency,
      })),
    };
  }

  if (normalized.includes("how much") || normalized.includes("כמה")) {
    if (!priceMatch) {
      return {
        id: randomId("msg"),
        role: "assistant",
        text: isHebrew
          ? "לא מצאתי מוצר תואם במחיר כרגע. אפשר לשאול על מוצר ספציפי?"
          : "I could not find a matching product price yet. Can you ask about a specific item?",
        createdAt: nowIso(),
      };
    }
    return {
      id: randomId("msg"),
      role: "assistant",
      text: isHebrew
        ? `${priceMatch.nameHe} עולה ${priceMatch.price} ${priceMatch.currency}.`
        : `${priceMatch.nameEn} is ${priceMatch.price} ${priceMatch.currency}.`,
      createdAt: nowIso(),
    };
  }

  return {
    id: randomId("msg"),
    role: "assistant",
    text: isHebrew
      ? "אני יכול לעזור רק עם מוצרים ומידע של החנות. רוצה שאעביר לנציג אנושי?"
      : "I can only help with this store's catalog and business information. Want a human handoff?",
    createdAt: nowIso(),
  };
}

export const mockApi = {
  async getMe(email: string): Promise<MeResponse> {
    const state = loadState();
    const user: UserProfile = state.user ?? {
      userId: randomId("user"),
      email,
      tenantId: state.tenant?.id,
    };
    updateState((prev) => ({ ...prev, user }));
    return { user, tenant: state.tenant };
  },

  async createTenant(name: string, description?: string): Promise<Tenant> {
    await delay(300);
    const state = loadState();
    const tenant: Tenant = state.tenant
      ? {
          ...state.tenant,
          name,
          description,
        }
      : { id: randomId("tenant"), name, description, createdAt: nowIso() };
    updateState((prev) => ({ ...prev, tenant, user: prev.user ? { ...prev.user, tenantId: tenant.id } : prev.user }));
    return tenant;
  },

  async getBusinessInfo(): Promise<BusinessInfoBlock[]> {
    return loadState().businessInfo;
  },

  async saveBusinessInfo(payload: BusinessInfoBlock[]): Promise<BusinessInfoBlock[]> {
    updateState((prev) => ({ ...prev, businessInfo: payload }));
    return payload;
  },

  async getProducts(): Promise<ProductDraft[]> {
    return loadState().products;
  },

  async saveProducts(products: ProductDraft[]): Promise<ProductDraft[]> {
    updateState((prev) => ({ ...prev, products }));
    return products;
  },

  async createImageDraft(file: File): Promise<ProductImageDraft> {
    const previewUrl = URL.createObjectURL(file);
    const relativePath = "webkitRelativePath" in file ? String(file.webkitRelativePath || "") : "";
    return {
      id: randomId("image"),
      fileName: file.name,
      previewUrl,
      storagePath: `mock/uploads/${file.name}`,
      relativePath: relativePath || undefined,
    };
  },

  async connectWhatsApp(payload: WhatsAppConnectRequest) {
    await delay(1500);
    const phoneSuffix = payload.instanceId.slice(-4).padStart(4, "0");
    const connection = {
      connected: true,
      phone: `9725454${phoneSuffix}`,
      intakeMode: "polling" as const,
      checkedAt: nowIso(),
    };
    updateState((prev) => ({ ...prev, whatsapp: connection }));
    return connection;
  },

  async getWhatsAppStatus() {
    return loadState().whatsapp;
  },

  async startBuild(): Promise<BuildRun> {
    const createdAt = nowIso();
    const run: BuildRun = {
      id: randomId("build"),
      status: "running",
      currentStep: "collect_assets",
      progressPct: 5,
      createdAt,
      updatedAt: createdAt,
    };
    updateState((prev) => ({ ...prev, buildRun: run, agentStatus: "building" }));
    return run;
  },

  async getBuildRun(buildRunId: string): Promise<BuildRun | undefined> {
    const run = loadState().buildRun;
    if (!run || run.id !== buildRunId) return undefined;
    return run;
  },

  async setBuildState(status: BuildStatus, progressPct: number, currentStep?: BuildRun["currentStep"]) {
    const state = loadState();
    if (!state.buildRun) return undefined;
    const report =
      status === "passed"
        ? {
            productsDetected: state.products.length,
            productsCreated: state.products.length,
            assumptions: [
              "Some product attributes were inferred from image names.",
              "Missing prices defaulted to owner-provided CSV values.",
            ],
            selfTest: DEMO_SELF_TEST_RESULTS,
          }
        : undefined;
    const updatedRun: BuildRun = {
      ...state.buildRun,
      status,
      progressPct,
      currentStep,
      report,
      updatedAt: nowIso(),
    };
    const agentStatus: AgentStatus = status === "passed" ? "live" : status === "failed" ? "failed" : "building";
    updateState((prev) => ({ ...prev, buildRun: updatedRun, agentStatus }));
    return updatedRun;
  },

  async getAgentStatus(): Promise<AgentStatus> {
    return loadState().agentStatus;
  },

  async sendTestChatMessage(text: string): Promise<TestChatResponse> {
    const userMsg: TestChatMessage = {
      id: randomId("msg"),
      role: "user",
      text,
      createdAt: nowIso(),
    };
    const reply = buildAgentReply(text);
    updateState((prev) => ({ ...prev, chat: [...prev.chat, userMsg, reply] }));
    return { reply };
  },

  async getTestChatHistory(): Promise<TestChatMessage[]> {
    return loadState().chat;
  },
};
