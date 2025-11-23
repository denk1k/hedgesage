<script lang="ts">
 import { cn } from "$lib/utils.js";
 import GithubIcon from "@lucide/svelte/icons/github";
 import { Button } from "$lib/components/ui/button/index.js";
 import CreatePortfolioDrawer from "$lib/components/CreatePortfolioDrawer.svelte";

 export let funds: any;
 export let defaultAllocationStrategy: string;
</script>

<header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur-sm supports-[backdrop-filter]:bg-background/60">
    <div class="container mx-auto flex h-20 items-center justify-between p-4">
        <div class="flex items-center gap-6">
            <a href="/" class="flex items-center space-x-2">
                <img
                    src="https://denk1k.github.io/hedgesage/logo-transparent-cropped.png"
                    alt="HedgeSage Logo"
                    class="h-12 w-32"
                />
            </a>
            
            <div class="hidden md:block h-8 w-px bg-border"></div>

            <p class="hidden md:block text-sm text-muted-foreground max-w-md leading-tight">
                Hedge fund backtesting and portfolio creation via live positions based on past performance and risk analysis.
            </p>
        </div>

        <div class="flex items-center gap-2">
            <CreatePortfolioDrawer
                {funds}
                {defaultAllocationStrategy}
            />
            <Button
                href="https://github.com/denk1k/hedgesage"
                variant="ghost"
                size="icon"
            >
                <GithubIcon class="size-5" />
            </Button>
        </div>
    </div>
</header>

<div class="md:hidden border-b bg-background">
    <div class="container mx-auto p-4 text-sm text-muted-foreground">
        Hedge fund backtesting and portfolio creation via live positions based on past performance and risk analysis.
    </div>
</div>
