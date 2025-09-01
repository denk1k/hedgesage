<script lang="ts">
  import FundCard from '$lib/components/FundCard.svelte';
  import { onMount } from 'svelte';
  import * as Select from "$lib/components/ui/select/index.js";
  import * as Popover from "$lib/components/ui/popover/index.js";
  import * as Label from "$lib/components/ui/label/index.js";
  import * as Input from "$lib/components/ui/input/index.js";
  import { Button } from "$lib/components/ui/button/index.js";

  let funds: Record<string, any> | null = null;
  let error: string | null = null;
  let metricType = 'copy_scaled';
  let sortMetric = 'sharpe_ratio';

  let filterMetricType = 'copy';
  let minSharpe: number | null = 0.5;
  let minCalmar: number | null = 0.3;
  let maxDrawdownPercent: number | null = -40;
  let minTotalReturnPercent: number | null = 150;
  let minMonths: number | null = 120;

  $: maxDrawdown = maxDrawdownPercent !== null ? maxDrawdownPercent / 100 : null;
  $: minTotalReturn = minTotalReturnPercent !== null ? minTotalReturnPercent / 100 : null;

  const metricTypeOptions = [
    { value: 'fund', label: 'Original' },
    { value: 'copy', label: 'Copied' },
    { value: 'copy_scaled', label: 'Copied (Scaled)' },
  ];
  const longMetricTypeOptions = [
    { value: 'fund', label: 'Original' },
    { value: 'copy', label: 'Copied (at Filing Dates)' },
    { value: 'copy_scaled', label: 'Copied (at Filing Dates, Investments scaled to 100%)' },
  ];

  const sopt = [
    { value: 'sharpe_ratio', label: 'Sharpe Ratio' },
    { value: 'calmar_ratio', label: 'Calmar Ratio' },
    { value: 'total_return', label: 'Total Returns' },
    { value: 'max_drawdown', label: 'Maximum Drawdown' },
    { value: 'annualized_return', label: 'Annualized Return' },
  ];

  const sortmetrics_descending = [
    'sharpe_ratio',
    'calmar_ratio',
    'total_return',
    'annualized_return',
  ];

  function calculateMonths(filingDate: string): number {
    if (!filingDate) return 0;
    const start = new Date(filingDate);
    const end = new Date(); 

    let months;
    months = (end.getFullYear() - start.getFullYear()) * 12;
    months -= start.getMonth();
    months += end.getMonth();
    return months <= 0 ? 0 : months;
  }

  onMount(async () => {
    try {
      const response = await fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/top_funds.json');
      if (!response.ok) {
        throw new Error('Failed to fetch funds data');
      }
      funds = await response.json();
    } catch (e: any) {
      error = e.message;
    }
  });

  $: sortBy = `${sortMetric}_${metricType}`;

  $: filteredFunds = funds ? Object.entries(funds).filter(([, fundData]) => {
    const results = fundData.backtest_results;
    if (!results) return false;

    const sharpe = results[`sharpe_ratio_${filterMetricType}`];
    const calmar = results[`calmar_ratio_${filterMetricType}`];
    const drawdown = results[`max_drawdown_${filterMetricType}`];
    const totalReturn = results[`total_return_${filterMetricType}`];
    const months = calculateMonths(fundData.earliest_filing_date);

    if (minSharpe !== null && (sharpe === null || sharpe < minSharpe)) return false;
    if (minCalmar !== null && (calmar === null || calmar < minCalmar)) return false;
    if (maxDrawdown !== null && (drawdown === null || drawdown < maxDrawdown)) return false;
    if (minTotalReturn !== null && (totalReturn === null || totalReturn < minTotalReturn)) return false;
    if (minMonths !== null && (months === null || months < minMonths)) return false;

    return true;
  }) : [];

  $: sortedFunds = filteredFunds.sort(([, a], [, b]) => {
    const valA = a.backtest_results?.[sortBy];
    const valB = b.backtest_results?.[sortBy];

    if (valA != null && valB != null) {
      if (sortmetrics_descending.includes(sortMetric)) {
        return valB - valA;
      } else {
        return valA - valB;
      }
    }
    if (valA != null) return -1;
    if (valB != null) return 1;
    return 0;
  });
</script>

<main class="container mx-auto p-4">
  <div class="self-center relative left-1/2 -translate-x-1/2 w-[300px]">
    <img src="/hedgesage/logo-transparent.png" alt="HedgeSage Logo" class="mb-4" />
  </div>

<div class="flex items-center mb-4 gap-2">
  <h2 class="text-xl font-semibold">Hedge funds sorted by</h2>
  <Select.Root type="single" bind:value={metricType}>
    <Select.Trigger class="w-[180px]">
      {metricTypeOptions.find(o => o.value === metricType)?.label}
    </Select.Trigger>
    <Select.Content>
      {#each longMetricTypeOptions as option}
        <Select.Item value={option.value}>{option.label}</Select.Item>
      {/each}
    </Select.Content>
  </Select.Root>
  <Select.Root type="single" bind:value={sortMetric}>
    <Select.Trigger class="w-[220px]">
      {sopt.find(o => o.value === sortMetric)?.label}
    </Select.Trigger>
    <Select.Content>
      {#each sopt as option}
        <Select.Item value={option.value}>{option.label}</Select.Item>
      {/each}
    </Select.Content>
  </Select.Root>
    <div class="ml-auto flex items-center gap-4">
      {#if funds}
        <span class="text-sm text-muted-foreground">
          Showing {sortedFunds.length} of {Object.keys(funds).length} funds
        </span>
      {/if}
      <Popover.Root>
        <Popover.Trigger asChild>
          <Button variant="outline">Filter</Button>
        </Popover.Trigger>
        <Popover.Content class="w-80">
          <div class="grid gap-4">
            <div class="space-y-2">
              <h4 class="font-medium leading-none">Filters</h4>
              <p class="text-sm text-muted-foreground">
                Set the filters for the funds.
              </p>
            </div>
            <div class="grid gap-y-4">
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root>Filter by Type</Label.Root>
                <Select.Root type="single" bind:value={filterMetricType}>
                  <Select.Trigger class="col-span-2">
                    {metricTypeOptions.find(o => o.value === filterMetricType)?.label}
                  </Select.Trigger>
                  <Select.Content>
                    {#each metricTypeOptions as option}
                      <Select.Item value={option.value}>{option.label}</Select.Item>
                    {/each}
                  </Select.Content>
                </Select.Root>
              </div>
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root for="min-sharpe">Min Sharpe</Label.Root>
                <Input.Root id="min-sharpe" type="number" placeholder="0" bind:value={minSharpe} class="col-span-2" />
              </div>
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root for="min-calmar">Min Calmar</Label.Root>
                <Input.Root id="min-calmar" type="number" placeholder="0" bind:value={minCalmar} class="col-span-2" />
              </div>
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root for="max-drawdown">Max Drawdown (%)</Label.Root>
                <Input.Root id="max-drawdown" type="number" placeholder="-40" bind:value={maxDrawdownPercent} class="col-span-2" />
              </div>
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root for="min-return">Min Total Return (%)</Label.Root>
                <Input.Root id="min-return" type="number" placeholder="None" bind:value={minTotalReturnPercent} class="col-span-2" />
              </div>
              <div class="grid grid-cols-3 items-center gap-4">
                <Label.Root for="min-months">Min Months</Label.Root>
                <Input.Root id="min-months" type="number" placeholder="120" bind:value={minMonths} class="col-span-2" />
              </div>
            </div>
          </div>
        </Popover.Content>
      </Popover.Root>
    </div>
</div>
  
  {#if funds}
    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {#each sortedFunds as [cik, fundData] (cik)}
        <FundCard {cik} {fundData} metricType={metricType} />
      {/each}
    </div>
  {:else if error}
    <div class="text-red">{error}</div>
  {:else}
    <p>Loading funds...</p>
  {/if}
</main>