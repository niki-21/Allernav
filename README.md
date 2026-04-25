# Allernav

Allernav now runs as one Next.js app and deploys as one Vercel project.

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

3. Put the same Google key in both variables:

```bash
GOOGLE_MAPS_API_KEY=your_google_maps_key
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_key
```

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

Vercel settings:

- Root Directory: `apps/web`
- Framework Preset: `Next.js`
- Install Command: `npm install`
- Build Command: `npm run build`

Vercel environment variables:

- `GOOGLE_MAPS_API_KEY`
- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`

Use the same key for both values.

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
