<script lang="ts">
  import FundCard from '$lib/components/FundCard.svelte';
  import { onMount } from 'svelte';
  import * as Select from "$lib/components/ui/select/index.js";

  let funds: Record<string, any> | null = null;
  let error: string | null = null;

  let metricType = 'copy';
  let sortMetric = 'sharpe_ratio';

  const metricTypeOptions = [
    { value: 'fund', label: 'Original' },
    { value: 'copy', label: 'Copied' },
    { value: 'copy_scaled', label: 'Copied (Scaled)' },
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

  $: sortedFunds = funds ? Object.entries(funds).sort(([, a], [, b]) => {
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
  }) : [];
</script>

<main class="container mx-auto p-4">
  <!-- <h1 class="text-3xl font-bold mb-4">Hedge Funds' Performance</h1> -->
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
      {#each metricTypeOptions as option}
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
</div>
  
  {#if funds}
    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {#each sortedFunds as [cik, fundData]}
        <FundCard {cik} {fundData} />
      {/each}
    </div>
  {:else if error}
    <div class="text-red">{error}</div>
  {:else}
    <p>Loading funds...</p>
  {/if}
</main>