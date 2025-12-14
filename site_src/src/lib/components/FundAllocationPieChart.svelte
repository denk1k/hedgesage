<script lang="ts">
  import TrendingUpIcon from "@lucide/svelte/icons/trending-up";
  import * as Chart from "$lib/components/ui/chart/index.js";
  import * as Card from "$lib/components/ui/card/index.js";
  import { PieChart, Text } from "layerchart";
  import { type ComponentProps } from "svelte";

  export let data: any[] = [];
  export let technical_update_date: string = "N/A";
  export let practical_update_date: string = "N/A";

  // Process data for the chart
  // Group into Top 4 + Other
  $: processedData = (() => {
      if (!data || data.length === 0) return [];
      
      const sorted = [...data].sort((a, b) => parseFloat(b.value) - parseFloat(a.value));
      
      let splitIndex = sorted.length;
      let otherSum = 0;
      
      // calc split point where Sum(Others) < Last Element Value
      
      const totalSum = sorted.reduce((acc, curr) => acc + parseFloat(curr.value), 0);
      let currentTopSum = 0;
      
      for (let i = 0; i < sorted.length; i++) {
          const val = parseFloat(sorted[i].value);
          // If we stop here (include i), Other is (Total - (currentTopSum + val))
          const potentialOther = totalSum - (currentTopSum + val);
          
          if (potentialOther < val) {
              splitIndex = i + 1;
              break;
          }
          currentTopSum += val;
      }
      
      // Safety cap to prevent too many slices if distribution is flat (optional but good practice, keeping ample space)
      // if (splitIndex > 30) splitIndex = 30;

      const top = sorted.slice(0, splitIndex);
      const others = sorted.slice(splitIndex);
      
      const otherValue = others.reduce((acc, curr) => acc + parseFloat(curr.value), 0);
      const otherAllocation = others.reduce((acc, curr) => acc + parseFloat(curr.allocation_percent), 0);
      
      const chartItems = top.map((item, index) => {
          // Cycle through 5 chart colors
          const colorIndex = (index % 5) + 1;
          // Darken for each subsequent loop (0%, 20%, 40%...)
          const darkenPercent = Math.floor(index / 5) * 20;
          
          return {
              fund: item.nameOfIssuer, 
              investments: parseFloat(item.value),
              allocation: parseFloat(item.allocation_percent),
              // Use color-mix to lighten the variable color
              color: `color-mix(in srgb, var(--chart-${colorIndex}), white ${darkenPercent}%)`,
              name: item.nameOfIssuer
          };
      });

      if (others.length > 0) {
          chartItems.push({
              fund: "Other",
              investments: otherValue,
              allocation: otherAllocation,
              color: "hsl(0, 0%, 60%)", // Gray
              name: "Other"
          });
      }
      return chartItems;
  })();

  $: chartConfig = processedData.reduce((acc, curr, i) => {
      acc[curr.fund] = {
          label: curr.name,
          color: curr.color
      };
      return acc;
  }, {
      investments: { label: "Value" }
  } as any); // Type cast as simpler approach than full ChartConfig for now

  $: totalValue = processedData.reduce((acc, curr) => acc + curr.investments, 0);
  
  // Format total value for display (e.g. $1.2B)
  const formatValue = (val: number) => {
      if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
      if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
      return `$${val.toLocaleString()}`;
  };
</script>

<Card.Root class="flex flex-col h-full w-full">
  <Card.Header class="items-center">
    <Card.Title>Current Allocation</Card.Title>
    <Card.Description>Top Holdings</Card.Description>
  </Card.Header>
  <Card.Content class="flex-1">
    <Chart.Container config={chartConfig} class="aspect-square w-full">
      <PieChart
        data={processedData}
        key="fund"
        value="investments"
        c="color"
        innerRadius={80}
        padding={28}
        props={{ pie: { motion: "tween" } }}
      >
        {#snippet aboveMarks()}
            <Text
              value={formatValue(totalValue)}
              textAnchor="middle"
              verticalAnchor="middle"
              class="fill-foreground text-2xl! font-bold"
              dy={0}
            />
            <Text
              value="Total Invested"
              textAnchor="middle"
              verticalAnchor="middle"
              class="fill-muted-foreground! text-muted-foreground"
              dy={20}
            />
        {/snippet}
        {#snippet tooltip()}
             <Chart.Tooltip 
                hideLabel
            />
        {/snippet}
      </PieChart>
    </Chart.Container>
  </Card.Content>
  <Card.Footer class="flex-col gap-1 text-sm pt-0 pb-2">
    <div class="flex items-center gap-2 font-medium leading-none">
        Last changed: {practical_update_date}
    </div>
    <div class="flex items-center gap-2 font-medium leading-none">
        Last fetched: {technical_update_date}
    </div>
  </Card.Footer>
</Card.Root>
