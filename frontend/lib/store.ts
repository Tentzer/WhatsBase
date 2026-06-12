"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { BusinessInfoBlock, ProductDraft, ProductImageDraft, Tenant, WhatsAppConnection } from "@/lib/types";

interface OnboardingState {
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
  reset: () => void;
}

const initialState = {
  businessInfo: [],
  products: [],
  catalogPhotos: [],
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initialState,
      setTenant: (tenant) => set({ tenant }),
      setBusinessInfo: (businessInfo) => set({ businessInfo }),
      setProducts: (products) => set({ products }),
      setCatalogPhotos: (catalogPhotos) => set({ catalogPhotos }),
      setWhatsApp: (whatsapp) => set({ whatsapp }),
      reset: () => set(initialState),
    }),
    { name: "whatsbase.onboarding" },
  ),
);
