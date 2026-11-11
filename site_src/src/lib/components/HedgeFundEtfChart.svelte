<script lang="ts">
    import { onMount } from "svelte";
    import * as Chart from "$lib/components/ui/chart/index.js";
    import { LineChart } from "layerchart";
    import { scaleUtc } from "d3-scale";
    import { curveNatural } from "d3-shape";

    let { etfMeta = null }: { etfMeta?: any } = $props();

    let chartData = $state<any[] | null>(null);
    let isLoading = $state(false);
    let error = $state<string | null>(null);
    let context = $state<any>(undefined);
    let activeDate = $state<Date | null>(null);
    let hasSpx = $state(false);

    // Rebalance windows from pit_etf_meta.json, with parsed Date bounds.
    const windows = $derived(
        (etfMeta?.windows ?? []).map((w: any) => ({
            ...w,
            start: new Date(w.date),
            end: new Date(w.end_date),
        }))
    );

    // Track the hovered date from the chart tooltip context.
    $effect(() => {
        const d = context?.tooltip?.data;
        activeDate = d?.date ?? null;
    });

    function windowForDate(date: Date | null) {
        if (!windows.length || !date) return null;
        for (let i = windows.length - 1; i >= 0; i--) {
            if (date >= windows[i].start) return windows[i];
        }
        return windows[0];
    }

    // Interval currently under the cursor (drives the shaded band).
    const activeWindow = $derived(windowForDate(activeDate));
    // What to show in the holdings strip: hovered interval, else the latest one.
    const displayWindow = $derived(
        activeWindow ?? (windows.length ? windows[windows.length - 1] : null)
    );

    const chartConfig = {
        PortfolioValue_etf: {
            label: "Hedge Fund Investment ETF",
            color: "#2563eb",
        },
        PortfolioValue_spx: {
            label: "S&P 500 (same investment)",
            color: "#dc2626",
        },
    };

    // Only overlay the SPX comparison line once its data has been merged in.
    const chartSeries = $derived([
        {
            key: "PortfolioValue_etf",
            label: chartConfig.PortfolioValue_etf.label,
            color: chartConfig.PortfolioValue_etf.color,
        },
        ...(hasSpx
            ? [
                  {
                      key: "PortfolioValue_spx",
                      label: chartConfig.PortfolioValue_spx.label,
                      color: chartConfig.PortfolioValue_spx.color,
                  },
              ]
            : []),
    ]);

    async function loadChartData() {
        isLoading = true;
        error = null;
        try {
            const url =
                "https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/pit_etf_backtest_values.csv";
            const response = await fetch(url);
            if (!response.ok) throw new Error("ETF chart data not available yet.");
            const text = await response.text();
            const rows = text.split("\n").slice(1);
            const parseValue = (val: string) =>
                val == null || val.trim() === "" ? null : +val;
            const parsed = rows
                .map((row) => {
                    const [date, value] = row.split(",");
                    if (!date) return null;
                    return {
                        date: new Date(date),
                        PortfolioValue_etf: parseValue(value),
                    };
                })
                .filter(
                    (d): d is { date: Date; PortfolioValue_etf: number } =>
                        !!d &&
                        !!d.date &&
                        !isNaN(d.date.valueOf()) &&
                        d.PortfolioValue_etf != null
                );
            // Overlay an S&P 500 comparison: the same initial investment grown
            // by SPX over the ETF's exact timerange. Gracefully skip if the SPX
            // returns file is missing.
            try {
                const spxUrl =
                    "https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/spx_returns.csv";
                const spxResp = await fetch(spxUrl);
                if (spxResp.ok && parsed.length) {
                    const spxText = await spxResp.text();
                    const spxRows = spxText.split("\n").slice(1);
                    const spx = spxRows
                        .map((row) => {
                            const [d, close] = row.split(",");
                            if (!d) return null;
                            const c = parseValue(close);
                            return c == null ? null : { date: new Date(d), close: c };
                        })
                        .filter(
                            (d): d is { date: Date; close: number } =>
                                !!d && !!d.date && !isNaN(d.date.valueOf())
                        )
                        .sort((a, b) => a.date.valueOf() - b.date.valueOf());

                    if (spx.length) {
                        const initial = parsed[0].PortfolioValue_etf;
                        const startMs = parsed[0].date.valueOf();
                        // SPX close on or before the ETF start (the buy price).
                        let baseClose = null;
                        for (let i = spx.length - 1; i >= 0; i--) {
                            if (spx[i].date.valueOf() <= startMs) {
                                baseClose = spx[i].close;
                                break;
                            }
                        }
                        if (baseClose == null) baseClose = spx[0].close;
                        // For each ETF date, use the most recent SPX close <= date.
                        let si = 0;
                        for (const row of parsed) {
                            const ms = row.date.valueOf();
                            while (si + 1 < spx.length && spx[si + 1].date.valueOf() <= ms) {
                                si++;
                            }
                            const cl = spx[si] ? spx[si].close : null;
                            (row as any).PortfolioValue_spx =
                                cl != null && baseClose ? (initial * cl) / baseClose : null;
                        }
                        hasSpx = true;
                    }
                }
            } catch (spxErr) {
                // SPX comparison is optional; render the ETF line only.
                hasSpx = false;
            }

            chartData = parsed as any[];
        } catch (e: any) {
            error = e.message;
        } finally {
            isLoading = false;
        }
    }

    onMount(loadChartData);

    const fmtMoney = (v: number | null | undefined) =>
        v == null ? "N/A" : `$${(v / 1_000_000).toFixed(2)}M`;
    const fmtDate = (d: Date | string | null | undefined) => {
        if (!d) return "";
        const date = d instanceof Date ? d : new Date(d);
        return date.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
        });
    };
    const fmtPct = (v: number | null | undefined) =>
        v == null ? "N/A" : `${(v * 100).toFixed(1)}%`;
</script>

<div class="flex h-full w-full flex-col gap-3">
    <div class="relative min-h-[260px] flex-1">
        {#if isLoading}
            <div class="flex h-full items-center justify-center text-sm text-muted-foreground">
                Loading ETF backtest...
            </div>
        {:else if error}
            <div class="flex h-full items-center justify-center text-sm text-destructive">
                {error}
            </div>
        {:else if chartData && chartData.length}
            <Chart.Container config={chartConfig} class="h-full w-full">
                <LineChart
                    bind:context
                    data={chartData}
                    x="date"
                    xScale={scaleUtc()}
                    series={chartSeries}
                    props={{
                        spline: {
                            curve: curveNatural,
                            motion: "tween",
                            strokeWidth: 2,
                        },
                        yAxis: {
                            ticks: 5,
                            format: (v) => `$${(v / 1000000).toFixed(1)}M`,
                        },
                        xAxis: {
                            ticks: 5,
                            format: (v) =>
                                v.toLocaleDateString("en-US", {
                                    month: "short",
                                    year: "numeric",
                                }),
                        },
                        highlight: { points: { r: 4 } },
                    }}
                >
                    {#snippet belowMarks({ context })}
                        {#if activeWindow}
                            {@const x0 = context.xScale(activeWindow.start)}
                            {@const x1 = context.xScale(activeWindow.end)}
                            <rect
                                x={Math.min(x0, x1)}
                                y={0}
                                width={Math.max(2, Math.abs(x1 - x0))}
                                height={context.height}
                                fill={chartConfig.PortfolioValue_etf.color}
                                opacity={0.1}
                            />
                        {/if}
                    {/snippet}
                </LineChart>
            </Chart.Container>
        {:else}
            <div class="flex h-full items-center justify-center text-sm text-muted-foreground">
                No ETF data available
            </div>
        {/if}
    </div>

    {#if displayWindow}
        <div class="rounded-lg border bg-card p-3">
            <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div class="text-sm font-medium">
                    {#if activeWindow}
                        Holdings {fmtDate(displayWindow.start)} → {fmtDate(displayWindow.end)}
                    {:else}
                        Latest holdings · {fmtDate(displayWindow.start)} → {fmtDate(displayWindow.end)}
                    {/if}
                </div>
                <span class="text-xs text-muted-foreground">
                    {displayWindow.num_funds} fund{displayWindow.num_funds === 1 ? "" : "s"} ·
                    {fmtMoney(displayWindow.value_start)} → {fmtMoney(displayWindow.value_end)}
                </span>
            </div>
            {#if displayWindow.selected && displayWindow.selected.length}
                <div class="flex flex-col divide-y">
                    {#each displayWindow.selected as f}
                        {@const ret = f.fund_return}
                        <div class="flex items-center justify-between gap-2 py-1.5 text-xs">
                            <div class="flex min-w-0 flex-1 items-center gap-2">
                                <span class="truncate font-medium" title={`Sharpe ${f.sharpe}`}>{@html f.name}</span>
                                <span class="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{fmtPct(f.weight)}</span>
                            </div>
                            <div class="flex shrink-0 items-center gap-3">
                                {#if f.value_start != null && f.value_end != null}
                                    <span class="tabular-nums text-muted-foreground">
                                        {fmtMoney(f.value_start)} → {fmtMoney(f.value_end)}
                                    </span>
                                {/if}
                                {#if ret != null}
                                    <span class={`tabular-nums font-medium ${ret >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                                        {ret >= 0 ? "+" : ""}{fmtPct(ret)}
                                    </span>
                                {/if}
                            </div>
                        </div>
                    {/each}
                </div>
            {:else}
                <div class="text-xs text-muted-foreground">
                    No funds passed the filter in this period (held as cash).
                </div>
            {/if}
        </div>
    {/if}
</div>
