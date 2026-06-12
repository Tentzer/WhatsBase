import type {
  AgentStatus,
  BuildRun,
  BusinessInfoBlock,
  ProductDraft,
  Tenant,
  TestChatMessage,
  UserProfile,
  WhatsAppConnection,
} from "@/lib/types";
import { DEMO_BUSINESS_INFO, DEMO_PRODUCTS } from "@/lib/mock/data";

const KEY = "whatsbase.mock.v1";

export interface MockDbState {
  tenant?: Tenant;
  user?: UserProfile;
  businessInfo: BusinessInfoBlock[];
  products: ProductDraft[];
  whatsapp: WhatsAppConnection;
  agentStatus: AgentStatus;
  buildRun?: BuildRun;
  chat: TestChatMessage[];
}

const defaultState: MockDbState = {
  businessInfo: DEMO_BUSINESS_INFO,
  products: DEMO_PRODUCTS,
  whatsapp: {
    connected: false,
    intakeMode: "polling",
  },
  agentStatus: "building",
  chat: [],
};

export function loadState(): MockDbState {
  if (typeof window === "undefined") return defaultState;
  const raw = window.localStorage.getItem(KEY);
  if (!raw) return defaultState;
  try {
    return { ...defaultState, ...JSON.parse(raw) } as MockDbState;
  } catch {
    return defaultState;
  }
}

export function saveState(state: MockDbState): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(state));
}

export function updateState(mutator: (state: MockDbState) => MockDbState): MockDbState {
  const next = mutator(loadState());
  saveState(next);
  return next;
}

export function randomId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}
