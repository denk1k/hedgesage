import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			pages: '../site',
			assets: '../site',
			fallback: 'index.html',
			precompress: false,
			strict: true
		})
	},
	preprocess: vitePreprocess()
};

export default config;