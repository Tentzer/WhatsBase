"use client";

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@/components/navigation-progress";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { WizardStepper } from "@/components/wizard-stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/locale";
import type { AgentStatus, BuildRun } from "@/lib/types";

const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 4 * 60 * 60 * 1000;

async function pollBuildRun(
  buildRunId: string,
  onUpdate: (run: BuildRun) => void,
): Promise<BuildRun> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let consecutiveErrors = 0;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    try {
      const updated = await api.getBuildRun(buildRunId);
      consecutiveErrors = 0;
      if (!updated) continue;
      onUpdate(updated);
      if (updated.status === "passed" || updated.status === "failed") {
        return updated;
      }
    } catch (err) {
      consecutiveErrors += 1;
      if (consecutiveErrors >= 8) {
        throw err instanceof Error
          ? err
          : new Error("Build status polling failed — refresh the page to see the latest run");
      }
    }
  }
  throw new Error("Build timed out — check Railway worker logs and retry");
}

export default function BuildPage() {
  const navigate = useNavigate();
  const { t } = useLocale();
  const [run, setRun] = useState<BuildRun | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [status, latestRun] = await Promise.all([
          api.getAgentStatus(),
          api.getLatestBuildRun(),
        ]);
        setAgentStatus(status);
        if (latestRun) {
          setRun(latestRun);
        }
      } catch (err) {
        console.error("Failed to load build page state:", err);
      } finally {
        setHydrating(false);
      }
    })();
  }, []);

  const isLive = agentStatus === "live" || run?.status === "passed";
  const buildInProgress = running || run?.status === "running" || run?.status === "queued";

  const runBuild = async (mode: "full" | "incremental") => {
    setRunning(true);
    setError(null);
    setRun(null);
    try {
      const started =
        mode === "full" ? await api.startBuild() : await api.startIncrementalBuild();
      setRun(started);
      const finalRun = await pollBuildRun(started.id, setRun);
      setRun(finalRun);
      if (finalRun.status === "passed") {
        setAgentStatus("live");
      } else if (finalRun.status === "failed" && mode === "full") {
        setAgentStatus("failed");
      }
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

  const startBuild = () => runBuild("full");
  const startIncrementalBuild = () => runBuild("incremental");

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

  const pageTitle = isLive
    ? t("Rebuild agent", "בנייה מחדש")
    : t("Build my agent", "בניית הסוכן");

  const pageDescription = isLive
    ? t(
        "Your agent is live. Rebuild after updating products or business info.",
        "הסוכן כבר בלייב. בנו מחדש אחרי עדכון מוצרים או פרטי עסק.",
      )
    : t(
        "Run the builder flow and validate the tenant before go-live.",
        "הרצת תהליך הבנייה ואימות לפני מעבר ללייב.",
      );

  const buildButtonLabel = running
    ? t("Starting...", "מתחיל...")
    : run?.status === "failed"
      ? t("Retry build", "נסו שוב")
      : isLive
        ? t("Rebuild agent", "בנייה מחדש")
        : t("Build my agent", "בנו את הסוכן");

  if (hydrating) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div>
      <WizardStepper />
      <Card>
        <CardHeader>
          <CardTitle>{pageTitle}</CardTitle>
          <CardDescription>{pageDescription}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {isLive && !buildInProgress ? (
            <div className="flex items-center gap-2 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">
              <CheckCircle2 className="size-4" />
              {t("Your agent is live.", "הסוכן שלכם בלייב.")}
            </div>
          ) : null}

          {!buildInProgress ? (
            <div className="flex flex-wrap gap-3">
              <Button className="bg-emerald-600 hover:bg-emerald-700" onClick={startBuild} disabled={running}>
                {buildButtonLabel}
              </Button>
              {isLive ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={startIncrementalBuild}
                  disabled={running}
                >
                  {running
                    ? t("Starting...", "מתחיל...")
                    : t("Rebuild with new data", "בנייה מחדש עם מוצרים חדשים")}
                </Button>
              ) : null}
            </div>
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
