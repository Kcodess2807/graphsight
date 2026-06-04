# TraceRAG Studio — Observability UI

The frontend dashboard for **TraceRAG**, the local-first GraphRAG observability
layer built on LadybugDB. A two-pane "execution log + visual tracer" for
debugging exactly *how* the hybrid router answered a query.

![two-pane dashboard: execution log on the left, interactive graph trace on the right]

## Stack

- **React 18 + TypeScript + Vite**
- **Tailwind CSS** (strict light mode) with the palette wired through shadcn CSS
  variables (`src/index.css`)
- **shadcn/ui** (Radix primitives) — Button, Card, Badge, Tooltip, HoverCard,
  Tabs, Separator, ScrollArea, Skeleton, Dialog, Sheet, Resizable, Command (cmdk)
- **reactflow** — the interactive node graph + custom traced edges
- **framer-motion** — subtle state transitions and the number tickers
- **sonner** — toasts · **recharts** — the token-reduction sparkline
- **lucide-react** — icons

## Run it

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

```bash
npm run build    # type-check + production bundle to dist/
npm run lint     # tsc --noEmit
```

## Backend integration

The UI talks to the FastAPI backend (`VITE_API_BASE`, default
`http://localhost:8000`) and chains two endpoints on every search:

1. `POST /api/trace` `{ query }` → `trace_log` (intent weights, execution path,
   metrics)
2. extract every unique node id from `execution_path` (`vector_seeds` + every
   `from_id`/`to_id` in `graph_hops`)
3. `POST /api/subgraph` `{ node_ids }` → `{ nodes, edges }`
4. merge + lay out into a `TraceState`

All of this lives in [`src/lib/api.ts`](src/lib/api.ts) — `runTraceQuery(query)`
orchestrates the flow and `adaptToTraceState(...)` merges both responses into the
single `TraceState` the UI already renders, so **no downstream component knows
the backend exists**. `TraceDashboard.handleSearch` calls it, measures real
round-trip latency, and falls back to the sample trace (with a warning toast) if
the backend is unreachable — the UI never goes blank.

**Layout:** the backend sends no coordinates, so
[`src/lib/layout.ts`](src/lib/layout.ts) runs a **dagre** left→right layered
layout (active/traced edges weighted onto a straight rank).

**Visual merging:** a node is *active* when it's in the execution path **or**
flagged `requested: true`; everything else renders as dimmed background context
(`opacity-40`, grey, slight desaturation). Active nodes/edges keep the indigo
trace treatment (indigo ring + animated indigo→violet dashed edges).

**Derived fields:** the contract doesn't include router confidence or
token/RAM telemetry, so those are derived honestly — confidence from the mean &
spread of graph-hop confidences, query time measured client-side, and
`total_nodes_evaluated` surfaced as the "Nodes Evaluated" metric. Drop real
fields into the response and the adapter will prefer them.

## What you're looking at

The whole UI is driven by a single, rigid `TraceState` interface
(`src/types/trace.ts`). When the backend is offline it falls back to realistic
mock data (`src/data/mockTrace.ts`) for the sample query
*"Which PR merged by engineer X caused the payments outage?"*.

- **Left pane — Execution Log (`src/components/left/`)**
  - `SearchCommand` — always-visible search styled as cmdk; ⌘K opens the
    command palette with query history + presets.
  - `RouterCard` — intent weights (α vector / β graph) as progress bars +
    a confidence/uncertainty meter (shades amber when the router is unsure).
  - `ExecutionStepper` — vertical timeline with connectors, checkmarks, and a
    staggered fade-in.
  - `MetricsFooter` — animated number tickers for token footprint (with the
    64% reduction badge + sparkline), peak RAM, and query time.

- **Right pane — Visual Tracer (`src/components/right/`)**
  - `VisualTracer` — React Flow canvas on a dotted grid. The active path
    (Document → PR → Service) uses an animated indigo→violet gradient dash;
    inactive nodes/edges recede to quiet grey.
  - `EntityNode` — custom node styled as a mini card, one lucide icon + soft
    color chip per entity type, with a metadata HoverCard.
  - `GraphControls` — frosted floating pill: zoom, recenter, show-orphans.

- **`TraceDashboard`** — composes the two panes in shadcn **Resizable** panels
  on desktop; collapses to **Tabs** under 1024px. Every panel has a Skeleton
  loading state.

## Theming

All colors are CSS variables in `src/index.css` (`--primary`, `--muted`,
`--border`, …). Change the palette in one place and the whole system follows.
Entity-type styling (icon + chip + badge) lives in `src/lib/entity.tsx`.
