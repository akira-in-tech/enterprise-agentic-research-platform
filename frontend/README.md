# Evident Research Console

Vue 3, TypeScript, and Vite operator interface for the research platform.

## Run locally

```bash
npm install
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`.
Open the workspace menu and provide an existing tenant UUID and optional user
UUID before submitting a real research job.

## Verification

```bash
npm run typecheck
npm test
npm run build
```

The interface connects to the existing asynchronous research contract:

```text
POST /research-runs/jobs
→ authenticated tenant headers
→ fetch-based SSE progress stream
→ durable report retrieval
→ scored source inspection
```

Research history is deliberately browser-local until a tenant-scoped history
endpoint is added. Private-knowledge selection is shown as unavailable rather
than presented as a control that the current API would silently ignore.
