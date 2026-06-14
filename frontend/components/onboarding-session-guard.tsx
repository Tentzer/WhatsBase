"use client";

import { useEffect } from "react";
import { clearOnboardingCache, useOnboardingStore } from "@/lib/store";
import { createClient } from "@/lib/supabase/client";

/** Clears onboarding state when the signed-in Supabase user changes. */
export function OnboardingSessionGuard() {
  const ensureUserSession = useOnboardingStore((state) => state.ensureUserSession);

  useEffect(() => {
    const supabase = createClient();
    clearOnboardingCache();

    const syncUser = (userId: string | undefined) => {
      if (userId) {
        ensureUserSession(userId);
      }
    };

    void supabase.auth.getUser().then(({ data }) => {
      syncUser(data.user?.id);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      syncUser(session?.user?.id);
    });

    return () => subscription.unsubscribe();
  }, [ensureUserSession]);

  return null;
}
