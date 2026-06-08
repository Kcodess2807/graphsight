# TraceRAG — Demo Script & Question Bank

> Curated questions for live demos, grounded in the **actual GLiNER-extracted
> entities** in each graph (rebuilt 2026-06-09, ~50 merged PRs per repo). Switch
> the active graph in the top-left dropdown, paste a question, and watch the
> retrieval arm + the clickable citations light up.

**Legend**
- **`[Graph]`** — relational query → leans on the **graph arm** (β≈0.85). Best for
  showing multi-hop traversal and the traced path.
- **`[Vector]`** — semantic query → leans on the **vector arm** (α≈0.80). Best for
  "explain / summarize" answers.
- ⭐ — strong **citation** demo: the answer names a specific PR / person, so the
  chips in the Answer card pan-and-highlight the node on the canvas.

---

## Showcase flow (the 90-second demo)

A tight three-beat sequence that shows the whole story:

1. **Graph traversal** — on `pallets/flask`, ask:
   > ⭐ `[Graph]` **What is related to PR #5818?**
   Watch the traced path light up and the Answer card name the PR + author.
2. **Citation → canvas** — click the **`PR #5818`** or author chip in the answer;
   the canvas pans, zooms, and highlights that node.
3. **Honest empty state** — still on `flask`, ask something off-domain:
   > `[Vector]` **How does the payment gateway handle refunds?**
   The amber "this graph may not cover that" hint appears with real suggestions —
   demonstrating the system *admits* when the graph lacks the answer.

---

## Existing repos

### encode/httpx
- ⭐ `[Graph]` What is related to PR #3699?
- `[Graph]` Which PRs did lovelydinosaur work on?
- `[Graph]` What is connected to cryptography?
- `[Graph]` Which PRs involve pytest or coverage?
- `[Vector]` Explain the recent changes to httpx.
- `[Vector]` How does httpx handle TLS / OpenSSL?

### fastapi/fastapi
- ⭐ `[Graph]` What is related to PR #15595?
- ⭐ `[Graph]` Which PR caused the JWKS / PyJWKClient changes?
- `[Vector]` Explain the security advisory GHSA-jq35-7prp-9v3f.
- `[Graph]` Who is tiangolo and what did they work on?
- `[Graph]` What is connected to pydantic?
- `[Graph]` Which PRs did YuriiMotov work on?

### pallets/click
- ⭐ `[Graph]` What is related to PR #3484?
- `[Graph]` Who is kdeldycke and what did they work on?
- `[Graph]` Which PRs did davidism work on?
- `[Graph]` What is connected to ruff?
- `[Vector]` Explain the recent Click changes.
- `[Graph]` What is PR #3509 about?

### pallets/flask
- ⭐ `[Graph]` What is related to PR #5818?
- `[Graph]` What did davidism work on?
- `[Graph]` Which PR caused the app-context / request-context changes?
- `[Graph]` What is connected to asyncio?
- `[Vector]` Explain how Flask handles request context.
- `[Graph]` What is PR #5945 about?

### psf/requests
- ⭐ `[Graph]` What is related to PR #7498?
- `[Graph]` Who is nateprewitt and what did they work on?
- `[Graph]` Which PRs involve urllib3 or mypy?
- `[Graph]` What is connected to Typeshed?
- `[Vector]` Explain the recent typing changes in requests.
- `[Graph]` What is PR #7427 about?

### pydantic/pydantic
- ⭐ `[Graph]` What is PR #13199 about?
- ⭐ `[Graph]` What is related to PR #13291?
- `[Graph]` What did Viicos work on?
- `[Graph]` Which PRs involve pydantic-core or PyO3?
- `[Vector]` Explain the recent pydantic-core changes.
- `[Graph]` What is connected to the reviewers team?

---

## New repos (AI/ML stack)

### huggingface/transformers
- ⭐ `[Graph]` What is PR #46505 about?
- `[Graph]` What is connected to vLLM?
- `[Graph]` Who is ydshieh and what did they work on?
- `[Graph]` Which PRs involve tokenizers?
- `[Vector]` Explain the recent transformers changes around VitPose.
- `[Graph]` What is connected to the huggingface team?

### langchain-ai/langchain
- ⭐ `[Graph]` What is PR #37968 about?
- `[Graph]` What is related to anthropic?
- `[Graph]` What did mdrxy work on?
- `[Graph]` Which integrations were updated — openai, fireworks, or xai?
- `[Vector]` Explain the model-profiles changes.
- `[Graph]` What is connected to chroma?

### openai/openai-python
- ⭐ `[Graph]` What is related to PR #3359?
- `[Graph]` What is the Stainless team connected to?
- `[Graph]` Which PRs involve semver / versioning?
- `[Graph]` What did jim-openai work on?
- `[Vector]` Explain the recent openai-python SDK changes.
- `[Vector]` How does the OpenAI SDK handle async clients?

---

## New repos (ASGI ecosystem)

### encode/starlette
- ⭐ `[Graph]` What is related to PR #3319?
- `[Graph]` Who is Kludex and what did they work on?
- `[Graph]` Which PRs were opened by Dependabot?
- `[Graph]` What did Adam Turner contribute?
- `[Vector]` Explain the recent Starlette changes.
- `[Graph]` What is connected to GitHub Actions?

### encode/uvicorn
- ⭐ `[Graph]` What did Kludex work on?
- `[Graph]` What is related to PR #2959?
- `[Graph]` Which PRs touch websockets or asyncio?
- `[Graph]` What is connected to Cloudflare?
- `[Vector]` How does uvicorn use asyncio?
- `[Vector]` Summarize the recent websockets changes.

### tiangolo/typer
- ⭐ `[Graph]` Who is svlandeg and what did they work on?
- `[Graph]` What did tiangolo work on?
- `[Graph]` What is connected to pydantic?
- `[Graph]` Which PRs involve ruff or mypy?
- `[Vector]` Explain the recent Typer changes.
- `[Graph]` What is connected to samuelcolvin?

---

## Tips for a clean demo

- **Lead with `[Graph]` questions** — they produce the visible traced-path "pop"
  and the multi-hop story that distinguishes GraphRAG from plain vector search.
- **Click a citation chip** after the answer renders to show the canvas focus —
  this is the single most convincing moment (claim → traceable evidence).
- **Toggle "Show context"** (top-right of the canvas) to reveal the dimmed 1-hop
  neighborhood around the traced path.
- **The PR numbers above are real** for the current rebuild, but a future
  re-ingest pulls the *latest* merged PRs and may shift them — re-run the
  inspection if you rebuild.
