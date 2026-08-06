# Evident Research Console

Vue 3, TypeScript, and Vite operator interface for the research platform.

The interface uses a warm editorial visual system, an original round eight-ray
brand mark, and a compact view of the eight-agent research workflow. Its report
hierarchy presents the conclusion first, quality signals second, and source
evidence on demand.

## Run locally

```bash
npm install
npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`.
Open the workspace menu and provide an existing tenant UUID and optional user
UUID before submitting a real research job.

## Run with the complete stack

From the repository root:

```bash
cp .env.example .env
docker compose up --build --detach --wait
```

Open `http://localhost:3000`. Nginx serves the production Vue build and proxies
`/api` to FastAPI with response buffering disabled for SSE. Qwen requests reuse
the host Ollama service through `host.docker.internal`.

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

Operational states are designed explicitly for Redis unavailability, SSE
disconnection, job failure, report unavailability, and citation revision. Run
the Vite app with `?design-preview` for realistic local fixtures; append
`&state=redis`, `sse`, `failed`, `report`, or `citation` to inspect a specific
recovery state without calling the backend.
