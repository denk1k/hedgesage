<script lang="ts">
  import FundCard from '$lib/components/FundCard.svelte';
  import { onMount } from 'svelte';
  import * as Select from "$lib/components/ui/select/index.js";

  let funds: Record<string, any> | null = null;
  let error: string | null = null;
  let sortBy = 'sharpe_ratio_copy';

  const sopt = [
    { value: 'sharpe_ratio_copy', label: 'Sharpe Ratio' },
    { value: 'calmar_ratio_copy', label: 'Calmar Ratio' },
    { value: 'total_return_copy', label: 'Total Returns' },
    { value: 'max_drawdown_copy', label: 'Maximum Drawdown' },
    { value: 'annualized_return_copy', label: 'Annualized Return' },
  ];

  $: selectedSortLabel = sopt.find(o => o.value === sortBy)?.label;

  const sortmetrics_descending = [
    'sharpe_ratio_copy',
    'calmar_ratio_copy',
    'total_return_copy',
    'annualized_return_copy',
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

  $: sortedFunds = funds ? Object.entries(funds).sort(([, a], [, b]) => {
    const valA = a.backtest_results?.[sortBy];
    const valB = b.backtest_results?.[sortBy];

    if (valA != null && valB != null) {
      if (sortmetrics_descending.includes(sortBy)) {
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

<div class="flex items-center mb-4">
  <h2 class="text-xl font-semibold mr-2">Top hedge funds by</h2>
  <Select.Root type="single" bind:value={sortBy}>
    <Select.Trigger class="w-[200px]">
      {selectedSortLabel}
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