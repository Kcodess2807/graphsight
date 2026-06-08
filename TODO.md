# TraceRAG — Roadmap & Audit

> Honest status of the Tier 1/2/3 feature list against what's **actually in the
> code** (audited 2026-06-09). Status legend:
> ✅ built · 🟡 partial / needs refinement · ❌ unbuilt · 🐞 known bug

---

## 🐞 Known bugs / latent issues

- [ ] **Citation regex has no word boundaries.**
  [AnswerCard.tsx:32](frontend/src/components/left/AnswerCard.tsx#L32) builds
  `new RegExp(labels.join("|"), "gi")` with no `\b` guards, so a short label
  like `click` matches *inside* `clicked`, producing a false-positive chip
  mid-word. Fix: add word-boundary guards — carefully, because labels such as
  `PR #5818` end in non-word characters, so a naive `\b...\b` wrapper won't fit
  every label. Likely needs per-label boundary logic (word-char-aware) rather
  than one blanket `\b`.
- [ ] **Placeholder metrics shown as real.** `tokens` and `peakRamGb` are
  hardcoded `0` ([api.ts:499](frontend/src/lib/api.ts#L499)) but rendered in the
  MetricsFooter. Either wire them or remove them.
- [ ] **"Confidence" is presentational, not calibrated.** `deriveConfidence`
  ([api.ts:309](frontend/src/lib/api.ts#L309)) is derived from mean edge
  confidence + a fixed prior. Relabel or properly ground it before leaning on it
  in a demo.

---

## Tier 1 — the trust gap

- ✅ **Clickable citations.** Built & committed (`17b68c4`). Frontend regex in
  [AnswerCard.tsx](frontend/src/components/left/AnswerCard.tsx); pan/zoom/highlight
  via `focusById` in
  [VisualTracer.tsx:128](frontend/src/components/right/VisualTracer.tsx#L128).
  (See word-boundary bug above.)
- ✅ **Graph-aware suggested queries.** `/api/suggestions` builds questions from
  the active graph's hub entities ([api.py](backend/api.py)); rendered via
  `SuggestionChips` + `EmptyState`.
- 🟡 **Honest "no strong match" state.** `LowGroundingHint` exists and detects
  LLM hedging via `LOW_GROUNDING_RE`
  ([LeftPane.tsx:28](frontend/src/components/left/LeftPane.tsx#L28)), showing an
  amber "try these" card. **Gap:** it appends the hint *below* the verbose LLM
  apology rather than replacing it. Refinement: suppress/replace the apology
  text when grounding is low so users don't read a 6-sentence non-answer.

## Tier 2 — perceived performance

- ✅ **Streaming answer.** `/api/answer/stream` + `streamAnswer`
  ([api.ts](frontend/src/lib/api.ts)); AnswerCard streams token-by-token with a
  caret.
- 🟡 **Live execution steps.** `LiveProgress` renders the 5 phases, but they
  **advance on a 650ms timer, not real backend events**
  ([LiveProgress.tsx:7](frontend/src/components/left/LiveProgress.tsx#L7) — the
  code comment says so). `ExecutionStepper` shows accurate *post-hoc* steps from
  the trace log. Refinement: drive the live phases from real route timings
  (the backend already logs them) instead of a timer.

## Tier 3 — history & polish

- 🟡 **History sidebar.** Built: list, new chat, select, timestamp, title-on-hover
  ([HistorySidebar.tsx](frontend/src/components/left/HistorySidebar.tsx)).
  **Unbuilt:** grouping by Today/Yesterday/Earlier, **rename**, **delete**,
  dedupe of consecutive identical queries. (Rename has a backend path via
  `create_or_rename_session`; **delete needs a new `DELETE /api/sessions/{id}`
  endpoint** — does not exist yet.)
- ❌ **Click-to-explore on the canvas.** Not implemented. VisualTracer supports
  drag/select/focus but has no `onNodeClick` → expand-neighbors. The
  `/api/subgraph` endpoint already exists and could back progressive expansion.
  **This is the single biggest genuinely-unbuilt interactive feature.**
- ❌ **Copy-answer button.** AnswerCard has no copy control.
- ❌ **Persist selected graph across reloads.** `GraphSwitcher` re-reads the
  active graph from the server on every mount
  ([GraphSwitcher.tsx](frontend/src/components/left/GraphSwitcher.tsx)); no
  localStorage, so a refresh forgets your selection.
- 🟡 **Onboarding hint.** `EmptyState` covers a fresh/empty session; no
  first-visit walkthrough beyond that.

---

## Backend / housekeeping (from earlier sessions — verify)

- [ ] Refresh the benchmark `TEST_SET` — stale (ShopFlow queries vs current
      Jira/GitHub data).
- [ ] README reportedly still says "Next.js" (it's Vite) — verify & fix.
- [ ] Rotate the OpenRouter / Groq / Clerk / Neon keys pasted in chat earlier.

---

## Recommended build order (true roadmap)

**Quick wins (~1 hr total), do first:**
1. 🐞 Word-boundary fix in the citation regex (small, removes a visible bug).
2. ❌ Copy-answer button (trivial, high daily-use value).
3. ❌ Persist selected graph in localStorage (one `useEffect`, kills a papercut).

**One substantial new feature (highest impact):**
4. ❌ Click-to-expand neighbors on the canvas — turns the graph from a static
   readout into an exploration tool. Reuses `/api/subgraph`. This is the
   marquee item for the "non-techie exploring the graph" audience.

**History UX (self-contained, satisfying):**
5. 🟡 Rename + delete + group sessions (needs the new DELETE endpoint).

**Refinements (polish, lower urgency):**
6. 🟡 Replace the low-grounding apology instead of appending to it.
7. 🟡 Drive LiveProgress from real route timings.
8. 🐞 Wire or remove the placeholder token/RAM metrics.
