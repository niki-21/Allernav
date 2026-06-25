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
- `LANGSMITH_TRACING` (optional; set to `true` to trace the FastAPI/LangGraph backend)
- `LANGSMITH_API_KEY` (optional; LangSmith key, not an OpenAI key)
- `LANGSMITH_PROJECT` (defaults to `allernav` when set)
- `APIFY_TOKEN` (optional; enables expanded Google review retrieval)
- `APIFY_REVIEWS_ACTOR` (defaults to `kaix~google-maps-reviews-scraper`)
- `APIFY_REVIEWS_LIMIT` (defaults to `100`)
- `APIFY_REVIEWS_SORT` (defaults to `newest`)
- `APIFY_LANGUAGE` (defaults to `en`)
- `APIFY_REGION` (defaults to `US`)
- `NEXT_PUBLIC_API_BASE_URL` (set to the FastAPI service URL when deployed)
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

Google is required for search and maps. Gemini is optional; the app falls back to cautious heuristic recommendations when it is missing. Apify is optional; when it is missing, AllerNav uses the limited review snippets returned by Google Places.

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
GET  /api/places/{id}/reviews
POST /api/places/{id}/reviews-refresh
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

Create or update the Azure AI Search index from the checked-in schema:

```bash
cd apps/api
PYTHONPATH=. python3 scripts/setup_azure_search_index.py
```

The index schema lives at `apps/api/azure_search_index.json`. It is configured for 1536-dimensional embeddings, matching `text-embedding-3-small`.

The deterministic allergen engine remains the safety authority. Hybrid/vector retrieval can surface evidence, but it does not decide that a dish is lower risk.

Live Azure smoke tests are opt-in so normal unit tests never call paid cloud APIs:

```bash
ALLERNAV_LIVE_CLOUD_TESTS=true PYTHONPATH=apps/api python3 -m pytest apps/api/tests/test_live_azure_smoke.py
```

## LangSmith Tracing

LangSmith is the observability layer for LangChain/LangGraph applications. In AllerNav, it traces the FastAPI agent backend in `apps/api/allernav_api/agent_graph.py`.

You do not need an OpenAI API key for the current backend trace. The current LangGraph path uses deterministic retrieval, ingestion, scoring, evidence selection, and safety gating. You only need `OPENAI_API_KEY` later if you add an OpenAI model call to a traced step.

Set these in `apps/api/.env` for local FastAPI and in the deployed API environment if FastAPI is deployed separately:

```bash
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=allernav
LANGCHAIN_CALLBACKS_BACKGROUND=false
```

When enabled, LangSmith will show:

- the top-level `AllerNav Dining Safety Graph` run
- the compiled `AllerNav LangGraph` run
- LangGraph node timing and ordering
- metadata such as restaurant ID, restaurant name, selected allergens, and menu source count
- whether the trace ended in verification, avoidance, staff questions, or insufficient evidence

Do not put secrets, private user profiles, or raw sensitive health details into trace metadata. Allergy selections are currently included because this is a demo decision-support project; remove that metadata before handling real user accounts.

Expanded Google review retrieval is optional through Apify. Set these in `apps/api/.env` for FastAPI and in the Vercel web project environment if the Next.js API route is serving place details directly:

```bash
APIFY_TOKEN=
APIFY_API_BASE_URL=https://api.apify.com/v2
APIFY_REVIEWS_ACTOR=kaix~google-maps-reviews-scraper
APIFY_REVIEWS_LIMIT=100
APIFY_REVIEWS_SORT=newest
APIFY_LANGUAGE=en
APIFY_REGION=US
APIFY_REVIEWS_SEARCH_QUERY=
APIFY_REVIEWS_NEWER_THAN=
APIFY_REVIEWS_OLDER_THAN=
APIFY_TIMEOUT_SECONDS=8
APIFY_REVIEWS_CACHE_TTL_HOURS=168
ALLERNAV_REVIEWS_DB=./.data/apify_reviews.sqlite
```

Apify reviews are treated as supplemental warning evidence. They can increase caution when allergy, cross-contact, staff knowledge, or reaction language appears, but they do not prove a dish is lower risk. Place details do not call Apify directly; expanded reviews are loaded through the explicit `/reviews-refresh` route so Vercel place-detail functions stay fast. Leave `APIFY_REVIEWS_SEARCH_QUERY` blank for the app default; AllerNav fetches a bounded review set and then locally ranks allergy-relevant language so it does not miss synonyms like celiac, cross-contact, dedicated fryer, peanut, sesame, or dairy.

Backend checks:

```bash
cd /Users/nikitamiller/Desktop/allernav
PYTHONPATH=apps/api python3 -m pytest apps/api/tests
```
