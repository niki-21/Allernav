# AllerNav

AllerNav is an Agentic AI Dining Safety Assistant. The v2 frontend is a map-first Next.js app, with a FastAPI service available for dining/search/menu/agent APIs.

That means:

- one repo
- one Vercel project
- one public link

The app handles both the UI and the API from `apps/web`.

## Local setup

1. Install web dependencies:

```bash
cd apps/web
npm install
```

2. Create `apps/web/.env.local` from `apps/web/.env.example`.

3. Use separate Google keys:

```bash
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_browser_maps_key
GOOGLE_PLACES_API_KEY=your_server_places_key
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.5-flash
```

The browser key must allow the Maps JavaScript API and the site referrer. The server key must allow Places API and must not be restricted by browser referrer.

4. Start the app from the repo root:

```bash
cd /Users/nikitamiller/Desktop/allernav
npm run dev
```

Then open:

```bash
http://localhost:3000
```

## Deploy With One Link

Use a single Vercel project connected to this GitHub repo.

Preferred Vercel settings:

- Root Directory: `apps/web`
- Framework Preset: `Next.js`
- Install Command: `npm install`
- Build Command: `npm run build`

The root package is configured with npm workspaces for local commands, but the Vercel project should still use `apps/web` as its Root Directory so Vercel detects and serves the Next.js app.

Vercel environment variables:

- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `GEMINI_API_KEY` (optional; enables Gemini-written menu recommendations)
- `GEMINI_MODEL` (defaults to `gemini-3.5-flash`)
- `NEXT_PUBLIC_API_BASE_URL` (set to the FastAPI service URL when deployed)
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Google is required for search and maps. Gemini is optional; the app falls back to cautious heuristic recommendations when it is missing.

After deploy, check:

```bash
https://your-project.vercel.app/api/health
```

`ok: true` means the required Google server and browser keys are configured.

After deploy, Vercel gives you one URL such as:

```bash
https://your-project.vercel.app
```

That is the only link you need to share.

## Upload To GitHub

If this folder is not already connected to your GitHub repo, run these commands from the project root:

```bash
git add .
git commit -m "Simplify Allernav to one-link deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If `origin` already exists, replace the `git remote add origin ...` line with:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

## Useful Commands

From the repo root:

```bash
npm run dev
npm run test
npm run build
```
