// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	integrations: [
		starlight({
			title: 'Dark Factory Docs',
			sidebar: [
				{
					label: 'Guides',
					items: [
						// Each item here is one entry in the navigation menu.
						{ label: 'Introduction', slug: 'guides/example' },
					],
				},
				{
					label: 'Reference',
					items: [{ autogenerate: { directory: 'reference' } }],
				},
				{
					// One entry per feature directory (specs/NNN-<slug>/), each holding
					// that feature's spec.md, plan.md, tasks.md and design artifacts.
					// Synced from repo-root specs/ by _shared/spec-helpers/docs-sync.sh.
					label: 'Features',
					items: [{ autogenerate: { directory: 'features' } }],
				},
			],
		}),
	],
});
