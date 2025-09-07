<script lang="ts">
    import * as Drawer from "$lib/components/ui/drawer/index.js";
    import { Button } from "$lib/components/ui/button/index.js";
    import * as Select from "$lib/components/ui/select/index.js";
    import { type ColumnDef, type RowSelectionState } from "@tanstack/table-core";
    import { renderComponent } from "$lib/components/ui/data-table/index.js";
    import { Checkbox } from "$lib/components/ui/checkbox/index.js";
    import DataTable from "./custom_data_table.svelte";
    import { writable } from "svelte/store";

    export let open: boolean;
    export let funds: [string, any][];
    export let metricType: string;

    type Fund = {
        cik: string;
        name: string;
        backtest_results: any;
        earliest_filing_date: string;
        id: string;
    };

    $: tableData: Fund[] = funds.map(([cik, fundData]) => ({
        cik,
        ...fundData,
        id: cik,
    }));

    const columns: ColumnDef<Fund>[] = [
        {
            id: "select",
            header: ({ table }) =>
                renderComponent(Checkbox, {
                    checked: table.getIsAllPageRowsSelected(),
                    indeterminate: table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected(),
                    onCheckedChange: (value: boolean) => table.toggleAllPageRowsSelected(!!value),
                    "aria-label": "Select all",
                }),
            cell: ({ row }) =>
                renderComponent(Checkbox, {
                    checked: row.getIsSelected(),
                    onCheckedChange: (value: boolean) => row.toggleSelected(!!value),
                    "aria-label": "Select row",
                }),
            enableSorting: false,
            enableHiding: false,
        },
        {
            accessorKey: "name",
            header: "Fund Name",
        },
        {
            accessorFn: (row) => row.backtest_results?.[`sharpe_ratio_${metricType}`],
            id: `sharpe_ratio_${metricType}`,
            header: "Sharpe Ratio",
            cell: (info) => (info.getValue() as number)?.toFixed(2) ?? 'N/A'
        },
        {
            accessorFn: (row) => row.backtest_results?.[`calmar_ratio_${metricType}`],
            id: `calmar_ratio_${metricType}`,
            header: "Calmar Ratio",
            cell: (info) => (info.getValue() as number)?.toFixed(2) ?? 'N/A'
        },
        {
            accessorFn: (row) => row.backtest_results?.[`total_return_${metricType}`],
            id: `total_return_${metricType}`,
            header: "Total Return",
            cell: (info) => {
                const value = info.getValue() as number;
                return value !== null && value !== undefined ? `${(value * 100).toFixed(2)}%` : 'N/A';
            }
        },
    ];

    const rowSelection = writable<RowSelectionState>({});

    let allocationStrategy = 'even';

    async function generateCsv() {
        const selectedIds = Object.keys($rowSelection);
        if (selectedIds.length === 0) {
            alert("Please select at least one fund.");
            return;
        }

        const selectedFunds = tableData.filter(fund => selectedIds.includes(fund.id));
        
        const validSelectedFunds = selectedFunds.filter(fund => {
            if (allocationStrategy === 'even') return true;
            const metricValue = fund.backtest_results?.[allocationStrategy];
            return metricValue !== null && metricValue !== undefined && metricValue > 0;
        });

        if (validSelectedFunds.length === 0) {
            alert("No funds with positive metric values selected for the chosen strategy.");
            return;
        }

        const totalMetricValue = validSelectedFunds.reduce((sum, fund) => {
            if (allocationStrategy === 'even') {
                return sum + 1;
            }
            const metricValue = fund.backtest_results?.[allocationStrategy] || 0;
            return sum + (metricValue || 0);
        }, 0);

        const fundWeights: Record<string, number> = {};
        for (const fund of validSelectedFunds) {
            if (allocationStrategy === 'even') {
                fundWeights[fund.cik] = 1 / validSelectedFunds.length;
            } else {
                const metricValue = fund.backtest_results?.[allocationStrategy] || 0;
                fundWeights[fund.cik] = metricValue / totalMetricValue;
            }
        }

        const portfolioAllocations: Record<string, number> = {};

        for (const fund of validSelectedFunds) {
            try {
                const response = await fetch(`https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations/${fund.cik}.csv`);
                if (!response.ok) {
                    console.error(`Failed to fetch allocations for CIK ${fund.cik}`);
                    continue;
                }
                const csvText = await response.text();
                const rows = csvText.split('\n').slice(1);
                const header = csvText.split('\n')[0].split(',');
                const tickerIndex = header.indexOf('ticker');
                const allocationIndex = header.indexOf('allocation_percent');

                for (const row of rows) {
                    const values = row.split(',');
                    if (values.length > Math.max(tickerIndex, allocationIndex)) {
                        const ticker = values[tickerIndex];
                        const allocationPercent = parseFloat(values[allocationIndex]);
                        if (ticker && !isNaN(allocationPercent)) {
                            const fundWeight = fundWeights[fund.cik];
                            const weightedAllocation = allocationPercent * fundWeight;
                            portfolioAllocations[ticker] = (portfolioAllocations[ticker] || 0) + weightedAllocation;
                        }
                    }
                }
            } catch (e) {
                console.error(`Error processing allocations for CIK ${fund.cik}`, e);
            }
        }

        let csvContent = "data:text/csv;charset=utf-8,Ticker,Allocation\n";
        for (const [ticker, allocation] of Object.entries(portfolioAllocations)) {
            csvContent += `${ticker},${allocation.toFixed(5)}\n`;
        }

        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", "portfolio_allocation.csv");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
</script>

<Drawer.Root {open} bind:open>
    <Drawer.Content>
        <Drawer.Header>
            <Drawer.Title>Create a Portfolio</Drawer.Title>
        </Drawer.Header>
        <div class="h-[90vh] overflow-auto px-4">
            {#if tableData}
                <DataTable data={tableData} columns={columns} bind:rowSelection={rowSelection} />
            {/if}
            <div class="flex items-center gap-4 mt-4">
                <Button on:click={generateCsv}>Generate allocation CSV</Button>
                <Select.Root onValueChange={(v) => allocationStrategy = v || 'even'}>
                    <Select.Trigger class="w-[380px]">
                        <Select.Value placeholder="Select allocation strategy" />
                    </Select.Trigger>
                    <Select.Content>
                        <Select.Item value="even">Allocate evenly</Select.Item>
                        <Select.Separator />
                        <Select.Label>Allocate based on Original performance</Select.Label>
                        <Select.Item value="sharpe_ratio_fund">Sharpe Ratio (Original)</Select.Item>
                        <Select.Item value="calmar_ratio_fund">Calmar Ratio (Original)</Select.Item>
                        <Select.Item value="total_return_fund">Total Return (Original)</Select.Item>
                        <Select.Separator />
                        <Select.Label>Allocate based on Copied performance</Select.Label>
                        <Select.Item value="sharpe_ratio_copy">Sharpe Ratio (Copied)</Select.Item>
                        <Select.Item value="calmar_ratio_copy">Calmar Ratio (Copied)</Select.Item>
                        <Select.Item value="total_return_copy">Total Return (Copied)</Select.Item>
                        <Select.Separator />
                        <Select.Label>Allocate based on Copied (Scaled) performance</Select.Label>
                        <Select.Item value="sharpe_ratio_copy_scaled">Sharpe Ratio (Copied, Scaled)</Select.Item>
                        <Select.Item value="calmar_ratio_copy_scaled">Calmar Ratio (Copied, Scaled)</Select.Item>
                        <Select.Item value="total_return_copy_scaled">Total Return (Copied, Scaled)</Select.Item>
                    </Select.Content>
                </Select.Root>
            </div>
        </div>
    </Drawer.Content>
</Drawer.Root>
