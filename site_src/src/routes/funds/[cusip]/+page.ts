import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params, fetch }) => {
    const { cusip } = params;

    // Load top funds to get fund name and metadata
    // might want an endpoint for just one fund, but for now follow the pattern
    const [fundsResponse, metaResponse] = await Promise.all([
        fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/top_funds.json'),
        fetch('https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/sec/allocations_meta.json')
    ]);

    if (!fundsResponse.ok) throw new Error('Failed to fetch funds data');
    const funds = await fundsResponse.json();

    // cusip here corresponds to the CIK in the JSON
    const fundData = funds[cusip];

    if (!fundData) {
        throw new Error('Fund not found');
    }

    const allocationsMeta = metaResponse.ok ? await metaResponse.json() : {};
    const meta = allocationsMeta[cusip] || {};

    return {
        cusip,
        fundData,
        funds,
        meta
    };
};
