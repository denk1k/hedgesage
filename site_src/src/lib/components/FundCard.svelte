<script lang="ts">
    import * as Card from "$lib/components/ui/card/index.js";
    import * as Select from "$lib/components/ui/select/index.js";
    import * as Alert from "$lib/components/ui/alert/index.js";
    import * as Drawer from "$lib/components/ui/drawer/index.js";
    import * as Chart from "$lib/components/ui/chart/index.js";
    import * as Tooltip from "$lib/components/ui/tooltip/index";
    import { Button, buttonVariants } from "$lib/components/ui/button";
    import { AreaChart, LineChart } from "layerchart";
    import { scaleUtc } from "d3-scale";
    import { format } from 'd3-format';
    import { base } from '$app/paths';
    import { curveNatural } from "d3-shape";
    import Expand from "@lucide/svelte/icons/expand";
    import AllocationsDataTable from "$lib/components/AllocationsDataTable.svelte";
    import { Skeleton } from "$lib/components/ui/skeleton/index.js";
    import { onMount, onDestroy } from "svelte";
    import { cn } from "$lib/utils";

    export let cik: string;
    export let fundData: any;
    export let meta: any = null;
    let chartVisible = false;
    let cardRef: HTMLElement;

    export let metricType: string = "copy";
    let activeMetric: string = metricType; // Local state for interaction

    // Sync local state when prop changes (from global filter)
    $: if (metricType) {
        activeMetric = metricType;
    }

    let chartData: any[] | null = null;
    let isLoading = false;
    let error: string | null = null;
    let drawerOpen = false;
    let allocationsDrawerOpen = false;
    let allocationsData: AllocationData[] | null = null;
    let isAllocationsLoading = false;
    let allocationsError: string | null = null;

    interface AllocationData {
        ticker: string;
        allocation_percent: string;
        [key: string]: string;
    }

    const metricSuffixes: Record<string, string> = {
        fund: "_fund",
        copy: "_copy",
        copy_scaled: "_copy_scaled",
    };

     const metrics = {
        copy: {
            label: 'Copied',
            tooltip: 'Performance based on copying the fund\'s holdings, rebalanced on filing dates (Available 45 days after quarter end).',
            suffix: '_copy'
        },
        copy_scaled: {
            label: 'Copied (Scaled)',
            tooltip: 'Performance based on copying the fund\'s holdings, scaled to 100% exposure, rebalanced on filing dates.',
            suffix: '_copy_scaled'
        },
        fund: {
            label: 'Original',
            tooltip: 'The actual reported performance of the fund.',
            suffix: '_fund'
        }
    };

    $: selectedMetrics = fundData.backtest_results
        ? {
              earliest_filing_date: fundData.earliest_filing_date || null,
              total_return:
                  fundData.backtest_results[
                      `total_return${metricSuffixes[activeMetric]}`
                  ] ?? null,
              annualized_return:
                  fundData.backtest_results[
                      `annualized_return${metricSuffixes[activeMetric]}`
                  ] ?? null,
              sharpe_ratio:
                  fundData.backtest_results[
                      `sharpe_ratio${metricSuffixes[activeMetric]}`
                  ] ?? null,
              max_drawdown:
                  fundData.backtest_results[
                      `max_drawdown${metricSuffixes[activeMetric]}`
                  ] ?? null,
              calmar_ratio:
                  fundData.backtest_results[
                      `calmar_ratio${metricSuffixes[activeMetric]}`
                  ] ?? null,
          }
        : null;

    let observer: IntersectionObserver;

    onMount(() => {
        observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    chartVisible = entry.isIntersecting;
                });
            },
            {
                rootMargin: "0px",
                threshold: 0.1, // when 10% of the card is visible
            },
        );

        if (cardRef) {
            observer.observe(cardRef);
        }
    });
    onDestroy(() => {
        if (observer && cardRef) {
            observer.unobserve(cardRef);
        }
    });

    let debounceTimer: ReturnType<typeof setTimeout>;

    $: if (chartVisible && !chartData && !isLoading && !error) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            if (chartVisible) loadChartData();
        }, 300);
    } else if (!chartVisible) {
        clearTimeout(debounceTimer);
        if (chartData) {
            chartData = null;
        }
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }

    let abortController: AbortController | null = null;

    async function loadChartData() {
        if (abortController) {
            abortController.abort();
        }
        abortController = new AbortController();
        const signal = abortController.signal;

        isLoading = true;
        error = null;
        try {
            const response = await fetch(
                `https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/backtests/${cik}_backtest_values.csv`,
                { signal }
            );
            if (!response.ok) {
                throw new Error(`Chart data not available for this fund.`);
            }
            const csvText = await response.text();
            const rows = csvText.split("\n").slice(1); // skip header
            const parseValue = (val: string) =>
                val.trim() === "" ? null : +val;
            const parsedData = rows
                .map((row) => {
                    const [date, copy, copy_scaled, fund] = row.split(",");
                    if (!date) return null;
                    return {
                        date: new Date(date),
                        PortfolioValue_copy: parseValue(copy),
                        PortfolioValue_copy_scaled: parseValue(copy_scaled),
                        PortfolioValue_fund: parseValue(fund),
                    };
                })
                .filter(
                    (d): d is Exclude<typeof d, null> =>
                        d !== null &&
                        d.date instanceof Date &&
                        !isNaN(d.date.valueOf()),
                );

            if (parsedData.length === 0) {
                throw new Error("CSV invalid");
            }
            
            if (chartVisible) {
                chartData = parsedData;
            }
        } catch (e: any) {
            if (e.name !== 'AbortError') {
                error = e.message;
            }
        } finally {
            isLoading = false;
            abortController = null;
        }
    }

    async function loadAllocationsData() {
        isAllocationsLoading = true;
        allocationsError = null;
        try {
            const response = await fetch(
                `https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations/${cik}.csv`,
            );
            if (!response.ok) {
                throw new Error(
                    `Allocations data not available for this fund.`,
                );
            }
            console.log("Alloc response OK");
            const csvText = await response.text();
            const rows = csvText.split("\n");
            const header = rows.shift()?.split(",");
            if (!header) {
                throw new Error("Invalid CSV header");
            }

            const parsedData = rows
                .map((row) => {
                    const values = row.split(",");
                    const rowData: AllocationData = header.reduce(
                        (obj: Record<string, string>, key, index) => {
                            obj[key.trim()] = values[index];
                            return obj;
                        },
                        {} as AllocationData,
                    );
                    return rowData;
                })
                .filter((d) => d.ticker); // no empty rows

            allocationsData = parsedData;
        } catch (e: any) {
            allocationsError = e.message;
        } finally {
            isAllocationsLoading = false;
        }
    }

    const chartConfig = {
        PortfolioValue_copy: { label: "Copied", color: "blue" },
        PortfolioValue_copy_scaled: { label: "Copied (Scaled)", color: "yellow" },
        PortfolioValue_fund: { label: "Original", color: "red" },
    } satisfies Chart.ChartConfig;

    const metricToSeriesKey: Record<string, keyof typeof chartConfig> = {
        fund: "PortfolioValue_fund",
        copy: "PortfolioValue_copy",
        copy_scaled: "PortfolioValue_copy_scaled",
    };

    $: activeSeries = [
        {
            key: metricToSeriesKey[activeMetric],
            label: chartConfig[metricToSeriesKey[activeMetric]].label,
            color: chartConfig[metricToSeriesKey[activeMetric]].color,
        },
    ];

    $: if (
        allocationsDrawerOpen &&
        !allocationsData &&
        !isAllocationsLoading &&
        !allocationsError
    ) {
        loadAllocationsData();
    }
    
    // Formatters
    function formatPercent(val: any) {
        if (val === undefined || val === null) return "N/A";
        return `${(val * 100).toFixed(2)}%`;
    }

    function formatNumber(val: any) {
        if (val === undefined || val === null) return "N/A";
        return val.toFixed(2);
    }
</script>

<div bind:this={cardRef}>
    <Card.Root>
        <Card.Header>
             <div class="flex justify-between items-start gap-4">
                <div>
                   <Card.Title>
                        <a href="{base}/funds/{cik}" class="hover:underline transition-all">{@html fundData.name}</a>
                    </Card.Title>
                </div>
                <span class="text-xs text-muted-foreground/60 font-mono">CIK: {cik}</span>
            </div>
            
        </Card.Header>
        <Card.Content>
            <div class="space-y-4">
                {#if selectedMetrics}
                     <!-- Selector & Total Return -->
                    <div class="flex justify-between items-center bg-muted/30 p-1 rounded-lg">
                        <div class="flex flex-wrap gap-1">
                            <Tooltip.Provider delayDuration={0}>
                                {#each Object.entries(metrics) as [key, m]}
                                    <Tooltip.Root>
                                        <Tooltip.Trigger 
                                            class={buttonVariants({ 
                                                variant: activeMetric === key ? "secondary" : "ghost", 
                                                size: "sm", 
                                                className: "h-7 text-xs px-2" 
                                            })}
                                            onclick={() => activeMetric = key}
                                        >
                                            {m.label}
                                        </Tooltip.Trigger>
                                        <Tooltip.Content>
                                            <p class="max-w-xs">{m.tooltip}</p>
                                        </Tooltip.Content>
                                    </Tooltip.Root>
                                {/each}
                            </Tooltip.Provider>
                        </div>
                        
                        <!-- Total Return Badge -->
                        <div class={cn(
                            "h-7 px-2 flex items-center justify-center text-xs font-medium rounded-md border ml-2",
                            (selectedMetrics.total_return || 0) >= 0 ? "bg-green-500/10 text-green-600 border-green-200 dark:bg-green-500/20 dark:text-green-400 dark:border-green-800" : "bg-red-500/10 text-red-600 border-red-200 dark:bg-red-500/20 dark:text-red-400 dark:border-red-800"
                        )}>
                             {(selectedMetrics.total_return || 0) >= 0 ? "+":""}{((selectedMetrics.total_return || 0) * 100).toFixed(0)}%
                        </div>
                    </div>

                    <!-- Statistics Grid -->
                    <div class="grid grid-cols-3 gap-2">
                         <!-- Annualized Return -->
                        <div class={cn(
                            "rounded-md border p-2 flex flex-col items-center justify-center text-center",
                            (selectedMetrics.annualized_return || 0) >= 0 ? "bg-green-500/10 border-green-200 dark:border-green-800" : "bg-red-500/10 border-red-200 dark:border-red-800"
                        )}>
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Annualized</span>
                            <span class={cn("font-bold text-sm", (selectedMetrics.annualized_return || 0) >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
                                {formatPercent(selectedMetrics.annualized_return)}
                            </span>
                        </div>

                        <!-- Sharpe -->
                        <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Sharpe</span>
                            <span class="font-bold text-sm">{formatNumber(selectedMetrics.sharpe_ratio)}</span>
                        </div>
                        
                         <!-- Calmar -->
                        <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Calmar</span>
                            <span class="font-bold text-sm">{formatNumber(selectedMetrics.calmar_ratio)}</span>
                        </div>

                        <!-- Max Drawdown -->
                        <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Max Drawdown</span>
                            <span class="font-bold text-sm text-red-600 dark:text-red-400">{formatPercent(selectedMetrics.max_drawdown)}</span>
                        </div>

                        <!-- Active Allocations -->
                         <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Allocations</span>
                            <span class="font-bold text-sm whitespace-nowrap">{meta?.practical_update_date || "N/A"}</span>
                        </div>

                         <!-- Earliest Filing -->
                         <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                            <span class="text-[9px] text-muted-foreground uppercase tracking-wider">Earliest Filing</span>
                            <span class="font-bold text-sm whitespace-nowrap">{selectedMetrics.earliest_filing_date || "N/A"}</span>
                        </div>
                    </div>
                {/if}
                <div
                    class="relative h-[250px] pl-4 flex items-center justify-center rounded-md border"
                >
                    {#if chartVisible}
                        {#if isLoading}
                            <div class="flex w-full h-full items-end gap-2 p-4">
                                <Skeleton class="h-1/3 w-full" />
                                <Skeleton class="h-2/3 w-full" />
                                <Skeleton class="h-1/2 w-full" />
                                <Skeleton class="h-3/4 w-full" />
                                <Skeleton class="h-full w-full" />
                                <Skeleton class="h-1/2 w-full" />
                            </div>
                        {:else if error}
                            <div class="flex flex-col items-center gap-4">
                                <Alert.Root variant="destructive">
                                    <Alert.Title>Error</Alert.Title>
                                    <Alert.Description
                                        >{error}</Alert.Description
                                    >
                                </Alert.Root>
                                <Button onclick={loadChartData}>Retry</Button>
                            </div>
                        {:else if chartData}
                            <Button
                                variant="ghost"
                                size="icon"
                                class="absolute top-1 right-1 z-10 h-8 w-8"
                                onclick={() => (drawerOpen = true)}
                            >
                                <Expand class="h-3 w-3" />
                            </Button>
                            {#key activeMetric}
                                <Chart.Container
                                    config={chartConfig}
                                    class="aspect-auto h-full w-full"
                                >
                                    <LineChart
                                        data={chartData}
                                        x="date"
                                        xScale={scaleUtc()}
                                        series={activeSeries}
                                        props={{
                                            spline: {
                                                curve: curveNatural,
                                                motion: "tween",
                                                strokeWidth: 2,
                                            },
                                            yAxis: {
                                                ticks: 10,
                                                format: (v) =>
                                                    `${(v / 1000000).toFixed(1)}M`,
                                            },
                                            xAxis: {
                                                ticks: 5,
                                                format: (v) =>
                                                    v.toLocaleDateString(
                                                        "en-US",
                                                        {
                                                            month: "short",
                                                            year: "numeric",
                                                        },
                                                    ),
                                            },
                                            highlight: { points: { r: 4 } },
                                        }}
                                    />
                                </Chart.Container>
                            {/key}
                        {/if}
                    {:else}
                        <div class="text-center">
                            <p class="text-sm text-muted-foreground">
                                Scroll to load chart
                            </p>
                        </div>
                    {/if}
                </div>
                <Button onclick={() => (allocationsDrawerOpen = true)}
                    class="w-full" variant="outline">View Allocations</Button
                >
            </div>
        </Card.Content>
    </Card.Root>
</div>

<Drawer.Root bind:open={drawerOpen}>
    <Drawer.Content>
        {#if drawerOpen}
        <Drawer.Header>
            <Drawer.Title
                >{@html fundData.name} - Performance Chart</Drawer.Title
            >
        </Drawer.Header>
        <div class="h-[90vh] overflow-auto px-8 scrollbar-hide">
            {#if chartData}
                <Chart.Container
                    config={chartConfig}
                    class="aspect-auto h-full w-full"
                >
                    <LineChart
                        data={chartData}
                        x="date"
                        xScale={scaleUtc()}
                        series={[
                            {
                                key: "PortfolioValue_fund",
                                label: "Fund",
                                color: chartConfig.PortfolioValue_fund.color,
                            },
                            {
                                key: "PortfolioValue_copy",
                                label: "Copy",
                                color: chartConfig.PortfolioValue_copy.color,
                            },
                            {
                                key: "PortfolioValue_copy_scaled",
                                label: "Copy (Scaled)",
                                color: chartConfig.PortfolioValue_copy_scaled
                                    .color,
                            },
                        ]}
                        seriesLayout="stack"
                        legend
                        props={{
                            spline: {
                                curve: curveNatural,
                                motion: "tween",
                                strokeWidth: 2,
                            },

                            xAxis: {
                                ticks: 10,
                                format: (v) =>
                                    v.toLocaleDateString("en-US", {
                                        month: "short",
                                        year: "numeric",
                                    }),
                            },
                            yAxis: {
                                ticks: 10,
                                format: (v) => `${(v / 1000000).toFixed(1)}M`,
                            },
                        }}
                    />
                </Chart.Container>
            {/if}
        </div>
        {/if}
    </Drawer.Content>
</Drawer.Root>

<Drawer.Root bind:open={allocationsDrawerOpen}>
    <Drawer.Content>
        {#if allocationsDrawerOpen}
        <div class="p-4">
            <Drawer.Header>
                <Drawer.Title>{@html fundData.name} - Allocations</Drawer.Title>
                <Drawer.Description>
                    This page shows the current allocations for the hedge fund.<br />
                    Last updated: {meta?.technical_update_date || "N/A"}<br />
                    Last change in allocations: {meta?.practical_update_date || "N/A"}
                </Drawer.Description>
            </Drawer.Header>
            <div class="h-[90vh] overflow-auto">
                {#if isAllocationsLoading}
                    <p>Loading allocations...</p>
                {:else if allocationsError}
                    <div class="text-red-500">{allocationsError}</div>
                    <Button onclick={loadAllocationsData}>Retry</Button>
                {:else if allocationsData}
                    <AllocationsDataTable data={allocationsData} />
                {/if}
            </div>
        </div>
        {/if}
    </Drawer.Content>
</Drawer.Root>
