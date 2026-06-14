"use client";

import { create } from "zustand";
import type { BusinessInfoBlock, ProductDraft, ProductImageDraft, Tenant, WhatsAppConnection } from "@/lib/types";

const LEGACY_STORAGE_KEY = "whatsbase.onboarding";

interface OnboardingState {
  sessionUserId: string | null;
  tenant?: Tenant;
  businessInfo: BusinessInfoBlock[];
  products: ProductDraft[];
  catalogPhotos: ProductImageDraft[];
  whatsapp?: WhatsAppConnection;
  setTenant: (tenant: Tenant) => void;
  setBusinessInfo: (businessInfo: BusinessInfoBlock[]) => void;
  setProducts: (products: ProductDraft[]) => void;
  setCatalogPhotos: (catalogPhotos: ProductImageDraft[]) => void;
  setWhatsApp: (whatsapp: WhatsAppConnection) => void;
  ensureUserSession: (userId: string) => void;
  reset: () => void;
}

const initialState = {
  sessionUserId: null as string | null,
  businessInfo: [] as BusinessInfoBlock[],
  products: [] as ProductDraft[],
  catalogPhotos: [] as ProductImageDraft[],
};

export function clearOnboardingCache() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  }
}

export const useOnboardingStore = create<OnboardingState>()((set) => ({
  ...initialState,
  setTenant: (tenant) => set({ tenant }),
  setBusinessInfo: (businessInfo) => set({ businessInfo }),
  setProducts: (products) => set({ products }),
  setCatalogPhotos: (catalogPhotos) => set({ catalogPhotos }),
  setWhatsApp: (whatsapp) => set({ whatsapp }),
  ensureUserSession: (userId) =>
    set((state) => {
      if (state.sessionUserId === userId) return state;
      clearOnboardingCache();
      return { ...initialState, sessionUserId: userId };
    }),
  reset: () => {
    clearOnboardingCache();
    set(initialState);
  },
}));

// Drop stale cross-account data left by the old persisted store.
clearOnboardingCache();
