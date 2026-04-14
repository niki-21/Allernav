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
- The backend can also be deployed to Vercel as a second project rooted at `apps/api`.

Recommended Vercel settings:

- Framework Preset: `Next.js`
- Root Directory: `apps/web`
- Install Command: `npm install`
- Build Command: `npm run build`

## Deploying the API to Vercel

Use a second Vercel project from the same GitHub repo with:

- Root Directory: `apps/api`
- Framework Preset: `Other`

Add these environment variables:

- `GOOGLE_MAPS_API_KEY`
- `FRONTEND_ORIGIN`

Set `FRONTEND_ORIGIN` to your deployed web URL, for example:

```bash
https://allernav.vercel.app
```
