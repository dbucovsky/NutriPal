# Architecture

## Stack

- **Backend:** PHP, exposing a JSON API. Locally this runs via PHP's built-in dev server (`php -S localhost:8080 -t public`, started with `start-services.ps1`/`start-services.bat`), not Apache — XAMPP is used only for MySQL locally. Apache/cPanel is the target in production (Bluehost).
- **Database:** MySQL (via XAMPP locally; Bluehost-managed MySQL in production).
- **Frontend:** React SPA, calling the PHP JSON API.
- **Auth:** Real login (not "whoever's on localhost is me") is designed in from the start, since remote deployment is a planned next step even though not day one.
- **Secrets:** Environment-based, not committed — see `doc/credentials/` for local-only reference notes.

## Why this stack

NutriPal is intended to eventually run on a Bluehost shared hosting plan, which is PHP/MySQL/Apache-native via cPanel. Bluehost's Python/Node support (where available) runs through cPanel's Passenger integration in WSGI mode and doesn't support always-on background processes — a poor fit for FastAPI (ASGI) and for any continuous sync/analysis process. PHP + MySQL avoids all of that friction and matches the local XAMPP dev environment exactly, so there's no dev/prod parity gap.

The app's analysis needs (macro/micronutrient math, activity/weight correlation) are arithmetic over a single user's modest dataset — not heavy enough to need Python's data-science ecosystem (pandas etc.), so giving that up costs little.

React was chosen over server-rendered PHP views specifically because fast meal logging (near-identical daily meals with small tweaks) is a first-class feature, not an afterthought — that UX benefits from a proper SPA rather than full-page form submissions.

## Frontend (dev setup, done 2026-09-08)

The React app lives in `frontend/` (scaffolded with Vite, plain JavaScript — no TypeScript yet). It runs as its own dev server, separate from the PHP one:

```
cd frontend
npm install   # first time only
npm run dev   # http://localhost:5173
```

`frontend/vite.config.js` proxies any `/api/*` request to `http://localhost:8080` (the PHP dev server), so the app can just `fetch('/api/...')` with no CORS handling needed in dev. The PHP side of the API lives under `public/api/` — one file per endpoint (`login.php`, `food-log.php`), matching this project's existing one-file-per-concern style rather than a router/framework. Not wired into `start-services.ps1` yet (that script is XAMPP/PHP-specific per its own header) — start the frontend dev server separately for now.

There's a placeholder login (`public/api/login.php`, `frontend/src/components/Login.jsx`) with no password/session/security of any kind — it just looks up a real user by email and the frontend remembers the result in `localStorage`. It exists purely to give the frontend a real "current user" concept and exercise a POST round-trip; real authentication is still future work (see "Auth" above).

## Deployment target (future)

Bluehost shared hosting. Not deployed yet — currently developed and run locally via XAMPP.

## Data source

Google Health API (successor to the deprecated Google Fit REST API), which itself covers what used to come from Fitbit directly. See `doc/credentials/` (local-only, gitignored) for OAuth credential reference notes.
