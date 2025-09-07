<script lang="ts" generics="TData, TValue">
  import {
    type ColumnDef,
    type PaginationState,
    type SortingState,
    type ColumnFiltersState,
    type VisibilityState,
    type RowSelectionState,
    getCoreRowModel,
    getPaginationRowModel,
    getSortedRowModel,
    getFilteredRowModel,
  } from "@tanstack/table-core";
  import { createSvelteTable, FlexRender } from "$lib/components/ui/data-table/index.js";
  import * as Table from "$lib/components/ui/table/index.js";
  import { Button } from "$lib/components/ui/button/index.js";
  import { writable } from "svelte/store";

  export let data: TData[];
  export let columns: ColumnDef<TData, TValue>[];

  const pagination = writable<PaginationState>({ pageIndex: 0, pageSize: 10 });
  const sorting = writable<SortingState>([]);
  const columnFilters = writable<ColumnFiltersState>([]);
  const rowSelection = writable<RowSelectionState>({});

  const table = createSvelteTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onPaginationChange: pagination.set,
    onSortingChange: sorting.set,
    onColumnFiltersChange: columnFilters.set,
    onRowSelectionChange: rowSelection.set,
    state: {
      get pagination() { return $pagination },
      get sorting() { return $sorting },
      get columnFilters() { return $columnFilters },
      get rowSelection() { return $rowSelection },
    },
  });

  export function getTable() {
    return table;
  }
</script>

<div class="rounded-md border">
  <Table.Root>
    <Table.Header>
      {#each table.getHeaderGroups() as headerGroup (headerGroup.id)}
        <Table.Row>
          {#each headerGroup.headers as header (header.id)}
            <Table.Head colspan={header.colSpan} class="[&:has([role=checkbox])]:pl-3">
              {#if !header.isPlaceholder}
                <FlexRender
                  content={header.column.columnDef.header}
                  context={header.getContext()}
                />
              {/if}
            </Table.Head>
          {/each}
        </Table.Row>
      {/each}
    </Table.Header>
    <Table.Body>
      {#each table.getRowModel().rows as row (row.id)}
        <Table.Row data-state={row.getIsSelected() && "selected"}>
          {#each row.getVisibleCells() as cell (cell.id)}
            <Table.Cell class="[&:has([role=checkbox])]:pl-3">
              <FlexRender
                content={cell.column.columnDef.cell}
                context={cell.getContext()}
              />
            </Table.Cell>
          {/each}
        </Table.Row>
      {:else}
        <Table.Row>
          <Table.Cell colspan={columns.length} class="h-24 text-center">
            No results.
          </Table.Cell>
        </Table.Row>
      {/each}
    </Table.Body>
  </Table.Root>
</div>
<div class="flex items-center justify-end space-x-2 pt-4">
  <div class="text-muted-foreground flex-1 text-sm">
    {table.getFilteredSelectedRowModel().rows.length} of
    {table.getFilteredRowModel().rows.length} row(s) selected.
  </div>
  <div class="space-x-2">
    <Button
      variant="outline"
      size="sm"
      on:click={() => table.previousPage()}
      disabled={!table.getCanPreviousPage()}
    >
      Previous
    </Button>
    <Button
      variant="outline"
      size="sm"
      on:click={() => table.nextPage()}
      disabled={!table.getCanNextPage()}
    >
      Next
    </Button>
  </div>
</div>
