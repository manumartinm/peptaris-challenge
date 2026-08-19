# Trace Explorer

Local viewer for `PipelineTrace` files used by the De la Fuente Lab at the
University of Pennsylvania.

You can submit a design request to the local jobs API, or open an existing
`traces/{request_id}.trace.json`. Uploaded files stay in the browser.

```bash
# terminal 1, from the interview root
uv run route-agent-api

# terminal 2
cd trace-viewer
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Only one job can run at a time.

```bash
npm run lint
npm run typecheck
npm run build
```
