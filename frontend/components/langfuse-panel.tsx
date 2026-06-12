"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type ModelCostRow = {
  modelName: string;
  calls: number;
  totalCost: number;
};

type DailyUsageRow = {
  date: string;
  calls: number;
};

type PanelState = {
  totalCostThisMonth: number;
  costByModel: ModelCostRow[];
  dailyUsage: DailyUsageRow[];
};

const EMPTY_STATE: PanelState = {
  totalCostThisMonth: 0,
  costByModel: [],
  dailyUsage: [],
};

const CURRENCY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

function toIsoDate(d: Date): string {
  return d.toISOString();
}

function asFiniteNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function asString(value: unknown, fallback = "Unknown"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  return fallback;
}

function parseModelRows(raw: unknown): ModelCostRow[] {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { data?: unknown }).data)) {
    return [];
  }

  const rows = (raw as { data: unknown[] }).data;
  return rows
    .map((row) => {
      if (!row || typeof row !== "object") return null;
      const record = row as Record<string, unknown>;
      return {
        modelName: asString(record.providedModelName),
        calls: Math.round(asFiniteNumber(record.count_countObservations ?? record.count_count)),
        totalCost: asFiniteNumber(record.sum_totalCost),
      };
    })
    .filter((row): row is ModelCostRow => Boolean(row))
    .sort((a, b) => b.totalCost - a.totalCost);
}

function parseTotalCost(raw: unknown): number {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { data?: unknown }).data)) {
    return 0;
  }
  const first = (raw as { data: unknown[] }).data[0];
  if (!first || typeof first !== "object") return 0;
  return asFiniteNumber((first as Record<string, unknown>).sum_totalCost);
}

function parseDailyRows(raw: unknown): DailyUsageRow[] {
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { data?: unknown }).data)) {
    return [];
  }

  const rows = (raw as { data: unknown[] }).data;
  return rows
    .map((row) => {
      if (!row || typeof row !== "object") return null;
      const record = row as Record<string, unknown>;
      const dateRaw = asString(record.time_dimension ?? record.timeDimension, "");
      if (!dateRaw) return null;

      return {
        date: dateRaw,
        calls: Math.round(asFiniteNumber(record.count_countObservations ?? record.count_count)),
      };
    })
    .filter((row): row is DailyUsageRow => Boolean(row))
    .sort((a, b) => a.date.localeCompare(b.date));
}

function buildSevenDaySeries(dailyUsage: DailyUsageRow[], now: Date): DailyUsageRow[] {
  const byDay = new Map<string, number>();
  for (const row of dailyUsage) {
    const dayKey = row.date.slice(0, 10);
    byDay.set(dayKey, row.calls);
  }

  const series: DailyUsageRow[] = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const day = new Date(now);
    day.setUTCDate(now.getUTCDate() - offset);
    const dayKey = day.toISOString().slice(0, 10);
    series.push({
      date: `${dayKey}T00:00:00.000Z`,
      calls: byDay.get(dayKey) ?? 0,
    });
  }
  return series;
}

async function postMetricsQuery(query: Record<string, unknown>) {
  const response = await fetch("/api/langfuse?endpoint=metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
    cache: "no-store",
  });

  const payload = await response.json();
  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && typeof payload.error === "string"
        ? payload.error
        : "Failed to fetch Langfuse metrics";
    throw new Error(message);
  }
  return payload;
}

export function LangfusePanel({ isOpen }: { isOpen: boolean }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<PanelState>(EMPTY_STATE);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);

    const now = new Date();
    const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
    const thirtyDaysAgo = new Date(now);
    thirtyDaysAgo.setUTCDate(now.getUTCDate() - 30);
    const sixDaysAgo = new Date(now);
    sixDaysAgo.setUTCDate(now.getUTCDate() - 6);

    try {
      const [monthlyTotalRaw, costByModelRaw, dailyUsageRaw] = await Promise.all([
        postMetricsQuery({
          view: "observations",
          metrics: [{ measure: "totalCost", aggregation: "sum" }],
          dimensions: [],
          fromTimestamp: toIsoDate(monthStart),
          toTimestamp: toIsoDate(now),
          config: { row_limit: 1 },
        }),
        postMetricsQuery({
          view: "observations",
          metrics: [
            { measure: "totalCost", aggregation: "sum" },
            { measure: "countObservations", aggregation: "count" },
          ],
          dimensions: [{ field: "providedModelName" }],
          fromTimestamp: toIsoDate(thirtyDaysAgo),
          toTimestamp: toIsoDate(now),
          orderBy: [{ field: "sum_totalCost", direction: "desc" }],
          config: { row_limit: 20 },
        }),
        postMetricsQuery({
          view: "observations",
          metrics: [{ measure: "countObservations", aggregation: "count" }],
          dimensions: [],
          timeDimension: { granularity: "day" },
          fromTimestamp: toIsoDate(sixDaysAgo),
          toTimestamp: toIsoDate(now),
          orderBy: [{ field: "time_dimension", direction: "asc" }],
          config: { row_limit: 7 },
        }),
      ]);

      const totalCostThisMonth = parseTotalCost(monthlyTotalRaw);
      const costByModel = parseModelRows(costByModelRaw);
      const dailyUsage = parseDailyRows(dailyUsageRaw);
      const normalizedDailyUsage = buildSevenDaySeries(dailyUsage, now);

      setState({
        totalCostThisMonth,
        costByModel,
        dailyUsage: normalizedDailyUsage,
      });
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "Failed to fetch analytics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      const refreshTimer = window.setTimeout(() => {
        void fetchMetrics();
      }, 0);
      return () => window.clearTimeout(refreshTimer);
    }
  }, [isOpen, fetchMetrics]);

  const maxDailyCalls = useMemo(() => {
    const max = state.dailyUsage.reduce((acc, row) => Math.max(acc, row.calls), 0);
    return max || 1;
  }, [state.dailyUsage]);

  return (
    <div className="absolute top-full right-0 z-50 mt-2 w-[26rem] origin-top-right rounded-2xl border bg-card p-3 shadow-2xl shadow-black/20 dark:shadow-black/50">
      {loading ? (
        <div className="space-y-3">
          <div className="h-28 animate-pulse rounded-xl bg-muted/70" />
          <div className="h-40 animate-pulse rounded-xl bg-muted/70" />
          <div className="h-32 animate-pulse rounded-xl bg-muted/70" />
        </div>
      ) : error ? (
        <Card className="border-destructive/30">
          <CardHeader>
            <CardTitle>Analytics unavailable</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardDescription>Total cost this month</CardDescription>
              <CardTitle className="text-3xl text-emerald-700 dark:text-emerald-400">
                {CURRENCY.format(state.totalCostThisMonth)}
              </CardTitle>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Cost by model</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Calls</TableHead>
                    <TableHead className="text-right">Total Cost (USD)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {state.costByModel.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-muted-foreground">
                        No model usage data in selected range.
                      </TableCell>
                    </TableRow>
                  ) : (
                    state.costByModel.map((row) => (
                      <TableRow key={row.modelName}>
                        <TableCell className="max-w-48 truncate">{row.modelName}</TableCell>
                        <TableCell className="text-right">{row.calls.toLocaleString()}</TableCell>
                        <TableCell className="text-right">{CURRENCY.format(row.totalCost)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Daily usage (last 7 days)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {state.dailyUsage.map((row) => {
                const widthPct = Math.max(8, Math.round((row.calls / maxDailyCalls) * 100));
                const label = new Date(row.date).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                });
                return (
                  <div key={`${row.date}-${row.calls}`} className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{label}</span>
                      <span>{row.calls.toLocaleString()} calls</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      <div
                        className="h-2 rounded-full bg-emerald-500 transition-all"
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
