# Your first trace

A 10-minute walkthrough, start to finish. No prior Graphsight knowledge, no backend, no
account. By the end you'll have a real agent run open in your browser with every retrieved
document marked **used** or **ignored**.

If you already know what a trace is and just want the API, read
[graphsight-langgraph](../graphsight-langgraph/README.md) instead.

---

## 1. Install

```bash
pip install graphsight graphsight-langgraph
```

Two packages, because they do different jobs:

| | |
|---|---|
| `graphsight-langgraph` | **records** a run. One callback handler. Depends only on `langchain-core`. |
| `graphsight` | **shows** it. A local viewer. Zero dependencies. |

---

## 2. See it work before writing any code

The fastest way to understand the output is to look at one. This builds a real trace from a
public GitHub repo, no token needed, no agent of your own:

```bash
pip install "graphsight-langgraph[example]"
graphsight-github-trace pallets/click "who fixed the recent bugs?"
graphsight graphsight_out/trace_state.json
```

Your browser opens on a graph of that repository. Click any node to inspect it.

Now do it with your own agent.

---

## 3. Trace your own agent

Here is a complete, runnable file. It uses a fake retriever so you can run it right now and
swap in your real one after.

```python
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from graphsight_langgraph import LangGraphTracer, capture


class State(TypedDict):
    question: str
    docs: list
    answer: str


class MyRetriever(BaseRetriever):
    def _get_relevant_documents(self, query, *, run_manager=None):
        return [
            Document(
                page_content="PR #412 'fix: refresh the expired token on 401' merged yesterday.",
                metadata={"id": "pr_412", "label": "PR #412",
                          "kind": "pull_request", "score": 0.34},
            ),
            Document(
                page_content="PR #101 'refactor: session helpers' merged 8 months ago.",
                metadata={"id": "pr_101", "label": "PR #101",
                          "kind": "pull_request", "score": 0.91},
            ),
        ]


retriever = MyRetriever()


def retrieve(state: State, config):          # <- accept config
    return {"docs": retriever.invoke(state["question"], config=config)}   # <- pass it on


def answer(state: State, config):
    return {"answer": "PR #412 fixed it, the token refresh now retries once on a 401."}


graph = StateGraph(State)
graph.add_node("retrieve", retrieve)
graph.add_node("answer", answer)
graph.set_entry_point("retrieve")
graph.add_edge("retrieve", "answer")
graph.add_edge("answer", END)
app = graph.compile()

tracer = LangGraphTracer()
result = app.invoke({"question": "what broke the session flow?"},
                    config={"callbacks": [tracer]})

capture(tracer, query="what broke the session flow?", answer=result["answer"])
```

Run it, then:

```bash
graphsight .graphsight/
```

---

## 4. Read the result

Two documents came back. **PR #101 scored 0.91, nearly three times higher than PR #412's
0.34, and the answer never used it.**

Click each node and compare the inspector:

| | PR #101 | PR #412 |
|---|---|---|
| Fused score | **0.910** | 0.340 |
| Status | `retrieved, unused` | `in the answer` |

That gap is the whole point. Your retriever ranked confidently and the model disagreed. The
two failures this exposes:

- **A dimmed node with a high score**, the right document was retrieved and the model
  ignored it. Your retriever is fine; your prompt or context ordering isn't.
- **A highlighted node that shouldn't be**, the model trusted the wrong thing.

The usage split is a lexical overlap heuristic (threshold 0.2), labeled as such. No LLM
re-reads your evidence and no score is invented.

---

## 5. The one thing that trips people up

Callbacks only reach runnables that receive the run's config. In the example above, note the
two marked lines:

```python
def retrieve(state, config):                             # accept it
    docs = retriever.invoke(state["question"], config=config)   # pass it through
```

**Skip that and your trace shows the nodes but zero retrievals**, an empty graph. It is the
most common thing to get wrong.

---

## 6. Two things that change what you see

**Pass `answer=`.** Without it there's no used/ignored split, every item renders plain,
because nothing has been compared against anything. Graphsight won't claim usage it can't
measure.

**Add a `score`.** Any of `score`, `relevance_score`, `similarity`, `_score` or
`vector_score` in `Document.metadata` becomes the retrieval score. Without one, no score
chips render, nothing is fabricated.

---

## Where to go next

- **Every run accumulates.** `capture()` appends to `./.graphsight/`, so `graphsight
  .graphsight/` becomes your debugging history. Compare two runs to see what a prompt change
  did to retrieval.
- **Draw relationships between results**, author, resolves, touches, with
  `metadata["edges"]`. Both ends of an edge must be documents you returned. See
  [making your retriever graph-aware](../graphsight-langgraph/README.md#making-your-retriever-graph-aware).
- **Full API and schema:** [graphsight-langgraph](../graphsight-langgraph/README.md).
- **Viewer options, sharing traces, troubleshooting:** [graphsight](../graphsight/README.md).
- **The graph memory engine behind it:** [main README](../README.md).
