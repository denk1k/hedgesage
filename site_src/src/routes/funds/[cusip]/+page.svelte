<script lang="ts">
    import { page } from '$app/stores';
    import { goto } from '$app/navigation';
    import Header from "$lib/components/Header.svelte";
    import * as Card from "$lib/components/ui/card/index.js";
    import * as Select from "$lib/components/ui/select/index.js";
    import * as Tooltip from "$lib/components/ui/tooltip/index";
    import { Button, buttonVariants } from "$lib/components/ui/button";
    import { Separator } from "$lib/components/ui/separator/index.js";
    import { Skeleton } from "$lib/components/ui/skeleton/index.js";
    import * as Chart from "$lib/components/ui/chart/index.js";
    import { LineChart } from "layerchart";
    import { scaleUtc } from "d3-scale";
    import { curveNatural } from "d3-shape";
    import ArrowLeft from "@lucide/svelte/icons/arrow-left";
    import AllocationsDataTable from "$lib/components/AllocationsDataTable.svelte";
    import FundAllocationPieChart from "$lib/components/FundAllocationPieChart.svelte";
    import { onMount } from 'svelte';
    import { cn } from "$lib/utils";

    export let data;
    const { cusip, fundData, meta } = data;

    let chartData: any[] | null = null;
    let fullChartData: any[] | null = null; // Store full data for filtering
    let isLoading = false;
    let error: string | null = null;

    let allocationsData: any[] | null = null;
    let isAllocationsLoading = false;
    let allocationsError: string | null = null;

    // Selectors
    let selectedMetric: 'copy' | 'copy_scaled' | 'fund' = 'copy';
    let selectedTimeframe: 'all' | '1y' | '30d' | '7d' = 'all';

    // Metrics Metadata
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

    // Derived Statistics
    $: selectedStats = fundData.backtest_results ? {
        annualized_return: fundData.backtest_results[`annualized_return${metrics[selectedMetric].suffix}`],
        sharpe_ratio: fundData.backtest_results[`sharpe_ratio${metrics[selectedMetric].suffix}`],
        max_drawdown: fundData.backtest_results[`max_drawdown${metrics[selectedMetric].suffix}`],
        calmar_ratio: fundData.backtest_results[`calmar_ratio${metrics[selectedMetric].suffix}`],
        earliest_filing_date: fundData.earliest_filing_date,
    } : null;

    // Chart Config
    const chartConfig = {
        PortfolioValue_copy: { label: "Copied", color: "blue" },
        PortfolioValue_copy_scaled: { label: "Copied (Scaled)", color: "yellow" },
        PortfolioValue_fund: { label: "Original", color: "red" }
    };


    async function loadChartData() {
        isLoading = true;
        error = null;
        try {
            const url = `https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/backtests/${cusip}_backtest_values.csv`;
            console.log("Fetching url:", url);
            const response = await fetch(url);
            if (!response.ok) throw new Error("Chart data not available for this fund.");
            const text = await response.text();
            console.log("Fetched text length:", text.length);
            
            const rows = text.split('\n').slice(1);
            const parseValue = (val: string) => val.trim() === "" ? null : +val;
            
             const parsed = rows.map(row => {
                 const [date, copy, copy_scaled, fund] = row.split(",");
                 if (!date) return null;
                 return {
                     date: new Date(date),
                     PortfolioValue_copy: parseValue(copy),
                     PortfolioValue_copy_scaled: parseValue(copy_scaled),
                     PortfolioValue_fund: parseValue(fund)
                 };
             }).filter(d => d && d.date && !isNaN(d.date.valueOf()));
             
             console.log("Parsed rows:", parsed.length);

             fullChartData = parsed;
             filterChartData();
        } catch (e: any) {
            console.error("loadChartData error:", e);
            error = e.message;
        } finally {
            isLoading = false;
        }
    }

    async function loadAllocationsData() {
        isAllocationsLoading = true;
        allocationsError = null;
        try {
            const response = await fetch(`https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations/${cusip}.csv`);
            if (!response.ok) throw new Error("Allocations data not available");
            const text = await response.text();
             
             const rows = text.split('\n');
             const header = rows.shift()?.split(",");
             if (!header) throw new Error("Invalid CSV header");

             const parsed = rows.map(row => {
                 const values = row.split(',');
                 return header.reduce((obj: any, key, index) => {
                     obj[key.trim()] = values[index];
                     return obj;
                 }, {});
             }).filter(d => d.ticker);
             
             allocationsData = parsed;
        } catch (e: any) {
            allocationsError = e.message;
        } finally {
            isAllocationsLoading = false;
        }
    }

    function filterChartData() {
        if (!fullChartData) return;
        
        if (selectedTimeframe === 'all') {
            chartData = fullChartData;
            return;
        }

        const lastPoint = fullChartData[fullChartData.length - 1];
        if (!lastPoint) return;
        
        const now = new Date(lastPoint.date); 
        const cutoff = new Date(now);
        
        if (selectedTimeframe === '30d') {
            cutoff.setDate(cutoff.getDate() - 30);
        } else if (selectedTimeframe === '7d') {
            cutoff.setDate(cutoff.getDate() - 7);
        } else if (selectedTimeframe === '1y') {
            cutoff.setFullYear(cutoff.getFullYear() - 1);
        }
        
        chartData = fullChartData.filter(d => d.date >= cutoff);
    }

    $: if (selectedTimeframe && fullChartData) {
        filterChartData();
    }

    function calculateStartValue(data: any[], key: string) {
        if (!data || data.length === 0) return null;
        return data[0][key];
    }
    
    function calculateEndValue(data: any[], key: string) {
        if (!data || data.length === 0) return null;
        // Last available value
        for(let i = data.length - 1; i >= 0; i--) {
            if (data[i][key] !== null && data[i][key] !== undefined) return data[i][key];
        }
        return null;
    }

    function calculateGainForTimeframe(tf: 'all' | '1y' | '30d' | '7d', data: any[], metric: string) {
        if (!data) return null;

        const seriesKey = `PortfolioValue_${metric}`;

        if (tf === 'all') {
             // For All Time, try to use the fundData total return if available, matching FundCard.
             const metricSuffix = metrics[metric as keyof typeof metrics].suffix;
             const totalReturn = fundData.backtest_results?.[`total_return${metricSuffix}`];
             if (totalReturn !== undefined && totalReturn !== null) {
                 return totalReturn;
             }
             // Fallback to calculation
             const start = calculateStartValue(data, seriesKey);
             const end = calculateEndValue(data, seriesKey);
             if (start && end) return (end - start) / start;
             return null;
        }

        const lastPoint = data[data.length - 1];
        if (!lastPoint) return null;
        
        const now = new Date(lastPoint.date); 
        const cutoff = new Date(now);

        if (tf === '30d') cutoff.setDate(cutoff.getDate() - 30);
        else if (tf === '7d') cutoff.setDate(cutoff.getDate() - 7);
        else if (tf === '1y') cutoff.setFullYear(cutoff.getFullYear() - 1);

        // Find the data point closest to cutoff (>= cutoff)
        // Since data is sorted by date
        const startIndex = data.findIndex(d => d.date >= cutoff);
        if (startIndex === -1) return null;
        
        const startVal = data[startIndex][seriesKey];
        const endVal = calculateEndValue(data, seriesKey); // Use the very last value available

        if (startVal && endVal) {
            return (endVal - startVal) / startVal;
        }

        return null;
    }

    $: currentGain = calculateGainForTimeframe(selectedTimeframe, fullChartData || [], selectedMetric);
    
    // Formatting helpers
    function formatGain(val: number | null) {
        if (val === null) return "N/A";
        const sign = val >= 0 ? "+" : "";
        return `${sign}${(val * 100).toFixed(2)}%`;
    }

    function formatPercent(val: any) {
        if (val === undefined || val === null) return "N/A";
        return `${(val * 100).toFixed(2)}%`;
    }

    function formatNumber(val: any) {
        if (val === undefined || val === null) return "N/A";
        return val.toFixed(2);
    }

    onMount(() => {
        loadChartData();
        loadAllocationsData();
    });

</script>

<div class="min-h-screen bg-background">
    <!-- Header -->
    <Header funds={Object.entries(data.funds)} defaultAllocationStrategy="sharpe_ratio_copy" /> 

    <main class="container mx-auto p-4 space-y-6">
        <!-- Back Link -->
        <a href="/" class="inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors group">
            <ArrowLeft class="mr-2 h-4 w-4 group-hover:-translate-x-1 transition-transform" />
            Back to main page
        </a>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch lg:min-h-[600px]">
            <!-- Left Column: Graph + Stats (Bentobox) -->
            <div class="lg:col-span-2 flex flex-col gap-6 h-full">
                
                <Card.Root class="flex-grow flex flex-col min-h-[300px]">
                    <Card.Header>
                         <div class="space-y-4">
                            <div class="flex justify-between items-start gap-4">
                                <div>
                                    <Card.Title class="text-xl">{@html fundData.name}</Card.Title>
                                    <Card.Description>Performance Analysis</Card.Description>
                                </div>
                                <span class="text-xs text-muted-foreground/60 font-mono">CIK: {cusip}</span>
                            </div>
                            
                            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                                 <!-- Metric Selectors (Left) -->
                                <div class="flex flex-wrap gap-2">
                                    <Tooltip.Provider delayDuration={0}>
                                        {#each Object.entries(metrics) as [key, m]}
                                            <Tooltip.Root>
                                                <Tooltip.Trigger 
                                                    class={buttonVariants({ 
                                                        variant: selectedMetric === key ? "secondary" : "ghost", 
                                                        size: "sm", 
                                                        className: "h-7 text-xs px-2" 
                                                    })}
                                                    onclick={() => selectedMetric = key as any}
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

                                <!-- Timeframe Selectors (Right) -->
                                <div class="flex items-center gap-2">
                                     <!-- Gain Display -->
                                     <div class={cn(
                                         "h-7 px-2 flex items-center justify-center text-xs font-medium rounded-md border",
                                         currentGain !== null && currentGain >= 0 ? "bg-green-500/10 text-green-600 border-green-200 dark:bg-green-500/20 dark:text-green-400 dark:border-green-800" : "",
                                         currentGain !== null && currentGain < 0 ? "bg-red-500/10 text-red-600 border-red-200 dark:bg-red-500/20 dark:text-red-400 dark:border-red-800" : "",
                                         currentGain === null ? "bg-muted text-muted-foreground" : ""
                                     )}>
                                         {formatGain(currentGain)}
                                     </div>

                                    <div class="flex gap-1">
                                        <Tooltip.Provider delayDuration={0}>
                                            {#each ['all', '1y', '30d', '7d'] as tf}
                                               {@const gain = calculateGainForTimeframe(tf, fullChartData || [], selectedMetric)}
                                               <Tooltip.Root>
                                                    <Tooltip.Trigger 
                                                        class={buttonVariants({ 
                                                            variant: selectedTimeframe === tf ? "secondary" : "ghost", 
                                                            size: "sm", 
                                                            className: "h-7 text-xs px-2" 
                                                        })}
                                                        onclick={() => selectedTimeframe = tf as any}
                                                    >
                                                        {tf === 'all' ? 'All Time' : tf === '1y' ? '1y' : tf === '30d' ? '30d' : '7d'}
                                                    </Tooltip.Trigger>
                                                    <Tooltip.Content>
                                                        <p>Gain: {formatGain(gain)}</p>
                                                    </Tooltip.Content>
                                               </Tooltip.Root>
                                            {/each}
                                        </Tooltip.Provider>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </Card.Header>
                    <Card.Content class="flex-1 min-h-0">
                         <div class="h-full w-full">
                            {#if isLoading}
                                <Skeleton class="h-full w-full" />
                            {:else if error}
                                <div class="flex items-center justify-center h-full text-destructive">
                                    {error}
                                </div>
                            {:else if chartData}
                                <Chart.Container config={chartConfig} class="h-full w-full">
                                    <LineChart
                                        data={chartData}
                                        x="date"
                                        xScale={scaleUtc()}
                                        series={[
                                            {
                                                key: `PortfolioValue_${selectedMetric}`,
                                                label: metrics[selectedMetric].label,
                                                color: chartConfig[`PortfolioValue_${selectedMetric}`].color
                                            }
                                        ]}
                                        props={{
                                            spline: {
                                                curve: curveNatural,
                                                motion: "tween",
                                                strokeWidth: 2,
                                            },
                                            yAxis: {
                                                ticks: 5,
                                                format: (v) => `$${(v / 1000000).toFixed(1)}M`
                                            },
                                            xAxis: {
                                                ticks: 5,
                                                format: (v) => {
                                                    if (selectedTimeframe === '30d' || selectedTimeframe === '7d') {
                                                        return v.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                                                    }
                                                    return v.toLocaleDateString("en-US", { month: "short", year: "numeric" });
                                                }
                                            },
                                            highlight: { points: { r: 4 } },
                                            tooltip: {
                                                
                                            }
                                        }}
                                    />
                                </Chart.Container>
                            {:else}
                                <div class="text-center py-10 text-muted-foreground">No data available</div>
                            {/if}
                         </div>
                    </Card.Content>
                </Card.Root>

                <!-- Stats Card -->
                <Card.Root class="flex-shrink-0 py-0">
                    <Card.Content class="h-full p-4 flex items-center">
                        <div class="w-full grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                            {#if selectedStats}
                                <!-- AR -->
                                <div class={cn(
                                    "rounded-md border p-2 flex flex-col items-center justify-center text-center",
                                    (selectedStats.annualized_return || 0) >= 0 ? "bg-green-500/10 border-green-200 dark:border-green-800" : "bg-red-500/10 border-red-200 dark:border-red-800"
                                )}>
                                    <span class="text-[10px] text-muted-foreground uppercase tracking-wider">Annualized</span>
                                    <span class={cn("font-bold", (selectedStats.annualized_return || 0) >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400")}>
                                        {formatPercent(selectedStats.annualized_return)}
                                    </span>
                                </div>

                                <!-- Sharpe -->
                                <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                                    <span class="text-[10px] text-muted-foreground uppercase tracking-wider">Sharpe</span>
                                    <span class="font-bold">{formatNumber(selectedStats.sharpe_ratio)}</span>
                                </div>
                                
                                <!-- MDD -->
                                <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                                    <span class="text-[10px] text-muted-foreground uppercase tracking-wider">Max Drawdown</span>
                                    <span class="font-bold text-red-600 dark:text-red-400">{formatPercent(selectedStats.max_drawdown)}</span>
                                </div>

                                <!-- Calmar -->
                                <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                                    <span class="text-[10px] text-muted-foreground uppercase tracking-wider">Calmar</span>
                                    <span class="font-bold">{formatNumber(selectedStats.calmar_ratio)}</span>
                                </div>

                                <!-- Earliest Filing -->
                                <div class="rounded-md border p-2 flex flex-col items-center justify-center text-center bg-card">
                                    <span class="text-[10px] text-muted-foreground uppercase tracking-wider">Earliest Filing</span>
                                    <span class="font-bold whitespace-nowrap">{selectedStats.earliest_filing_date || "N/A"}</span>
                                </div>
                            {:else}
                                <Skeleton class="h-12 w-full col-span-full" />
                            {/if}
                        </div>
                    </Card.Content>
                </Card.Root>
            </div>

            <!-- Radial Chart -->
            <div class="h-full">
                <FundAllocationPieChart 
                    data={allocationsData || []} 
                    technical_update_date={meta?.technical_update_date}
                    practical_update_date={meta?.practical_update_date}
                />
            </div>
        </div>

        <!-- Allocations Table -->
        <div class="pt-8">
            <h2 class="text-2xl font-bold mb-4">Current Allocations</h2>
            {#if isAllocationsLoading}
                 <Skeleton class="h-64 w-full" />
            {:else if allocationsError}
                 <div class="text-destructive">Failed to load allocations: {allocationsError}</div>
            {:else if allocationsData}
                 <AllocationsDataTable data={allocationsData} />
            {/if}
        </div>
    </main>
</div>
