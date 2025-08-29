<script lang="ts">
  import FundCard from '$lib/components/FundCard.svelte';
  import { onMount } from 'svelte';

  let funds: Record<string, any> | null = null;
  let error: string | null = null;

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

  $: sortedFunds = funds ? Object.entries(funds).sort(([, fundA], [, fundB]) => {
    const sharpe1 = fundA.backtest_results?.sharpe_ratio_copy;
    const sharpe2 = fundB.backtest_results?.sharpe_ratio_copy;

    if (sharpe1 != null && sharpe2 != null) {
      return sharpe2 - sharpe1;
    }
    if (sharpe1 != null) {
      return -1;
    }
    if (sharpe2 != null) {
      return 1;
    }
    return 0;
  }) : [];
</script>

<main class="container mx-auto p-4">
  <!-- <h1 class="text-3xl font-bold mb-4">Hedge Funds' Performance</h1> -->
   <div class="self-center relative left-1/2 -translate-x-1/2 w-[300px]">
    <img src="/hedgesage/logo-transparent.png" alt="HedgeSage Logo" class="mb-4" />
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