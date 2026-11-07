"""Build tasks/<corpus>.jsonl from a frozen snapshot, so gold answers come from
GitHub's records and not from anyone's judgment. Only the reworded descriptions
are hand-written, and each one is tied to a record that exists.

    python eval/make_tasks.py pallets_click
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLOSES = re.compile(r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)

# PR -> a description that avoids the title's distinctive words
CLICK_PRS = {
    3878: "makes the test runner print control bytes in caret notation",
    3896: "lets tests hand extra settings straight to the test runner call",
    3884: "corrects what help shows for environment variables that are lists or blank",
    3909: "adds the newest CPython release to continuous integration",
    3858: "teaches type checkers what a filesystem path parameter returns",
    3900: "explains what happens when someone interrupts the pager",
    3897: "adds a walkthrough for compiling a CLI into a single binary",
    3901: "stops translating the help of obsolete commands",
    3899: "adds tests that removing terminal colors gives back the original text",
    3861: "moves a shared constructor setting up into the base class",
    3866: "warns about names that cannot be used as Python variables",
    3865: "fixes how long help gets cut down to a short summary",
    3826: "documents autocompletion inside interactive questions",
    3905: "strips ticket links from everywhere but the release notes",
    3877: "replaces an old display name attribute with a new one",
    3906: "updates the action that uploads releases",
}

CLICK_ISSUES = {
    3903: "says an interrupted safe save destroys the existing data",
    3886: "says the whole program dies when the pager is stopped",
    3832: "reports that error text can smuggle in terminal control codes",
    3840: "reports that opening the external editor crashes on Microsoft's OS",
    3882: "asks for help output to open the manual page instead",
}

# nothing in the corpus answers these: the right response is "unknown"
CLICK_UNANSWERABLE = [
    "Who authored PR #1234?",
    "Which files did PR #3000 touch?",
    "Who reported issue #9001?",
    "Which PR added async command support?",
    "Which PR fixed issue #3904?",
    "Who reviewed PR #3906?",
]


# held-out corpus: written before any evaluation ran on it, and never changed after
PYTEST_PRS = {
    15298: "keeps one measured time object on the record of each test phase",
    15296: "brings back quoted numbers for the output detail settings in the config file",
    15285: "repairs approximate comparison for a machine learning array library",
    15255: "stops scanning the whole scratch folder each time a fresh one is needed",
    15246: "registers a third-party add-on for checking AI agents",
    15245: "explains several ways to set up an isolated Python environment before installing",
    15227: "relaxes the static type of the attribute that points at the current test item",
    15223: "reduces the flood of automated upgrade pull requests by batching them per ecosystem",
    15202: "warns when raw binary data is handed to the console output writer",
    15193: "makes the return type of the parametrize helper importable by users",
    15192: "repairs the Sphinx site after a plugin library upgrade",
    15319: "raises the async add-on version so integration tests install on development builds",
    15211: "upgrades the web framework used in the integration tests",
    15272: "copies the changelog of the latest version back onto the main branch",
    15257: "refreshes the generated catalogue of third-party add-ons",
}

PYTEST_ISSUES = {
    15341: "says cleanup of old scratch folders fails when a parent lost write permission",
    15335: "reports a crash when comparing a not-a-number decimal value",
    15295: "reports a startup crash when the store directory path contains parent-directory dots",
    15237: "reports a crash when a different thread creates a log handle during a test",
    15289: "asks whether bailing out in cleanup code should produce a warning",
    15221: "says passing a lot of test paths from one folder makes discovery repeat work",
}

PYTEST_UNANSWERABLE = [
    "Who authored PR #1234?",
    "Which files did PR #3000 touch?",
    "Who reported issue #90010?",
    "Which PR added a GraphQL reporter?",
    "Which PR fixed issue #15200?",
    "Who reviewed PR #15272?",
]

CORPORA = {
    "pallets_click": (CLICK_PRS, CLICK_ISSUES, CLICK_UNANSWERABLE),
    "pytest_dev_pytest": (PYTEST_PRS, PYTEST_ISSUES, PYTEST_UNANSWERABLE),
}


def main() -> None:
    corpus = sys.argv[1]
    described, issues_described, unanswerable = CORPORA[corpus]
    data = json.loads((HERE / f"corpus/{corpus}.json").read_text(encoding="utf-8"))
    prs = {p["number"]: p for p in data["pulls"]}
    tasks: list[dict] = []

    def add(category: str, question: str, gold: list[str], **extra) -> None:
        tasks.append({"id": f"{category}-{len(tasks)}", "category": category,
                      "question": question, "gold": gold, **extra})

    reviewers = {
        n: sorted({r["user"]["login"] for r in p["reviews"]} - {p["user"]["login"], None})
        for n, p in prs.items()
    }

    # one hop, id in the question
    for n in sorted(prs)[::3]:
        add("lookup", f"Who authored PR #{n}?", [prs[n]["user"]["login"]])
    for issue in data["issues"][::5]:
        add("lookup", f"Who reported issue #{issue['number']}?", [issue["user"]["login"]])
    for n, names in sorted(reviewers.items()):
        if names and len(tasks) < 20:
            add("lookup", f"Who reviewed PR #{n}?", names)

    # two steps: find the PR through its issue, then read a fact off it
    closes = {int(i): n for n, p in prs.items() for i in CLOSES.findall(p["body"] or "")}
    for issue, n in sorted(closes.items()):
        add("multi_hop", f"Which PR fixed issue #{issue}?", [f"PR #{n}"])
        if reviewers[n]:
            add("multi_hop", f"Who reviewed the PR that fixed issue #{issue}?", reviewers[n])
        add("multi_hop", f"Who authored the PR that fixed issue #{issue}?", [prs[n]["user"]["login"]])
    for commit in data["commits"]:
        for issue in CLOSES.findall(commit["commit"]["message"] or ""):
            add("multi_hop", f"Which commit fixed issue #{issue}?", [commit["sha"][:7]])

    # list everything: the shape a capped graph walk should struggle with
    by_file = defaultdict(list)
    for n, p in prs.items():
        for f in p["files"]:
            by_file[f["filename"]].append(n)
    small = [f for f, ns in sorted(by_file.items()) if 2 <= len(ns) <= 4 and f.startswith("src/")]
    for f in small[:6]:
        add("enumerate", f"Which PRs touched {f}?", [f"PR #{n}" for n in sorted(by_file[f])])
    reviewed = Counter(name for names in reviewers.values() for name in names)
    for name in sorted(p for p, c in reviewed.items() if c <= 3)[:5]:
        add("enumerate", f"Which PRs did {name} review?",
            [f"PR #{n}" for n, names in sorted(reviewers.items()) if name in names])

    # no id: found only by meaning
    for n, phrase in described.items():
        add("described", f"Which PR {phrase}?", [f"PR #{n}"])
    issues = {i["number"] for i in data["issues"]}
    for n, phrase in issues_described.items():
        assert n in issues, n
        add("described", f"Which issue {phrase}?", [f"Issue #{n}"])

    # a later task that a past run can help with: same subject, new question
    for n, phrase in described.items():
        if reviewers[n]:
            add("followup", f"Who reviewed the PR that {phrase}?", reviewers[n],
                seed=f"Which PR {phrase}?", seed_gold=[f"PR #{n}"])

    for question in unanswerable:
        add("unanswerable", question, ["unknown"])

    out = HERE / f"tasks/{corpus}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(json.dumps(t) for t in tasks) + "\n", encoding="utf-8")
    print(Counter(t["category"] for t in tasks), len(tasks))


if __name__ == "__main__":
    main()
