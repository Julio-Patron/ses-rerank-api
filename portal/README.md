# SES Enterprise Portal

Next.js 16 administration portal for the FastAPI Gateway in `../gateway`.
The portal is a browser client: it does not embed an API key at build time.
The configured Gateway URL and administrator key are stored in the current
browser's `localStorage` under `ses_api_url` and `ses_api_key`.

## Local validation

From the repository root:

```powershell
npm ci --prefix portal
npm --prefix portal run lint
npm --prefix portal run build
npm --prefix portal run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000/settings`, enter the Gateway URL and a rotated
administrator key, then use **Test Connection**. That check calls both the
public health endpoint and the administrator analytics endpoint, so it
validates connectivity and privileges.

The default Gateway URL is `http://localhost:8000`. A non-secret alternative
can be embedded at build time with `NEXT_PUBLIC_SES_API_URL`; never place an API
key in a `NEXT_PUBLIC_` variable.

## Implemented routes

- `/dashboard`: persisted analytics and service health.
- `/search`: semantic search, answer generation, actual Rust-path status, and
  evidence PDF export.
- `/documents`: file ingestion, document listing, and deletion.
- `/keys`: administrator key creation, one-time display, and revocation.
- `/analytics`: persisted request aggregates and recent-log timeline.
- `/reports`: usage and health PDF downloads.
- `/settings`: browser-local Gateway configuration.

## Operational boundary

`npm run build` proves the frontend compiles and prerenders. Full feature
validation also requires the Gateway plus its configured Qdrant, Redis, and
Ollama dependencies. A degraded or unavailable backend is surfaced by the
individual pages; it is not replaced with sample data.
