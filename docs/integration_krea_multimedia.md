# Krea multimedia provider notes

Reviewed 2026-07-07 from Krea's public docs:

- Docs entry point: `https://www.krea.ai/docs`
- SDK/setup: `https://www.krea.ai/docs/getting-started/installation-and-setup`
- API keys/billing: `https://www.krea.ai/docs/getting-started/api-keys-and-billing`
- Feature API overview: `https://www.krea.ai/docs/features-api/introduction`
- Assets: `https://www.krea.ai/docs/features-api/assets`
- Jobs: `https://www.krea.ai/docs/features-api/jobs`
- Image generation: `https://www.krea.ai/docs/features-api/image-generation`
- Video generation: `https://www.krea.ai/docs/features-api/video-generation`
- Webhooks: `https://www.krea.ai/docs/features-api/webhooks`
- Pricing examples: `https://www.krea.ai/docs/features-api/pricing`

Implementation posture for SPR-03:

- Secret shape: `KREA_API_KEY`; do not print or commit values.
- Auth shape: bearer token.
- Execution shape: asynchronous jobs; dry-run must be free and CI-safe.
- Asset upload: documented 75 MB limit.
- Supported families: assets, jobs, webhooks, image generation, video generation, upscale.
- Antiek route policy: `cheapest` stays local placeholder/dry-run, `balanced` uses Krea standard settings, and `highest_quality` uses Krea premium settings.

Live smoke is intentionally deferred until the operator explicitly approves paid provider execution with a configured key.
