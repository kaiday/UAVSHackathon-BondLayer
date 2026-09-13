# BondLayer Web

Next.js dashboard for the BondLayer merchant console.

## Start locally

```bash
npm install
npm run dev
```

The console uses `/console/` as its base path. Its `/onboard/*` API calls are
same-origin, so the complete flow is served by the merchant Python server:

```bash
npm run build
```

Then start `run.ps1` / `run.sh` from the repository root and open
[http://127.0.0.1:8000/console/](http://127.0.0.1:8000/console/).
The committed `out/` export is served without Node at runtime.

## Routes

- Main dashboard: `/console/` — redirects to onboarding when no merchants exist.
- Merchant onboarding: `/console/onboarding/` — business details, actual CSV
  validation, then atomic publication. The preview does not create a merchant.
- Catalogue: `/console/catalogue/` — use the merchant selector and Replace catalogue.

Existing uploaded catalogues are retained. `BONDLAYER_UPLOADS_DIR` selects an
independent storage directory when testing an empty installation. No mock
merchant profiles, catalogue rows or evaluation reports load by default.
