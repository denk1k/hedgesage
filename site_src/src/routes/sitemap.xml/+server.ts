import type { RequestHandler } from './$types';
import { readFileSync } from 'fs';
import { join } from 'path';

const ITEMS_PER_PAGE = 24;
const BASE_URL = 'https://denk1k.github.io/hedgesage';
const DATA_URL = 'https://raw.githubusercontent.com/denk1k/hedgesage/refs/heads/main/top_funds.json';

async function getFundsData(): Promise<any[]> {
    try {
        try {
            const fundsPath = join(process.cwd(), '../top_funds.json');
            const data = readFileSync(fundsPath, 'utf-8');
            console.log(`Successfully read funds data from ${fundsPath}`);
            return JSON.parse(data);
        } catch (fsError) {
            console.log('Local file read failed:', (fsError as Error).message);
        }

        console.log('Attempting to fetch from URL:', DATA_URL);
        const response = await fetch(DATA_URL);
        if (!response.ok) {
            console.error('Failed to fetch funds data:', response.status, response.statusText);
            throw new Error('Failed to fetch funds data');
        }
        return await response.json();
    } catch (error) {
        console.error('Error getting funds data:', error);
        throw error;
    }
}

export const GET: RequestHandler = async () => {
    try {
        const fundsData = await getFundsData();
        const fundsWithBacktest = Object.values(fundsData).filter((fund: any) => fund.backtest_results);
        const fundsCount = fundsWithBacktest.length;
        const totalPages = Math.ceil(fundsCount / ITEMS_PER_PAGE);

        console.log(`Sitemap: Found ${fundsCount} funds with backtest results (out of ${Object.keys(fundsData).length} total), generating ${totalPages} pages`);

        const urls = [];

        // Add the first page without filters (default view)
        urls.push(`<url>
        <loc>${BASE_URL}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>`);

        // first page with filters=clear to show all funds
        urls.push(`<url>
        <loc>${BASE_URL}/?filters=clear</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>`);

        // paginated pages with filters=clear
        for (let page = 2; page <= totalPages; page++) {
            urls.push(`<url>
        <loc>${BASE_URL}/?page=${page}&amp;filters=clear</loc>
        <changefreq>weekly</changefreq>
        <priority>0.8</priority>
    </url>`);
        }

        const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join('')}
</urlset>`.trim();

        console.log(`Sitemap: Generated ${urls.length} URLs`);

        return new Response(sitemap, {
            headers: {
                'Content-Type': 'application/xml',
                'Cache-Control': 'max-age=0, s-maxage=3600'
            }
        });
    } catch (error) {
        console.error('Error generating sitemap:', error);
        // minimal sitemap with just the base URL
        const fallbackSitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>${BASE_URL}/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>`;
        return new Response(fallbackSitemap, {
            headers: {
                'Content-Type': 'application/xml'
            }
        });
    }
};

export const prerender = true;
