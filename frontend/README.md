## WhatsBase Frontend

Next.js frontend for onboarding and testing a WhatsApp sales agent.

This app is intentionally runnable without the backend API by using `NEXT_PUBLIC_USE_MOCK_API=true`.

## Getting Started

1) Copy env template:

```bash
cp .env.example .env.local
```

2) Fill `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

3) Start the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## App Routes

- `/` landing page
- `/login` and `/signup` for Supabase auth
- `/onboarding/business`
- `/onboarding/products`
- `/onboarding/whatsapp`
- `/onboarding/build`
- `/test-chat`

## Mock API mode

When `NEXT_PUBLIC_USE_MOCK_API=true`, onboarding, build flow, and test chat use browser-local mock handlers (`lib/mock/*`) with persisted state in localStorage.

## Deploy to Vercel (WhatsBase)

1) Create a Vercel project named `WhatsBase`
2) Import this repo and set **Root Directory** to `frontend`
3) Add env vars:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_USE_MOCK_API=true`
4) Deploy

Expected default URL: `https://whatsbase.vercel.app` (depending on availability).

## Backend wiring later

Set:
- `NEXT_PUBLIC_USE_MOCK_API=false`
- `NEXT_PUBLIC_API_URL=<your-api-url>`

Then implement `realApi` in `lib/api.ts`.

## Figma integration (local tooling)

This repo now includes a local script for pulling Figma file JSON and exporting image assets.

1) Add these values in `.env.local`:
- `FIGMA_ACCESS_TOKEN=<your-personal-access-token>`
- `FIGMA_FILE_KEY=<optional default file key>`

2) Verify token access:

```bash
npm run figma:check
```

3) Pull a Figma file JSON (full file or specific nodes):

```bash
# using default FIGMA_FILE_KEY
npm run figma:file

# explicit key + nodes
npm run figma:file -- --file <FILE_KEY> --nodes "12:34,56:78" --depth 3
```

4) Export frame/component images:

```bash
npm run figma:images -- --file <FILE_KEY> --nodes "12:34,56:78" --format png --scale 2
```

Output is written to:
- `figma-output/file-<FILE_KEY>.json`
- `figma-output/assets/*` (+ `manifest.json`)

Do not expose `FIGMA_ACCESS_TOKEN` to browser code or Vercel public env vars. Keep it local only.
