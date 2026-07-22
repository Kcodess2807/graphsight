"""graphsight-github-trace: GitHub repo -> traced agent run -> trace_state.json.

Fetches recent PRs/issues, runs a small traced LangGraph agent over them,
writes graphsight_out/. Needs the `example` extra for LangGraph.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from .mapper import to_tracestate
from .tracer import LangGraphTracer

_API = "https://api.github.com"
_RESOLVE_RE = re.compile(r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9_#-]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "is", "are",
    "was", "were", "it", "this", "that", "with", "by", "at", "from", "what",
    "who", "which", "how", "why", "when", "did", "do", "does", "recently",
    "recent", "latest", "github", "user", "author",
}

# tie-break on equal lexical score: substantive artifacts over boilerplate
_KIND_PRIORITY = {"pull_request": 3, "ticket": 2, "repo": 1, "person": 0}


# github fetch, stdlib only
def _get(path: str, token: Optional[str]) -> Any:
    req = urllib.request.Request(
        f"{_API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "graphsight-github-trace/0.1",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            raise SystemExit(
                f"GitHub API {err.code} for {path}. Private repo or rate limit — "
                "pass --token or set GITHUB_TOKEN."
            ) from err
        if err.code == 404:
            raise SystemExit(f"GitHub API 404 for {path} — is the repo name right?") from err
        raise SystemExit(f"GitHub API error {err.code} for {path}.") from err


def _excerpt(text: Optional[str], limit: int = 400) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


# corpus
def build_corpus(repo: str, token: Optional[str], n_prs: int, n_issues: int) -> list[Document]:
    owner_name = repo.split("/")[-1]
    meta = _get(f"/repos/{repo}", token)
    repo_id = f"repo_{owner_name}"
    docs: list[Document] = [
        Document(
            page_content=_excerpt(
                f"{repo}: {meta.get('description') or 'no description'}. "
                f"Primary language {meta.get('language') or 'n/a'}, "
                f"{meta.get('stargazers_count', 0)} stars, "
                f"{meta.get('open_issues_count', 0)} open issues."
            ),
            metadata={
                "id": repo_id, "label": owner_name, "kind": "repo",
                "source": meta.get("html_url"),
            },
        )
    ]

    prs = _get(f"/repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page={n_prs}", token)
    authored: dict[str, list[str]] = {}
    for pr in prs:
        num, login = pr["number"], (pr.get("user") or {}).get("login") or "unknown"
        pr_id = f"pr_{num}"
        edges = [{"source": pr_id, "target": repo_id, "relation": "TOUCHES", "weight": 0.7},
                 {"source": f"person_{login}", "target": pr_id, "relation": "AUTHORED", "weight": 0.9}]
        for ref in _RESOLVE_RE.findall(pr.get("body") or ""):
            edges.append({"source": pr_id, "target": f"tkt_{ref}", "relation": "RESOLVES", "weight": 0.85})
        state = "merged" if pr.get("merged_at") else pr.get("state", "open")
        docs.append(Document(
            page_content=_excerpt(f"PR #{num} '{pr['title']}' by {login} ({state}). {pr.get('body') or ''}"),
            metadata={"id": pr_id, "label": f"PR #{num}", "kind": "pull_request",
                      "source": pr.get("html_url"), "edges": edges},
        ))
        authored.setdefault(login, []).append(pr_id)

    issues = _get(f"/repos/{repo}/issues?state=all&sort=updated&direction=desc&per_page={n_issues}", token)
    for issue in issues:
        if "pull_request" in issue:  # the issues API also returns PRs; skip those
            continue
        num, login = issue["number"], (issue.get("user") or {}).get("login") or "unknown"
        tkt_id = f"tkt_{num}"
        docs.append(Document(
            page_content=_excerpt(
                f"Issue #{num} '{issue['title']}' by {login} ({issue.get('state', 'open')}). "
                f"{issue.get('body') or ''}"
            ),
            metadata={"id": tkt_id, "label": f"Issue #{num}", "kind": "ticket",
                      "source": issue.get("html_url"),
                      "edges": [{"source": tkt_id, "target": repo_id,
                                 "relation": "REPORTS_ON", "weight": 0.6}]},
        ))
        authored.setdefault(login, [])

    for login, pr_ids in authored.items():
        docs.append(Document(
            page_content=f"GitHub user {login} — authored {len(pr_ids)} of the "
                         f"last {len(prs)} pull requests in {repo}.",
            metadata={"id": f"person_{login}", "label": login, "kind": "person",
                      "source": f"https://github.com/{login}",
                      # carried on both endpoints; the tracer dedups per retrieval
                      "edges": [{"source": f"person_{login}", "target": pid,
                                 "relation": "AUTHORED", "weight": 0.9} for pid in pr_ids]},
        ))
    return docs


# retrieval
def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP}


class LexicalGraphRetriever(BaseRetriever):
    """Lexical seeds + 1-hop edge neighbors, capped at k.

    Neighbors keep their own (often lower) lexical score. Edges are only
    emitted when both endpoints made the cut.
    """

    corpus: list[Document]
    k: int = 10

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        q = _tokens(query) or {"?"}
        scored = sorted(
            ((round(len(q & _tokens(d.page_content)) / len(q), 3), d) for d in self.corpus),
            key=lambda pair: (pair[0], _KIND_PRIORITY.get(pair[1].metadata["kind"], 0)),
            reverse=True,
        )
        by_id = {d.metadata["id"]: (s, d) for s, d in scored}

        # lexical seeds first
        kept: dict[str, tuple[float, Document]] = {
            d.metadata["id"]: (s, d) for s, d in scored[: max(3, self.k // 2)]
        }
        # then their 1-hop neighbors
        for _, doc in list(kept.values()):
            for edge in doc.metadata.get("edges", []):
                for nid in (edge["source"], edge["target"]):
                    if len(kept) >= self.k:
                        break
                    if nid not in kept and nid in by_id:
                        kept[nid] = by_id[nid]
        # fill spare slots
        for s, d in scored:
            if len(kept) >= self.k:
                break
            kept.setdefault(d.metadata["id"], (s, d))

        out = []
        for score, doc in sorted(kept.values(), key=lambda pair: pair[0], reverse=True):
            edges = [e for e in doc.metadata.get("edges", [])
                     if e["source"] in kept and e["target"] in kept]
            out.append(Document(
                page_content=doc.page_content,
                metadata={**{k: v for k, v in doc.metadata.items() if k != "edges"},
                          "score": score, "edges": edges},
            ))
        return out


# the traced agent
def run_traced(corpus: list[Document], question: str, repo: str, k: int):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        raise SystemExit(
            'LangGraph is required for the demo agent: pip install "graphsight-langgraph[example]"'
        )
    from typing import TypedDict

    retriever = LexicalGraphRetriever(corpus=corpus, k=k)

    class State(TypedDict):
        question: str
        docs: list[Document]
        answer: str

    def retrieve(state: State, config) -> dict:
        return {"docs": retriever.invoke(state["question"], config=config)}

    def answer(state: State, config) -> dict:
        docs = state["docs"]
        top = docs[0]
        kinds = {}
        for d in docs:
            kinds[d.metadata["kind"]] = kinds.get(d.metadata["kind"], 0) + 1
        parts = ", ".join(f"{v} {k.replace('_', ' ')}(s)" for k, v in sorted(kinds.items()))
        return {"answer": (
            f"Top match in {repo}: {top.metadata['label']} — "
            f"{top.page_content[:160]}… Retrieved {len(docs)} items ({parts}); "
            "open the graph to see who and what they connect to."
        )}

    graph = (StateGraph(State)
             .add_node("retrieve", retrieve)
             .add_node("answer", answer)
             .add_edge(START, "retrieve")
             .add_edge("retrieve", "answer")
             .add_edge("answer", END)
             .compile())

    tracer = LangGraphTracer()
    result = graph.invoke({"question": question}, config={"callbacks": [tracer]})
    return tracer.finish(query=question, answer=result["answer"])


# cli
def main(argv: Optional[list[str]] = None) -> None:
    # windows consoles default to cp1252
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(
        prog="graphsight-github-trace",
        description="GitHub repo → traced LangGraph run → Studio-ready trace_state.json",
    )
    parser.add_argument("repo", help="owner/name, e.g. langchain-ai/langgraph")
    parser.add_argument("question", nargs="?", default=None,
                        help='the question to trace (default: "what changed recently and who drove it?")')
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub token (or set GITHUB_TOKEN); needed for private repos")
    parser.add_argument("--prs", type=int, default=25, help="recent PRs to fetch (default 25)")
    parser.add_argument("--issues", type=int, default=25, help="recent issues to fetch (default 25)")
    parser.add_argument("--top", type=int, default=10, help="items to retrieve (default 10)")
    parser.add_argument("--out", type=Path, default=Path("graphsight_out"), help="output directory")
    args = parser.parse_args(argv)

    if "/" not in args.repo:
        parser.error("repo must be owner/name")
    question = args.question or f"What changed recently in {args.repo}, and who drove it?"

    print(f"fetching {args.repo} (last {args.prs} PRs, {args.issues} issues)…", file=sys.stderr)
    corpus = build_corpus(args.repo, args.token, args.prs, args.issues)
    print(f"corpus   : {len(corpus)} documents", file=sys.stderr)

    trace = run_traced(corpus, question, args.repo, args.top)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "agent_trace.json").write_text(
        json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    (args.out / "trace_state.json").write_text(
        json.dumps(to_tracestate(trace), indent=2), encoding="utf-8")

    items = sum(len(r.items) for r in trace.retrievals)
    edges = sum(len(r.edges) for r in trace.retrievals)
    arm = trace.retrievals[0].arm if trace.retrievals else "n/a"
    print(f"answer   : {trace.answer}")
    print(f"retrieved: {items} items · {edges} edges · arm={arm} · {trace.latency_ms:.1f}ms")
    print(f"wrote    : {args.out / 'agent_trace.json'}")
    print(f"wrote    : {args.out / 'trace_state.json'}  ← drop into the Studio at /memory/import")


if __name__ == "__main__":
    main()
