import type { PageLoad } from './$types';

export const prerender = true;

export const load: PageLoad = async ({ fetch }) => {
    const [fundsResponse, metaResponse] = await Promise.all([
        fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/top_funds.json'),
        fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations_meta.json')
    ]);

    if (!fundsResponse.ok) {
        throw new Error('Failed to fetch funds data');
    }

    const funds = await fundsResponse.json();
    const allocationsMeta = metaResponse.ok ? await metaResponse.json() : {};

    return {
        funds,
        allocationsMeta
    };
};
