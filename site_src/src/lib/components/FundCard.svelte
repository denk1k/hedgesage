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

  export let cik: string;
  export let fundData: any;

  let metricType: string = 'copy';
  let chartData: any[] | null = null;
  let isLoading = false;
  let error: string | null = null;
  let drawerOpen = false;

  const metricSuffixes: Record<string, string> = {
    fund: '_fund',
    copy: '_copy',
    copy_scaled: '_copy_scaled'
  };

  const metricLabels: Record<string, string> = {
    fund: "Fund's Original Performance",
    copy: "Copied Performance (Filing Dates)",
    copy_scaled: "Copied Performance (Filing Dates, Scaled)"
  };
  $: selectedLabel = metricLabels[metricType];

  $: selectedMetrics = fundData.backtest_results ? {
    total_return: fundData.backtest_results[`total_return${metricSuffixes[metricType]}`] ?? null,
    annualized_return: fundData.backtest_results[`annualized_return${metricSuffixes[metricType]}`] ?? null,
    sharpe_ratio: fundData.backtest_results[`sharpe_ratio${metricSuffixes[metricType]}`] ?? null,
    max_drawdown: fundData.backtest_results[`max_drawdown${metricSuffixes[metricType]}`] ?? null,
    calmar_ratio: fundData.backtest_results[`calmar_ratio${metricSuffixes[metricType]}`] ?? null
  } : null;

  async function loadChartData() {
    console.log('loadChartData called for CIK:', cik);
    isLoading = true;
    error = null;
    try {
      const response = await fetch(`https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/backtests/${cik}_backtest_values.csv`);
      console.log('fetch response:', response);
      if (!response.ok) {
        throw new Error(`Chart data not available for this fund.`);
      }
      const csvText = await response.text();
      const rows = csvText.split('\n').slice(1); // skip header
      const parseValue = (val: string) => val.trim() === '' ? null : +val;
      const parsedData = rows
        .map(row => {
            const [date, copy, copy_scaled, fund] = row.split(',');
            if (!date) return null;
            return {
              date: new Date(date),
              PortfolioValue_copy: parseValue(copy),
              PortfolioValue_copy_scaled: parseValue(copy_scaled),
              PortfolioValue_fund: parseValue(fund)
            };
        })
        .filter((d): d is Exclude<typeof d, null> => d !== null && d.date instanceof Date && !isNaN(d.date.valueOf()));
      
      console.log('parsedData:', parsedData);
      if (parsedData.length === 0) {
        throw new Error('CSV invalid');
      }
      chartData = parsedData;
      console.log(chartData)

    } catch (e: any) {
      console.error('Error in loadChartData:', e);
      error = e.message;
    } finally {
      isLoading = false;
    }
  }

  const chartConfig = {
    PortfolioValue_copy: { label: "Copy", color: "blue" },
    PortfolioValue_copy_scaled: { label: "Copy (Scaled)", color: "yellow" },
    PortfolioValue_fund: { label: "Fund", color: "red" },
  } satisfies Chart.ChartConfig;

  const metricToSeriesKey = {
    fund: "PortfolioValue_fund",
    copy: "PortfolioValue_copy",
    copy_scaled: "PortfolioValue_copy_scaled"
  };

  $: activeSeries = [{
    key: metricToSeriesKey[metricType],
    label: chartConfig[metricToSeriesKey[metricType]].label,
    color: chartConfig[metricToSeriesKey[metricType]].color
  }];

</script>

<Card.Root>
  <Card.Header>
    <Card.Title class="flex justify-between items-start">
      <span>{fundData.name}</span>
      {#if chartData}
        <Button variant="ghost" size="icon" onclick={() => drawerOpen = true}>
          <Expand class="h-4 w-4" />
        </Button>
      {/if}
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
              <Select.Item value="fund">Fund's Original Performance</Select.Item>
              <Select.Item value="copy">Copied Performance (Filing Dates)</Select.Item>
              <Select.Item value="copy_scaled">Copied Performance (Filing Dates, Scaled)</Select.Item>
            </Select.Content>
          </Select.Root>
        </div>
        <div class="grid grid-cols-2 gap-2 text-sm">
          <p>Total Return:</p><p>{selectedMetrics.total_return !== null ? (selectedMetrics.total_return * 100).toFixed(2) + '%' : 'N/A'}</p>
          <p>Annualized Return:</p><p>{selectedMetrics.annualized_return !== null ? (selectedMetrics.annualized_return * 100).toFixed(2) + '%' : 'N/A'}</p>
          <p>Sharpe Ratio:</p><p>{selectedMetrics.sharpe_ratio !== null ? selectedMetrics.sharpe_ratio.toFixed(2) : 'N/A'}</p>
          <p>Max Drawdown:</p><p>{selectedMetrics.max_drawdown !== null ? (selectedMetrics.max_drawdown * 100).toFixed(2) + '%' : 'N/A'}</p>
          <p>Calmar Ratio:</p><p>{selectedMetrics.calmar_ratio !== null ? selectedMetrics.calmar_ratio.toFixed(2) : 'N/A'}</p>
        </div>
      {/if}
      <div class="h-[250px] flex items-center justify-center rounded-md border">
        {#if chartData}
          <Chart.Container config={chartConfig} class="aspect-auto h-full w-full">
            <LineChart
              data={chartData}
              x="date"
              xScale={scaleUtc()}
              
              series={activeSeries}
              props={{
                spline: { curve: curveNatural, motion: "tween", strokeWidth: 2 },
                yAxis: {
                  ticks: 10,
                  format: (v) => `${(v/1000000).toFixed(1)}M`,
                },
                xAxis: {
                  format: (v: Date) => {
                    return v.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    });
                  },
                },
                highlight: { points: { r: 4 } },
              }}
            />
          </Chart.Container>
        {:else if isLoading}
          <p>Loading...</p>
        {:else if error}
          <Alert.Root variant="destructive">
            <Alert.Title>Error</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        {:else}
          <Button onclick={loadChartData}>Load Chart</Button>
        {/if}
      </div>
    </div>
  </Card.Content>
</Card.Root>

<Drawer.Root bind:open={drawerOpen}>
  <Drawer.Content>
    <Drawer.Header>
      <Drawer.Title>{fundData.name} - Performance Chart</Drawer.Title>
    </Drawer.Header>
    <div class="h-[90vh] overflow-auto px-4">
      {#if chartData}
        <Chart.Container config={chartConfig} class="aspect-auto h-full w-full">
          <LineChart
            data={chartData}
            x="date"
            xScale={scaleUtc()}
            series={[ 
                { key: "PortfolioValue_fund", label: "Fund", color: chartConfig.PortfolioValue_fund.color },
                { key: "PortfolioValue_copy", label: "Copy", color: chartConfig.PortfolioValue_copy.color },
                { key: "PortfolioValue_copy_scaled", label: "Copy (Scaled)", color: chartConfig.PortfolioValue_copy_scaled.color },
              ]}
            seriesLayout="stack"
            legend
            props={{
              spline: { curve: curveNatural, motion: "tween", strokeWidth: 2 },

              xAxis: {
                format: (v: Date) => {
                  return v.toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  });
                },
              },
              yAxis: {
                ticks: 10,
                format: (v) => `${(v/1000000).toFixed(1)}M`,
              },
            }}
          />
        </Chart.Container>
      {/if}
    </div>
  </Drawer.Content>
</Drawer.Root>
