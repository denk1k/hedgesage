<script lang="ts">
    import * as Card from "$lib/components/ui/card/index.js";
    import * as Select from "$lib/components/ui/select/index.js";
    import * as Alert from "$lib/components/ui/alert/index.js";
    import * as Drawer from "$lib/components/ui/drawer/index.js";
    import * as Chart from "$lib/components/ui/chart/index.js";
    import { Button } from "$lib/components/ui/button";
    import { AreaChart, LineChart } from "layerchart";
    import { scaleUtc } from "d3-scale";
    import { curveNatural } from "d3-shape";
    import Expand from "@lucide/svelte/icons/expand";
    import AllocationsDataTable from "$lib/components/AllocationsDataTable.svelte";
    import { Skeleton } from "$lib/components/ui/skeleton/index.js";
    import { onMount, onDestroy } from "svelte";

    export let cik: string;
    export let fundData: any;
    let chartVisible = false;
    let cardRef: HTMLElement;

    export let metricType: string = "copy";
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

    const metricLabels: Record<string, string> = {
        fund: "Fund's Original Performance",
        copy: "Fund's Copied Performance",
        copy_scaled: "Fund's Copied Performance (Scaled)",
    };
    $: selectedLabel = metricLabels[metricType];

    $: selectedMetrics = fundData.backtest_results
        ? {
              earliest_filing_date: fundData.earliest_filing_date || null,
              total_return:
                  fundData.backtest_results[
                      `total_return${metricSuffixes[metricType]}`
                  ] ?? null,
              annualized_return:
                  fundData.backtest_results[
                      `annualized_return${metricSuffixes[metricType]}`
                  ] ?? null,
              sharpe_ratio:
                  fundData.backtest_results[
                      `sharpe_ratio${metricSuffixes[metricType]}`
                  ] ?? null,
              max_drawdown:
                  fundData.backtest_results[
                      `max_drawdown${metricSuffixes[metricType]}`
                  ] ?? null,
              calmar_ratio:
                  fundData.backtest_results[
                      `calmar_ratio${metricSuffixes[metricType]}`
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

    $: if (chartVisible && !chartData && !isLoading && !error) {
        loadChartData();
    } else if (!chartVisible && chartData) {
        chartData = null;
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
        PortfolioValue_copy: { label: "Copy", color: "blue" },
        PortfolioValue_copy_scaled: { label: "Copy (Scaled)", color: "yellow" },
        PortfolioValue_fund: { label: "Fund", color: "red" },
    } satisfies Chart.ChartConfig;

    const metricToSeriesKey: Record<string, keyof typeof chartConfig> = {
        fund: "PortfolioValue_fund",
        copy: "PortfolioValue_copy",
        copy_scaled: "PortfolioValue_copy_scaled",
    };

    $: activeSeries = [
        {
            key: metricToSeriesKey[metricType],
            label: chartConfig[metricToSeriesKey[metricType]].label,
            color: chartConfig[metricToSeriesKey[metricType]].color,
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
</script>

<div bind:this={cardRef}>
    <Card.Root>
        <Card.Header>
            <Card.Title>
                <span>{@html fundData.name}</span>
            </Card.Title>
            <Card.Description>CIK: {cik}</Card.Description>
        </Card.Header>
        <Card.Content>
            <div class="grid gap-4">
                {#if selectedMetrics}
                    <div>
                        <Select.Root type="single" bind:value={metricType}>
                            <Select.Trigger class="w-full">
                                {selectedLabel}
                            </Select.Trigger>
                            <Select.Content>
                                <Select.Item value="fund"
                                    >Fund's Original Performance</Select.Item
                                >
                                <Select.Item value="copy"
                                    >Copied Performance (Rebalances on Filing
                                    Dates)</Select.Item
                                >
                                <Select.Item value="copy_scaled"
                                    >Copied Performance (Rebalances on Filing
                                    Dates, Investments Scaled to 100% of
                                    Portfolio)</Select.Item
                                >
                            </Select.Content>
                        </Select.Root>
                    </div>
                    <div class="grid grid-cols-2 gap-2 text-sm">
                        <p>Earliest Filing Date:</p>
                        <p>{selectedMetrics.earliest_filing_date || "N/A"}</p>
                        <p>Total Return:</p>
                        <p>
                            {selectedMetrics.total_return !== null
                                ? (selectedMetrics.total_return * 100).toFixed(
                                      2,
                                  ) + "%"
                                : "N/A"}
                        </p>
                        <p>Annualized Return:</p>
                        <p>
                            {selectedMetrics.annualized_return !== null
                                ? (
                                      selectedMetrics.annualized_return * 100
                                  ).toFixed(2) + "%"
                                : "N/A"}
                        </p>
                        <p>Sharpe Ratio:</p>
                        <p>
                            {selectedMetrics.sharpe_ratio !== null
                                ? selectedMetrics.sharpe_ratio.toFixed(2)
                                : "N/A"}
                        </p>
                        <p>Max Drawdown:</p>
                        <p>
                            {selectedMetrics.max_drawdown !== null
                                ? (selectedMetrics.max_drawdown * 100).toFixed(
                                      2,
                                  ) + "%"
                                : "N/A"}
                        </p>
                        <p>Calmar Ratio:</p>
                        <p>
                            {selectedMetrics.calmar_ratio !== null
                                ? selectedMetrics.calmar_ratio.toFixed(2)
                                : "N/A"}
                        </p>
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
                            {#key metricType}
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
                    >View Allocations</Button
                >
            </div>
        </Card.Content>
    </Card.Root>
</div>

<Drawer.Root bind:open={drawerOpen}>
    <Drawer.Content>
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
    </Drawer.Content>
</Drawer.Root>

<Drawer.Root bind:open={allocationsDrawerOpen}>
    <Drawer.Content>
        <div class="p-4">
            <Drawer.Header>
                <Drawer.Title>{@html fundData.name} - Allocations</Drawer.Title>
                <Drawer.Description
                    >This page shows the current allocations for the hedge fund.
                    Last updated: .</Drawer.Description
                >
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
    </Drawer.Content>
</Drawer.Root>
