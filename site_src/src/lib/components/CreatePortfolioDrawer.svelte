<script lang="ts">
  import * as Drawer from "$lib/components/ui/drawer/index.js";
  import { Button } from "$lib/components/ui/button/index.js";
  import * as Select from "$lib/components/ui/select/index.js";
  import { Checkbox } from "$lib/components/ui/checkbox/index.js";
  import { Label } from "$lib/components/ui/label/index.js";
  import { onMount } from "svelte";

  export let funds: Record<string, any> | null = null;

  let selectedFunds: Record<string, boolean> = {};
  $: if (funds) {
    for (const cik of Object.keys(funds)) {
      if (!(cik in selectedFunds)) {
        selectedFunds[cik] = false;
      }
    }
    selectedFunds = selectedFunds;
  }

  let allocationMetric = "even";
  let isDownloading = false;

  const allocationOptions = [
    { value: "even", label: "Distribute Evenly" },
    { value: "sharpe_ratio_fund", label: "Sharpe Ratio (Original)" },
    { value: "calmar_ratio_fund", label: "Calmar Ratio (Original)" },
    { value: "total_return_fund", label: "Total Return (Original)" },
    { value: "sharpe_ratio_copy", label: "Sharpe Ratio (Copied)" },
    { value: "calmar_ratio_copy", label: "Calmar Ratio (Copied)" },
    { value: "total_return_copy", label: "Total Return (Copied)" },
    { value: "sharpe_ratio_copy_scaled", label: "Sharpe Ratio (Copied Scaled)" },
    { value: "calmar_ratio_copy_scaled", label: "Calmar Ratio (Copied Scaled)" },
    { value: "total_return_copy_scaled", label: "Total Return (Copied Scaled)" },
  ];

  function getMetricValue(fundData: any, metric: string) {
    if (metric === "even") return null;
    const value = fundData.backtest_results?.[metric];
    return typeof value === 'number' ? value : null;
  }

  async function downloadCSV() {
    isDownloading = true;
    try {
      const activeFundCiks = funds ? Object.keys(funds).filter(cik => selectedFunds[cik]) : [];
      if (activeFundCiks.length === 0) {
        alert("Please select at least one fund.");
        return;
      }

      const allocationPromises = activeFundCiks.map(async (cik) => {
        try {
          const response = await fetch(`https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations/${cik}.csv`);
          if (!response.ok) {
            console.error(`Failed to fetch allocations for CIK ${cik}`);
            return { cik, allocations: [] };
          }
          const csvText = await response.text();
          const rows = csvText.split('\n');
          const header = rows.shift()?.split(',');
          if (!header) return { cik, allocations: [] };

          const parsedData = rows.map(row => {
            const values = row.split(',');
            return header.reduce((obj, key, index) => {
              obj[key.trim()] = values[index];
              return obj;
            }, {});
          }).filter(d => d.ticker);

          return { cik, allocations: parsedData };
        } catch (e) {
          console.error(`Error processing allocations for CIK ${cik}:`, e);
          return { cik, allocations: [] };
        }
      });

      const fetchedAllocations = await Promise.all(allocationPromises);
      const allocationsMap = new Map(fetchedAllocations.map(item => [item.cik, item.allocations]));
      const activeFunds = activeFundCiks.map(cik => [cik, funds[cik]]);

      const totalMetricValue = activeFunds.reduce((sum, [cik, fundData]) => {
        if (allocationMetric === "even") {
          return sum + 1;
        }
        return sum + (fundData.backtest_results?.[allocationMetric] ?? 0);
      }, 0);

      const portfolioAllocations: Record<string, number> = {};

      for (const [cik, fundData] of activeFunds) {
        const weight = (allocationMetric === "even" || totalMetricValue === 0)
          ? 1 / activeFunds.length
          : (fundData.backtest_results?.[allocationMetric] ?? 0) / totalMetricValue;
        
        const fundAllocations = allocationsMap.get(cik);
        if (fundAllocations) {
          for (const allocation of fundAllocations) {
            const ticker = allocation.ticker;
            const percentage = parseFloat(allocation.allocation_percent);
            if (ticker && !isNaN(percentage)) {
              if (!portfolioAllocations[ticker]) {
                portfolioAllocations[ticker] = 0;
              }
              portfolioAllocations[ticker] += (percentage / 100) * weight;
            }
          }
        }
      }

      if (Object.keys(portfolioAllocations).length === 0) {
        alert("Could not generate portfolio. The selected funds may not have allocation data available, or the data may be invalid.");
        return;
      }

      let csvRows = ["Ticker,Percentage Allocation"];
      for (const [ticker, percentage] of Object.entries(portfolioAllocations)) {
        csvRows.push(`${ticker},${(percentage)}`);
      }
      const csvContent = csvRows.join("\n");

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.setAttribute("href", url);
      link.setAttribute("download", "portfolio_allocations.csv");
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

    } finally {
      isDownloading = false;
    }
  }

  $: fundsList = funds ? Object.entries(funds) : [];

  $: sortedFundsList = (() => {
    if (!fundsList) return [];
    if (allocationMetric === 'even') {
      return fundsList;
    }
    return [...fundsList].sort(([, a], [, b]) => {
      const valA = getMetricValue(a, allocationMetric) ?? -Infinity;
      const valB = getMetricValue(b, allocationMetric) ?? -Infinity;
      return valB - valA;
    });
  })();
</script>

<Drawer.Root>
  <Drawer.Trigger asChild>
    <Button variant="outline">Create a portfolio</Button>
  </Drawer.Trigger>
  <Drawer.Content class="h-[90vh]">
    <div class="p-4 h-full flex flex-col">
      <Drawer.Header>
        <Drawer.Title>Create a Portfolio</Drawer.Title>
        <Drawer.Description>Select funds to include in your portfolio and how to weight them.</Drawer.Description>
      </Drawer.Header>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 overflow-y-auto p-1 flex-grow">
        {#each sortedFundsList as [cik, fundData]}
          <Label
            class="hover:bg-accent/50 flex items-start gap-3 rounded-lg border p-3 has-[[aria-checked=true]]:border-blue-600 has-[[aria-checked=true]]:bg-blue-50 dark:has-[[aria-checked=true]]:border-blue-900 dark:has-[[aria-checked=true]]:bg-blue-950"
          >
            <Checkbox
              bind:checked={selectedFunds[cik]}
              class="data-[state=checked]:border-blue-600 data-[state=checked]:bg-blue-600 data-[state=checked]:text-white dark:data-[state=checked]:border-blue-700 dark:data-[state=checked]:bg-blue-700"
            />
            <div class="grid gap-1.5 font-normal">
              <p class="text-sm font-medium leading-none">{fundData.name}</p>
              <p class="text-muted-foreground text-sm">
                {#if allocationMetric !== 'even'}
                  {@const metricValue = getMetricValue(fundData, allocationMetric)}
                  {allocationOptions.find(o => o.value === allocationMetric)?.label}: 
                  {metricValue !== null ? metricValue.toFixed(2) : 'N/A'}
                {/if}
              </p>
            </div>
          </Label>
        {/each}
      </div>

      <Drawer.Footer class="pt-4 mt-auto">
        <div class="flex items-center gap-4">
          <Select.Root type="single" bind:value={allocationMetric}>
            <Select.Trigger class="w-[280px]">
              {allocationOptions.find(o => o.value === allocationMetric)?.label}
            </Select.Trigger>
            <Select.Content>
              {#each allocationOptions as option}
                <Select.Item value={option.value}>{option.label}</Select.Item>
              {/each}
            </Select.Content>
          </Select.Root>
          <Button onclick={downloadCSV} disabled={isDownloading}>
            {#if isDownloading}
              Loading...
            {:else}
              Download CSV
            {/if}
          </Button>
        </div>
      </Drawer.Footer>
    </div>
  </Drawer.Content>
</Drawer.Root>
