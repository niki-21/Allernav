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

## Agentic FastAPI Backend

The FastAPI service now includes a first-pass LangGraph dining-safety workflow with deterministic allergen risk scoring.

Run the backend locally:

```bash
cd apps/api
python3 -m pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app:app --reload --port 8000
```

Useful endpoints:

```text
POST /analyze-restaurant
POST /analyze-menu
POST /recommend-dishes
POST /chat
POST /feedback
GET  /restaurants/{id}/evidence
GET  /api/places/{id}/menu
POST /api/places/{id}/menu-refresh
POST /api/restaurants/{id}/search-index
POST /api/search/hybrid
```

Menu ingestion stores extracted HTML/JSON-LD menu records in SQLite. PDF and image menu links are detected as document sources and can be extracted with Azure Document Intelligence when these variables are set:

```bash
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=
AZURE_DOCUMENT_INTELLIGENCE_KEY=
```

By default the SQLite database is created at:

```text
apps/api/.data/menu_ingestion.sqlite
```

That `.data` directory is local-only and ignored by git. Override it when needed:

```bash
ALLERNAV_MENU_DB=/tmp/allernav-menu.sqlite
```

Refresh a menu from an official restaurant site:

```bash
curl -X POST "http://localhost:8000/api/places/demo/menu-refresh?restaurant_name=Demo&website_url=https://example.com"
```

The same endpoints are also available under `/api/...` so the existing frontend API prefix can target this service with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

For the Next.js route bridge, set this server-side value in `apps/web/.env.local`:

```bash
FASTAPI_API_BASE_URL=http://localhost:8000
```

Azure AI Search indexing and hybrid retrieval are optional until Phase 3 infrastructure is provisioned:

```bash
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=
AZURE_SEARCH_INDEX_NAME=allernav-menu-evidence
```

The deterministic allergen engine remains the safety authority. Hybrid/vector retrieval can surface evidence, but it does not decide that a dish is lower risk.

Backend checks:

```bash
cd /Users/nikitamiller/Desktop/allernav
PYTHONPATH=apps/api python3 -m pytest apps/api/tests
```
