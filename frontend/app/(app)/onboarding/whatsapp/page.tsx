"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import { useOnboardingStore } from "@/lib/store";

export default function WhatsAppOnboardingPage() {
  const router = useRouter();
  const { t } = useLocale();
  const { whatsapp, setWhatsApp } = useOnboardingStore();
  const [instanceId, setInstanceId] = useState("");
  const [token, setToken] = useState("");
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (whatsapp?.connected) return;
    void api.getWhatsAppStatus().then((status) => {
      if (status.connected) setWhatsApp(status);
    });
  }, [setWhatsApp, whatsapp?.connected]);

  const testConnection = async () => {
    setChecking(true);
    const result = await api.connectWhatsApp({ instanceId, token });
    setWhatsApp(result);
    setChecking(false);
  };

  return (
    <div>
      <WizardStepper />
      <Card>
        <CardHeader>
          <CardTitle>{t("Connect WhatsApp", "חיבור וואטסאפ")}</CardTitle>
          <CardDescription>
            {t(
              "Provide Green API credentials and verify the connection.",
              "הזינו פרטי Green API ובדקו שהחיבור תקין.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="instance">{t("Instance ID", "מזהה Instance")}</Label>
            <Input
              id="instance"
              value={instanceId}
              onChange={(event) => setInstanceId(event.target.value)}
              placeholder="7107649122"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="token">{t("API token", "טוקן API")}</Label>
            <Input
              id="token"
              value={token}
              type="password"
              onChange={(event) => setToken(event.target.value)}
              placeholder="••••••••••"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={testConnection}
            disabled={checking || !instanceId || !token}
          >
            {checking ? (
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                {t("Testing...", "בודק...")}
              </span>
            ) : (
              t("Test connection", "בדיקת חיבור")
            )}
          </Button>

          {whatsapp?.connected ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              {t("Connected phone", "מספר מחובר")}: {whatsapp.phone} · {whatsapp.intakeMode}
            </div>
          ) : null}

          <Button
            type="button"
            className="bg-emerald-600 hover:bg-emerald-700"
            disabled={!whatsapp?.connected}
            onClick={() => router.push("/onboarding/build")}
          >
            {t("Rebuild to go live", "בנייה מחדש לפרסום")}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
