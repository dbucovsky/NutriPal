# Architecture

## Stack

- **Backend:** PHP, exposing a JSON API. Runs on XAMPP (Apache) locally.
- **Database:** MySQL (via XAMPP locally; Bluehost-managed MySQL in production).
- **Frontend:** React SPA, calling the PHP JSON API.
- **Auth:** Real login (not "whoever's on localhost is me") is designed in from the start, since remote deployment is a planned next step even though not day one.
- **Secrets:** Environment-based, not committed — see `doc/credentials/` for local-only reference notes.

## Why this stack

NutriPal is intended to eventually run on a Bluehost shared hosting plan, which is PHP/MySQL/Apache-native via cPanel. Bluehost's Python/Node support (where available) runs through cPanel's Passenger integration in WSGI mode and doesn't support always-on background processes — a poor fit for FastAPI (ASGI) and for any continuous sync/analysis process. PHP + MySQL avoids all of that friction and matches the local XAMPP dev environment exactly, so there's no dev/prod parity gap.

The app's analysis needs (macro/micronutrient math, activity/weight correlation) are arithmetic over a single user's modest dataset — not heavy enough to need Python's data-science ecosystem (pandas etc.), so giving that up costs little.

React was chosen over server-rendered PHP views specifically because fast meal logging (near-identical daily meals with small tweaks) is a first-class feature, not an afterthought — that UX benefits from a proper SPA rather than full-page form submissions.

## Deployment target (future)

Bluehost shared hosting. Not deployed yet — currently developed and run locally via XAMPP.

## Data source

Google Health API (successor to the deprecated Google Fit REST API), which itself covers what used to come from Fitbit directly. See `doc/credentials/` (local-only, gitignored) for OAuth credential reference notes.
