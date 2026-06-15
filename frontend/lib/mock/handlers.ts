import type {
  AgentStatus,
  BuildRun,
  BuildStatus,
  BusinessInfoBlock,
  Lead,
  LeadCreatePayload,
  LeadStatus,
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
let mockLeads: Lead[] = [];

function nowIso(): string {
  return new Date().toISOString();
}

function advanceMockBuild(status: BuildStatus, progressPct: number, currentStep?: BuildRun["currentStep"]) {
  const state = loadState();
  if (!state.buildRun) return;
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

  async getLeads(params?: { status?: LeadStatus; q?: string }): Promise<Lead[]> {
    let rows = [...mockLeads];
    if (params?.status) {
      rows = rows.filter((lead) => lead.status === params.status);
    }
    if (params?.q?.trim()) {
      const q = params.q.toLowerCase();
      rows = rows.filter(
        (lead) =>
          lead.fullName.toLowerCase().includes(q) ||
          lead.phoneNumber.toLowerCase().includes(q) ||
          (lead.notes ?? "").toLowerCase().includes(q),
      );
    }
    return rows.sort((a, b) => (a.updatedAt > b.updatedAt ? -1 : 1));
  },

  async createLead(payload: LeadCreatePayload): Promise<Lead> {
    const now = nowIso();
    const lead: Lead = {
      id: randomId("lead"),
      fullName: payload.fullName,
      phoneNumber: payload.phoneNumber,
      status: payload.status,
      didBuy: payload.didBuy,
      businessName: payload.businessName,
      source: payload.source ?? "manual",
      notes: payload.notes,
      nextFollowUpAt: payload.nextFollowUpAt,
      lastMessageSentAt: now,
      lastConversationSummary: undefined,
      productIds: payload.productIds ?? [],
      createdAt: now,
      updatedAt: now,
    };
    mockLeads = [lead, ...mockLeads];
    return lead;
  },

  async updateLead(
    id: string,
    payload: Partial<
      Omit<LeadCreatePayload, "productIds"> & {
        lastConversationSummary: string;
        lastMessageSentAt: string;
      }
    >,
  ): Promise<Lead> {
    const idx = mockLeads.findIndex((lead) => lead.id === id);
    if (idx < 0) {
      throw new Error("Lead not found");
    }
    const prev = mockLeads[idx];
    const next: Lead = {
      ...prev,
      fullName: payload.fullName ?? prev.fullName,
      phoneNumber: payload.phoneNumber ?? prev.phoneNumber,
      status: payload.status ?? prev.status,
      didBuy: payload.didBuy ?? prev.didBuy,
      businessName: payload.businessName ?? prev.businessName,
      source: payload.source ?? prev.source,
      notes: payload.notes ?? prev.notes,
      nextFollowUpAt: payload.nextFollowUpAt ?? prev.nextFollowUpAt,
      lastConversationSummary:
        payload.lastConversationSummary ?? prev.lastConversationSummary,
      lastMessageSentAt: payload.lastMessageSentAt ?? prev.lastMessageSentAt,
      updatedAt: nowIso(),
    };
    mockLeads[idx] = next;
    return next;
  },

  async setLeadProducts(id: string, productIds: string[]): Promise<Lead> {
    const idx = mockLeads.findIndex((lead) => lead.id === id);
    if (idx < 0) {
      throw new Error("Lead not found");
    }
    const next: Lead = {
      ...mockLeads[idx],
      productIds: [...productIds],
      updatedAt: nowIso(),
    };
    mockLeads[idx] = next;
    return next;
  },

  async deleteLead(id: string): Promise<void> {
    mockLeads = mockLeads.filter((lead) => lead.id !== id);
  },

  async saveProducts(products: ProductDraft[]): Promise<ProductDraft[]> {
    updateState((prev) => ({ ...prev, products }));
    return products;
  },

  async deleteProduct(id: string): Promise<void> {
    updateState((prev) => ({ ...prev, products: prev.products.filter((p) => p.id !== id) }));
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

    const timeline = [
      { step: "collect_assets" as const, progress: 15 },
      { step: "caption_images" as const, progress: 45 },
      { step: "index_embeddings" as const, progress: 70 },
      { step: "run_self_test" as const, progress: 92 },
      { step: "finalize" as const, progress: 100 },
    ];

    timeline.forEach((point, index) => {
      window.setTimeout(() => {
        const status = point.progress === 100 ? "passed" : "running";
        advanceMockBuild(status, point.progress, point.step);
      }, (index + 1) * 3500);
    });

    return run;
  },

  async startIncrementalBuild(): Promise<BuildRun> {
    const createdAt = nowIso();
    const run: BuildRun = {
      id: randomId("build"),
      status: "running",
      currentStep: "index_embeddings",
      progressPct: 30,
      createdAt,
      updatedAt: createdAt,
    };
    updateState((prev) => ({ ...prev, buildRun: run }));

    window.setTimeout(() => {
      advanceMockBuild("passed", 100, "finalize");
    }, 2500);

    return run;
  },

  async getBuildRun(buildRunId: string): Promise<BuildRun | undefined> {
    const run = loadState().buildRun;
    if (!run || run.id !== buildRunId) return undefined;
    return run;
  },

  async getLatestBuildRun(): Promise<BuildRun | undefined> {
    return loadState().buildRun;
  },

  async setBuildState(status: BuildStatus, progressPct: number, currentStep?: BuildRun["currentStep"]) {
    advanceMockBuild(status, progressPct, currentStep);
    return loadState().buildRun;
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

  async clearTestChatHistory(): Promise<number> {
    updateState((prev) => ({ ...prev, chat: [] }));
    return 0;
  },

  async sendSetupAssistantMessage(text: string): Promise<TestChatResponse> {
    const userMsg: TestChatMessage = {
      id: randomId("msg"),
      role: "user",
      text,
      createdAt: nowIso(),
    };
    const reply: TestChatMessage = {
      id: randomId("msg"),
      role: "assistant",
      text: "I can help with onboarding steps: business info, products, WhatsApp connect, and build. What should we do next?",
      createdAt: nowIso(),
    };
    updateState((prev) => ({ ...prev, chat: [...prev.chat, userMsg, reply] }));
    return { reply };
  },
  async getSetupAssistantHistory(): Promise<TestChatMessage[]> {
    return loadState().chat;
  },
};
