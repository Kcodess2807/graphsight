# Graphsight frontend

Vite + React 18 + TypeScript. One app, three jobs: the landing page, the
live Studio (dev-only), and the trace viewer that ships inside the
`graphsight` pip package.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # dist/ — copy into ../graphsight/graphsight/dist to rebundle the viewer
```

## Routes

| Route | What | Needs backend? |
|---|---|---|
| `/` | landing page | no |
| `/memory/preview` | Studio on mock data, simulated tracing | no |
| `/memory/import` | render external traces; run history via `?runs=` | no |
| `/docs/concepts` | concepts doc | no |
| `/studio`, `/memory` | live Studio | yes — dev builds only (`VITE_ENABLE_STUDIO=1` to force) |
| `/classic` | legacy dashboard, kept for reference | yes — dev builds only |

Design system: [src/components/memory/DESIGN.md](src/components/memory/DESIGN.md)
— light neubrutalist, hard offset shadows, lime highlights, emerald accents.
