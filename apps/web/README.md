# Allernav Web

## Local development

Run the web app from this folder:

```bash
npm run dev
```

The app expects:

- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`
- `NEXT_PUBLIC_API_BASE_URL`

See [`.env.example`](/Users/nikitamiller/Desktop/allernav/apps/web/.env.example).

## Deploying the web app to Vercel

Use `apps/web` as the Vercel project root directory.

Set these environment variables in Vercel:

- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`
- `NEXT_PUBLIC_API_BASE_URL`

Important:

- The frontend can deploy to Vercel by itself.
- The app will not fully work unless `NEXT_PUBLIC_API_BASE_URL` points to a publicly reachable backend.
- The backend is currently a separate FastAPI app and should be hosted somewhere like Render or Railway.

Recommended Vercel settings:

- Framework Preset: `Next.js`
- Root Directory: `apps/web`
- Install Command: `npm install`
- Build Command: `npm run build`
