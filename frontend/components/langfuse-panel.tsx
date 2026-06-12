"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import type { LangfuseAnalytics } from "@/lib/types";

const EMPTY_STATE: LangfuseAnalytics = {
  totalCostThisMonthUsd: 0,
  costByModel: [],
  dailyUsageLast7Days: [],
  latencyByName: [],
};

const CURRENCY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

function formatMs(ms: number): string {
  if (ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function LangfusePanel({ isOpen }: { isOpen: boolean }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<LangfuseAnalytics>(EMPTY_STATE);

  useEffect(() => {
    if (isOpen) {
      const refreshTimer = window.setTimeout(async () => {
        setLoading(true);
        setError(null);
        try {
          const analytics = await api.getLangfuseAnalytics();
          setState(analytics);
        } catch (fetchError) {
          setError(fetchError instanceof Error ? fetchError.message : "Failed to fetch analytics");
        } finally {
          setLoading(false);
        }
      }, 0);
      return () => window.clearTimeout(refreshTimer);
    }
  }, [isOpen]);

  const maxDailyCalls = useMemo(() => {
    const max = state.dailyUsageLast7Days.reduce((acc, row) => Math.max(acc, row.calls), 0);
    return max || 1;
  }, [state.dailyUsageLast7Days]);

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
                {CURRENCY.format(state.totalCostThisMonthUsd)}
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
                        <TableCell className="text-right">{CURRENCY.format(row.totalCostUsd)}</TableCell>
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
              {state.dailyUsageLast7Days.map((row) => {
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

          {state.latencyByName.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Latency by trace (last 30 days)</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Trace name</TableHead>
                      <TableHead className="text-right">p50</TableHead>
                      <TableHead className="text-right">p95</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {state.latencyByName.map((row) => (
                      <TableRow key={row.name}>
                        <TableCell className="max-w-40 truncate font-mono text-xs">{row.name}</TableCell>
                        <TableCell className="text-right text-xs">{formatMs(row.p50Ms)}</TableCell>
                        <TableCell className="text-right text-xs">{formatMs(row.p95Ms)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
