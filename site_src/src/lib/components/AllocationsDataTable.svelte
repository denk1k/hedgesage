<script lang="ts">
  import {
    createSvelteTable,
    FlexRender,
  } from "$lib/components/ui/data-table/index.js";
  import {
    type ColumnDef,
    type ColumnFiltersState,
    type PaginationState,
    type RowSelectionState,
    type SortingState,
    type VisibilityState,
    getCoreRowModel,
    getFilteredRowModel,
    getPaginationRowModel,
    getSortedRowModel
  } from "@tanstack/table-core";
  import * as Table from "$lib/components/ui/table/index.js";
  import { Button } from "$lib/components/ui/button/index.js";

  export let data: any[];

  type Allocation = {
    ticker: string;
    nameOfIssuer: string;
    value: string;
    shares: string;
    allocation_percent: string;
  };

  const columns: ColumnDef<Allocation>[] = [
    {
      accessorKey: "ticker",
      header: "Ticker",
    },
    {
      accessorKey: "nameOfIssuer",
      header: "Company Name",
    },
    {
      accessorKey: "value",
      header: "Value",
      cell: ({ row }) => {
        const amount = parseFloat(row.getValue("value"));
        const formatted = new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
        }).format(amount);
        return formatted;
      },
    },
    {
      accessorKey: "shares",
      header: "Shares",
    },
    {
      accessorKey: "allocation_percent",
      header: "Allocation %",
      cell: ({ row }) => {
        const value = parseFloat(row.getValue("allocation_percent"));
        return `${value.toFixed(5)}%`;
      }
    },
  ];

  const table = createSvelteTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
</script>

<div class="rounded-md border">
  <Table.Root>
    <Table.Header>
      {#each table.getHeaderGroups() as headerGroup}
        <Table.Row>
          {#each headerGroup.headers as header}
            <Table.Head>
              {#if header.isPlaceholder}
                &nbsp;
              {:else}
                <Button variant="ghost" on:click={header.column.getToggleSortingHandler()}>
                  <FlexRender
                    content={header.column.columnDef.header}
                    context={header.getContext()}
                  />
                  {{
                    asc: ' 🔼',
                    desc: ' 🔽',
                  }[header.column.getIsSorted() as string] ?? ''}
                </Button>
              {/if}
            </Table.Head>
          {/each}
        </Table.Row>
      {/each}
    </Table.Header>
    <Table.Body>
      {#each table.getRowModel().rows as row}
        <Table.Row>
          {#each row.getVisibleCells() as cell}
            <Table.Cell>
              <FlexRender
                  content={cell.column.columnDef.cell}
                  context={cell.getContext()}
                />
            </Table.Cell>
          {/each}
        </Table.Row>
      {/each}
    </Table.Body>
  </Table.Root>
</div>
