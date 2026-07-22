# TraceRAG Design System — Light Neubrutalist

One system across the whole product surface: the landing page (`/`), the
Studio (`/studio`), and their shared components. The thesis: **you are not
talking to an AI, you are exploring the memory of your codebase** — so the
canvas is the primary surface, text is annotation, and color is semantic,
never decorative.

## 1. Color

| Token | Value | Use |
|---|---|---|
| Paper | `#FAFAFB` | Canvas background (`--m-paper`). |
| Surface | `#FFFFFF` | Sidebar, cards, inputs. |
| Ink | `#131316` | Text, borders, primary buttons. All structural borders are 1px ink — no gray hairlines. |
| Dim / Ghost | `zinc-600` / `zinc-400` | Body copy / labels, hints, idle states. |
| **Lime** | `#C8F169` | Marker-highlights (hero headline, "MEMORY" chip, score stickers) and **citation-focus** shadows. |
| **Emerald** | `#059669` | All interactive + traced states: focus shadows, traced edges/arrowheads, active list items, live dots, latency readout. |
| Entity tints | 600-weight hues in 10%-alpha wells | Per-type identity on nodes (see `entityTheme.ts`). Multicolor is confined to icon glyphs. |

**Semantic shadows on the canvas** — the load-bearing rule:
emerald offset shadow = node is on the traced path · lime offset shadow =
citation focus · faint gray = background context.

## 2. Depth — hard shadows, not blur

Every raised element is `border border-[#131316]` + a solid offset shadow
(`shadow-[3px_4px_0_0_#131316]`; `2px 3px` for chips, `6px 7px` for the
inspector). No glassmorphism, no soft drop shadows, no glows. Hover =
`-translate-y-0.5` lift, focus = the shadow turns emerald.

## 3. Typography

- **Display**: Space Grotesk (`font-display`) — wordmark, canvas hero,
  landing headlines, stat numbers. Bold, tight tracking.
- **UI**: Inter, 13px body, weights 400–700 (bold is used freely; this
  system likes weight).
- **Machine text**: JetBrains Mono for IDs, scores, latency, kbd hints, and
  section labels (`font-mono text-[10px] uppercase tracking-[0.2em]`).

## 4. Motion

- Easing `[0.16, 1, 0.3, 1]`; entrances are 6–12px rise + fade.
- **Tracing** (query running): no spinner ever — staggered sonar rings on
  nodes (`animate-trace-ping`), an emerald light sweep (`animate-scan`), and
  a hard-shadow status chip ("traversing graph…").
- **Camera pan** (citation click): `setCenter`, 650ms, zoom 1.25.
- Landing extras: tilted logo marquee (32s loop), floating hero stickers
  (`lp2-float`). Everything loops respects `prefers-reduced-motion`.

## 5. Keyboard map (Studio)

| Key | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Focus trace input (opens sidebar if collapsed) |
| `⌘\` | Toggle sidebar |
| `Enter` | Run trace |
| `Esc` | Close inspector |

## 6. Component map

```
Landing (/)          components/landing/LandingPage.tsx — hero + stickers,
                     marquee, code showcase, bento, pricing, waitlist forms
Studio (/studio)
  AppLayout          shell, keyboard, selection + focus state (light-only)
  ├── CommandPanel   sidebar: input, Recall, sessions, accordions, metrics
  │   └── CitationPill  sticker chip → camera pan + inspector
  ├── GraphCanvas    full-bleed React Flow, tracing animation, camera pan
  │   └── MemoryNode hard-shadow entity card, icon well, sonar ring
  └── InspectorPanel floating card: context, scores, provenance, source
```

Contracts: everything renders from `TraceState` (`types/trace.ts`).
`FocusRequest {id, nonce}` drives camera pans (nonce allows repeat clicks).
`NODE_HALF_W` in `GraphCanvas.tsx` is coupled to `w-[240px]` in
`MemoryNode.tsx`.

## 7. Voice

Interface copy is instrument-panel terse and never anthropomorphic:
"traversing graph…", "Recall", "49ms". No "I found…", no "Thinking…",
no chat bubbles, no avatars.
