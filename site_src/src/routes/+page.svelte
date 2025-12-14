<script lang="ts">
    import FundCard from "$lib/components/FundCard.svelte";
    import * as Select from "$lib/components/ui/select/index.js";
    import * as Popover from "$lib/components/ui/popover/index.js";
    import * as Label from "$lib/components/ui/label/index.js";
    import * as Input from "$lib/components/ui/input/index.js";
    import { Button } from "$lib/components/ui/button/index.js";
    import Header from "$lib/components/Header.svelte";
    import * as InputGroup from "$lib/components/ui/input-group/index.js";
    import SearchIcon from "@lucide/svelte/icons/search";
    import FilterIcon from "@lucide/svelte/icons/filter";
    import * as Pagination from "$lib/components/ui/pagination/index.js";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { browser } from "$app/environment";

    export let data;

    $: funds = data.funds;

    let metricType = "copy_scaled";
    let sortMetric = "sharpe_ratio";
    let searchQuery = "";

    let filterMetricType = "copy";
    let minSharpe: number | null = 0.5;
    let minCalmar: number | null = 0.3;
    let maxDrawdownPercent: number | null = -40;
    let minTotalReturnPercent: number | null = 150;
    let minAnnualizedReturnPercent: number | null = 10;
    let minMonths: number | null = 120;

    // Check for filters=clear URL parameter
    $: filtersCleared = browser && $page.url.searchParams.get('filters') === 'clear';

    // Pagination
    const itemsPerPage = 24;
    $: currentPage = browser && $page.url.searchParams.get('page') ? Number($page.url.searchParams.get('page')) : 1;

    // Clear filters function
    function clearFilters() {
        minSharpe = null;
        minCalmar = null;
        maxDrawdownPercent = null;
        minTotalReturnPercent = null;
        minAnnualizedReturnPercent = null;
        minMonths = null;
        searchQuery = "";
    }

    // React to filtersCleared change
    $: if (filtersCleared) {
        clearFilters();
    }

    $: maxDrawdown =
        maxDrawdownPercent !== null ? maxDrawdownPercent / 100 : null;
    $: minTotalReturn =
        minTotalReturnPercent !== null ? minTotalReturnPercent / 100 : null;
    $: minAnnualizedReturn =
        minAnnualizedReturnPercent !== null
            ? minAnnualizedReturnPercent / 100
            : null;

    const metricTypeOptions = [
        { value: "fund", label: "Original" },
        { value: "copy", label: "Copied" },
        { value: "copy_scaled", label: "Copied (Scaled)" },
    ];
    const longMetricTypeOptions = [
        { value: "fund", label: "Original" },
        { value: "copy", label: "Copied (Rebalances on Filing Dates)" },
        {
            value: "copy_scaled",
            label: "Copied (Rebalances on Filing Dates, Investments scaled to 100% of the Portfolio)",
        },
    ];

    const sopt = [
        { value: "sharpe_ratio", label: "Sharpe Ratio" },
        { value: "calmar_ratio", label: "Calmar Ratio" },
        { value: "total_return", label: "Total Returns" },
        { value: "max_drawdown", label: "Maximum Drawdown" },
        { value: "annualized_return", label: "Annualized Return" },
    ];

    const sortmetrics_descending = [
        "sharpe_ratio",
        "calmar_ratio",
        "total_return",
        "annualized_return",
        "max_drawdown",
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

    $: sortBy = `${sortMetric}_${metricType}`;

    $: filteredFunds = funds
        ? Object.entries(funds).filter(([cik, fundData]: [string, any]) => {
              const results = fundData.backtest_results;
              if (!results) return false;

              const sharpe = results[`sharpe_ratio_${filterMetricType}`];
              const calmar = results[`calmar_ratio_${filterMetricType}`];
              const drawdown = results[`max_drawdown_${filterMetricType}`];
              const totalReturn = results[`total_return_${filterMetricType}`];
              const annualizedReturn =
                  results[`annualized_return_${filterMetricType}`];
              const months = calculateMonths(fundData.earliest_filing_date);

              if (searchQuery) {
                  const query = searchQuery.toLowerCase();
                  const nameMatch = fundData.name?.toLowerCase().includes(query);
                  const cikMatch = cik.includes(query);
                  if (!nameMatch && !cikMatch) return false;
              }

              // Only apply filters if they have a non-null value
              if (minSharpe !== null && minSharpe !== '' && (sharpe === null || sharpe < minSharpe))
                  return false;
              if (minCalmar !== null && minCalmar !== '' && (calmar === null || calmar < minCalmar))
                  return false;
              if (
                  maxDrawdown !== null &&
                  maxDrawdownPercent !== null && maxDrawdownPercent !== '' &&
                  (drawdown === null || drawdown < maxDrawdown)
              )
                  return false;
              if (
                  minTotalReturn !== null &&
                  minTotalReturnPercent !== null && minTotalReturnPercent !== '' &&
                  (totalReturn === null || totalReturn < minTotalReturn)
              )
                  return false;
              if (
                  minAnnualizedReturn !== null &&
                  minAnnualizedReturnPercent !== null && minAnnualizedReturnPercent !== '' &&
                  (annualizedReturn === null ||
                      annualizedReturn < minAnnualizedReturn))
                  return false;
              if (minMonths !== null && minMonths !== '' && (months === null || months < minMonths))
                  return false;

              return true;
          })
        : [];

    $: sortedFunds = filteredFunds.sort(([, a]: [string, any], [, b]: [string, any]) => {
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

    $: totalPages = Math.ceil(sortedFunds.length / itemsPerPage);
    $: paginatedFunds = sortedFunds.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

    function changePage(newPage: number) {
        if (newPage >= 1 && newPage <= totalPages) {
            const url = new URL($page.url);
            url.searchParams.set('page', String(newPage));
            goto(url);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }
</script>

<svelte:head>
    {#if currentPage > 1}
        <link rel="prev" href="https://denk1k.github.io/hedgesage/?page={currentPage - 1}" />
    {/if}
    {#if currentPage < totalPages}
        <link rel="next" href="https://denk1k.github.io/hedgesage/?page={currentPage + 1}" />
    {/if}
</svelte:head>

<Header funds={sortedFunds} defaultAllocationStrategy={sortBy} />

<main class="container mx-auto p-4">

    <div class="flex flex-wrap items-center mb-4 gap-2">
        <div class="flex items-center gap-2 w-full md:w-auto">
            <h2 class="text-xl font-semibold">Hedge funds sorted by</h2>
            <Select.Root type="single" bind:value={metricType}>
                <Select.Trigger class="w-[150px]">
                    {metricTypeOptions.find((o) => o.value === metricType)?.label}
                </Select.Trigger>
                <Select.Content>
                    {#each longMetricTypeOptions as option}
                        <Select.Item value={option.value}
                            >{option.label}</Select.Item
                        >
                    {/each}
                </Select.Content>
            </Select.Root>
            <Select.Root type="single" bind:value={sortMetric}>
                <Select.Trigger class="w-[150px]">
                    {sopt.find((o) => o.value === sortMetric)?.label}
                </Select.Trigger>
                <Select.Content>
                    {#each sopt as option}
                        <Select.Item value={option.value}
                            >{option.label}</Select.Item
                        >
                    {/each}
                </Select.Content>
            </Select.Root>
        </div>

        <!-- Search section with filter - second row on mobile, inline on desktop -->
        <div class="flex items-center gap-2 w-full md:w-auto md:ml-auto">
            {#if funds}
                {@const totalFundsWithBacktest = Object.values(funds).filter((f: any) => f.backtest_results).length}
                <span class="text-sm text-muted-foreground">
                    Showing {sortedFunds.length} of {totalFundsWithBacktest} funds
                </span>
            {/if}
            <div class="w-[200px]">
                <InputGroup.Root>
                    <InputGroup.Input
                        placeholder="Search..."
                        bind:value={searchQuery}
                    />
                    <InputGroup.Addon>
                        <SearchIcon class="size-4" />
                    </InputGroup.Addon>
                </InputGroup.Root>
            </div>
            <Popover.Root>
                <Popover.Trigger>
                    {#snippet child({ props })}
                        <Button {...props} variant="outline" size="icon">
                            <FilterIcon class="size-4" />
                        </Button>
                    {/snippet}
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
                                <Select.Root
                                    type="single"
                                    bind:value={filterMetricType}
                                >
                                    <Select.Trigger class="col-span-2">
                                        {metricTypeOptions.find(
                                            (o) => o.value === filterMetricType,
                                        )?.label}
                                    </Select.Trigger>
                                    <Select.Content>
                                        {#each metricTypeOptions as option}
                                            <Select.Item value={option.value}
                                                >{option.label}</Select.Item
                                            >
                                        {/each}
                                    </Select.Content>
                                </Select.Root>
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="min-sharpe"
                                    >Min Sharpe</Label.Root
                                >
                                <Input.Root
                                    id="min-sharpe"
                                    type="number"
                                    placeholder="0"
                                    bind:value={minSharpe}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="min-calmar"
                                    >Min Calmar</Label.Root
                                >
                                <Input.Root
                                    id="min-calmar"
                                    type="number"
                                    placeholder="0"
                                    bind:value={minCalmar}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="max-drawdown"
                                    >Max Drawdown (%)</Label.Root
                                >
                                <Input.Root
                                    id="max-drawdown"
                                    type="number"
                                    placeholder="-40"
                                    bind:value={maxDrawdownPercent}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="min-return"
                                    >Min Total Return (%)</Label.Root
                                >
                                <Input.Root
                                    id="min-return"
                                    type="number"
                                    placeholder="None"
                                    bind:value={minTotalReturnPercent}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="min-annualized-return"
                                    >Min Annualized Return (%)</Label.Root
                                >
                                <Input.Root
                                    id="min-annualized-return"
                                    type="number"
                                    placeholder="None"
                                    bind:value={minAnnualizedReturnPercent}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="grid grid-cols-3 items-center gap-4">
                                <Label.Root for="min-months"
                                    >Min Months</Label.Root
                                >
                                <Input.Root
                                    id="min-months"
                                    type="number"
                                    placeholder="120"
                                    bind:value={minMonths}
                                    class="col-span-2"
                                />
                            </div>
                            <div class="pt-2">
                                <Button variant="outline" class="w-full" on:click={clearFilters}>
                                    Clear Filters
                                </Button>
                            </div>
                        </div>
                    </div>
                </Popover.Content>
            </Popover.Root>
        </div>
    </div>

    {#if funds}
        <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {#each paginatedFunds as [cik, fundData] (cik)}
                <FundCard {cik} {fundData} {metricType} meta={data.allocationsMeta?.[cik]} />
            {/each}
        </div>

        <!-- Pagination Controls -->
        {#if totalPages > 1}
            <div class="flex justify-center mt-8">
                <Pagination.Root count={filteredFunds.length} perPage={itemsPerPage} page={currentPage}>
                    {#snippet children({ pages, currentPage })}
                        <Pagination.Content>
                            <Pagination.Item>
                                <Pagination.PrevButton onclick={() => changePage(currentPage - 1)} />
                            </Pagination.Item>
                            {#each pages as page (page.key)}
                                {#if page.type === "ellipsis"}
                                    <Pagination.Item>
                                        <Pagination.Ellipsis />
                                    </Pagination.Item>
                                {:else}
                                    <Pagination.Item>
                                        <Pagination.Link {page} isActive={currentPage === page.value} href="?page={page.value}" onclick={(e) => {
                                            e.preventDefault();
                                            changePage(page.value);
                                        }}>
                                            {page.value}
                                        </Pagination.Link>
                                    </Pagination.Item>
                                {/if}
                            {/each}
                            <Pagination.Item>
                                <Pagination.NextButton onclick={() => changePage(currentPage + 1)} />
                            </Pagination.Item>
                        </Pagination.Content>
                    {/snippet}
                </Pagination.Root>
            </div>
        {/if}
    {:else}
        <p>Loading funds...</p>
    {/if}
</main>
