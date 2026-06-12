"use client";

import { useMemo, useState } from "react";
import { useNavigate } from "@/components/navigation-progress";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import type { BuildRun } from "@/lib/types";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

async function pollBuildRun(
  buildRunId: string,
  onUpdate: (run: BuildRun) => void,
): Promise<BuildRun> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    const updated = await api.getBuildRun(buildRunId);
    if (!updated) continue;
    onUpdate(updated);
    if (updated.status === "passed" || updated.status === "failed") {
      return updated;
    }
  }
  throw new Error("Build timed out — check Railway worker logs and retry");
}

export default function BuildPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const [run, setRun] = useState<BuildRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startBuild = async () => {
    setRunning(true);
    setError(null);
    setRun(null);
    try {
      const started = await api.startBuild();
      setRun(started);
      const finalRun = await pollBuildRun(started.id, setRun);
      setRun(finalRun);
      if (finalRun.status === "failed") {
        setError(
          t(
            "Build failed. Check that the Railway worker is running with LLM API keys configured.",
            "הבנייה נכשלה. ודאו ש-worker ב-Railway רץ עם מפתחות LLM מוגדרים.",
          ),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const stepLabel = useMemo(() => {
    if (!run?.currentStep) return t("Waiting to start", "ממתין להתחלה");
    const map: Record<string, string> = {
      collect_assets: t("Collecting assets", "איסוף נכסים"),
      caption_images: t("Captioning images", "תיאור תמונות"),
      index_embeddings: t("Indexing knowledge", "אינדוקס ידע"),
      run_self_test: t("Running self-test", "בדיקה עצמית"),
      finalize: t("Finalizing", "סיום"),
    };
    return map[run.currentStep];
  }, [run?.currentStep, t]);

  return (
    <div>
      <WizardStepper />
      <Card>
        <CardHeader>
          <CardTitle>{t("Build my agent", "בניית הסוכן")}</CardTitle>
          <CardDescription>
            {t(
              "Run the builder flow and validate the tenant before go-live.",
              "הרצת תהליך הבנייה ואימות לפני מעבר ללייב.",
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {!run || run.status === "failed" ? (
            <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={startBuild} disabled={running}>
              {running
                ? t("Starting...", "מתחיל...")
                : run?.status === "failed"
                  ? t("Retry build", "נסו שוב")
                  : t("Build my agent", "בנו את הסוכן")}
            </Button>
          ) : null}

          {error ? (
            <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {run ? (
            <div className="space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{stepLabel}</span>
                <span className="font-medium">{run.progressPct}%</span>
              </div>
              <Progress value={run.progressPct} />
              {run.status === "running" || run.status === "queued" || running ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" />
                  {t("Builder is running...", "הבילדר רץ...")}
                </div>
              ) : null}
              {run.status === "passed" ? (
                <div className="flex items-center gap-2 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
                  <CheckCircle2 className="size-4" />
                  {t("Build passed and agent is live.", "הבנייה עברה והסוכן בלייב.")}
                </div>
              ) : null}
              {run.status === "failed" ? (
                <div className="flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800">
                  <AlertTriangle className="size-4" />
                  {t("Build failed. Review the report or retry.", "הבנייה נכשלה. בדקו את הדוח או נסו שוב.")}
                </div>
              ) : null}
            </div>
          ) : null}

          {run?.report ? (
            <Card>
              <CardHeader>
                <CardTitle>{t("Build report", "דוח בנייה")}</CardTitle>
                <CardDescription>
                  {t("Self-test results and assumptions", "תוצאות בדיקה עצמית והנחות")}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-2 text-sm sm:grid-cols-2">
                  <p>
                    {t("Products detected", "מוצרים שאותרו")}:{" "}
                    <span className="font-medium">{run.report.productsDetected}</span>
                  </p>
                  <p>
                    {t("Products created", "מוצרים שנוצרו")}:{" "}
                    <span className="font-medium">{run.report.productsCreated}</span>
                  </p>
                </div>

                {run.report.assumptions.length > 0 ? (
                  <div>
                    <p className="mb-2 text-sm font-medium">{t("Assumptions", "הנחות")}</p>
                    <ul className="list-disc space-y-1 ps-6 text-sm text-muted-foreground">
                      {run.report.assumptions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {run.report.selfTest.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("Question", "שאלה")}</TableHead>
                        <TableHead>{t("Result", "תוצאה")}</TableHead>
                        <TableHead>{t("Status", "סטטוס")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {run.report.selfTest.map((result) => (
                        <TableRow key={result.question}>
                          <TableCell>{result.question}</TableCell>
                          <TableCell>{result.answerSummary}</TableCell>
                          <TableCell>{result.passed ? "PASS" : "FAIL"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={run?.status !== "passed"}
              onClick={() => navigate("/test-chat")}
            >
              {t("Open test chat", "פתיחת צ׳אט בדיקה")}
            </Button>
            <Button
              type="button"
              className="bg-emerald-600 hover:bg-emerald-700"
              disabled={run?.status !== "passed"}
              onClick={() => navigate("/onboarding/whatsapp")}
            >
              {t("Continue → Connect WhatsApp", "המשך → חיבור וואטסאפ")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
