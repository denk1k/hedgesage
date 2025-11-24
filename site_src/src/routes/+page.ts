import type { PageLoad } from './$types';

export const prerender = true;

export const load: PageLoad = async ({ fetch }) => {
    const response = await fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/top_funds.json');
    if (!response.ok) {
        throw new Error('Failed to fetch funds data');
    }
    const funds = await response.json();
    return {
        funds
    };
};
