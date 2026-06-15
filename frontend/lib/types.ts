export type Locale = "en" | "he";

export type BuildStep =
  | "collect_assets"
  | "caption_images"
  | "index_embeddings"
  | "run_self_test"
  | "finalize";

export type BuildStatus = "queued" | "running" | "passed" | "failed";
export type AgentStatus = "building" | "live" | "failed";

export interface Tenant {
  id: string;
  name: string;
  description?: string;
  createdAt: string;
}

export interface UserProfile {
  userId: string;
  email: string;
  tenantId?: string;
}

export interface MeResponse {
  user: UserProfile;
  tenant?: Tenant;
}

export interface BusinessInfoBlock {
  topic: "hours" | "location" | "policy" | "faq" | "other";
  content_he: string;
  content_en: string;
}

export interface ProductImageDraft {
  id: string;
  fileName: string;
  previewUrl: string;
  storagePath: string;
  relativePath?: string;
}

export interface ProductDraft {
  id: string;
  stableKey: string;
  nameHe: string;
  nameEn: string;
  category: string;
  price: number;
  currency: "ILS";
  inStock: boolean;
  colors: string;
  materials: string;
  style: string;
  image?: ProductImageDraft;
}

export type LeadStatus =
  | "pending"
  | "contacted"
  | "qualified"
  | "not_interested"
  | "success";

export interface Lead {
  id: string;
  fullName: string;
  phoneNumber: string;
  status: LeadStatus;
  didBuy: boolean;
  businessName?: string;
  source: string;
  notes?: string;
  nextFollowUpAt?: string;
  lastMessageSentAt?: string;
  lastConversationSummary?: string;
  productIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface LeadCreatePayload {
  fullName: string;
  phoneNumber: string;
  status: LeadStatus;
  didBuy: boolean;
  businessName?: string;
  source?: string;
  notes?: string;
  nextFollowUpAt?: string;
  productIds: string[];
}

export interface WhatsAppConnectRequest {
  instanceId: string;
  token: string;
}

export interface WhatsAppConnection {
  connected: boolean;
  phone?: string;
  intakeMode: "polling" | "webhook";
  checkedAt?: string;
}

export interface BuildQuestionResult {
  question: string;
  answerSummary: string;
  passed: boolean;
}

export interface BuildReport {
  productsDetected: number;
  productsCreated: number;
  assumptions: string[];
  selfTest: BuildQuestionResult[];
}

export interface BuildRun {
  id: string;
  status: BuildStatus;
  currentStep?: BuildStep;
  progressPct: number;
  report?: BuildReport;
  createdAt: string;
  updatedAt: string;
}

export interface ProductCard {
  id: string;
  imageUrl?: string;
  nameHe: string;
  nameEn: string;
  price: number;
  currency: string;
  category?: string;
}

export interface TestChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
  cards?: ProductCard[];
}

export interface TestChatResponse {
  reply: TestChatMessage;
}

export interface LangfuseModelCost {
  modelName: string;
  calls: number;
  totalCostUsd: number;
}

export interface LangfuseDailyUsage {
  date: string;
  calls: number;
}

export interface LangfuseLatency {
  name: string;
  p50Ms: number;
  p95Ms: number;
  calls: number;
}

export interface LangfuseAnalytics {
  totalCostThisMonthUsd: number;
  costByModel: LangfuseModelCost[];
  dailyUsageLast7Days: LangfuseDailyUsage[];
  latencyByName: LangfuseLatency[];
}
