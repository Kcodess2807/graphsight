"""Build tasks/join_pytest.json: questions that need a remembered fact AND a GitHub
fact. The GitHub half of every gold answer is read from the frozen snapshot and
asserted here; the remembered half is invented team knowledge.

    python eval/make_join_tasks.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLOSES = re.compile(r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)

NOTE = (
    "Join tasks on pytest-dev/pytest. Each question needs a fact the agent was told "
    "(invented, not true of the pytest project) joined to a fact GitHub records. The "
    "question never names the entity in the middle. Written and committed before any run. "
    "Pre-registered reading: graph memory has to beat episodic recall on the join "
    "categories (sign test, p<0.05) for the graph to count as adding something over "
    "replaying statements. A full-context arm, every record and every statement in the "
    "prompt, is reported beside them as the ceiling."
)


def main() -> int:
    data = json.loads((HERE / "corpus/pytest_dev_pytest.json").read_text(encoding="utf-8"))
    pulls = {p["number"]: p for p in data["pulls"]}
    touched = Counter(f["filename"] for p in data["pulls"] for f in p.get("files", []))

    def author(n: int) -> str:
        return pulls[n]["user"]["login"]

    def reviewers(n: int) -> list[str]:
        return sorted({r["user"]["login"] for r in pulls[n].get("reviews", [])})

    def only_file(n: int, path: str) -> str:
        # the file must lead to exactly this PR, or the join has more than one answer
        assert path in [f["filename"] for f in pulls[n]["files"]] and touched[path] == 1, (n, path)
        return path

    def resolves(n: int) -> int:
        (issue,) = sorted(set(CLOSES.findall(pulls[n].get("body") or "")))
        return int(issue)

    tasks: list[dict] = []

    def add(category: str, statements: list[str], question: str, gold: list[str], **extra) -> None:
        n = sum(t["category"] == category for t in tasks) + 1
        tasks.append({"id": f"{category}-{n}", "category": category, "statements": statements,
                      "question": question, "gold": gold, **extra})

    # remembered fact first, then a GitHub hop: team -> file -> PR -> person or issue
    for pr, path, team in [
        (15298, "src/_pytest/runner.py", "execution team"),
        (15246, "scripts/update-plugin-list.py", "tooling team"),
        (15223, ".github/dependabot.yml", "supply chain team"),
        (15202, "src/_pytest/terminal.py", "console team"),
    ]:
        add("memory_then_github", [f"The {team} owns {only_file(pr, path)}."],
            f"Who authored the PR that touches the file the {team} owns?", [author(pr)])
    add("memory_then_github", [f"The collection team owns {only_file(15227, 'src/_pytest/fixtures.py')}."],
        "Who reviewed the PR that touches the file the collection team owns?", reviewers(15227))
    add("memory_then_github", [f"The markers team owns {only_file(15193, 'src/_pytest/mark/structures.py')}."],
        "Which issue does the PR touching the markers team's file resolve?", [f"Issue #{resolves(15193)}"])

    # GitHub hop first, then the remembered fact: PR -> author -> team
    for pr, team in [(15246, "plugins guild"), (15202, "onboarding cohort"), (15193, "typing guild"),
                     (15192, "docs guild"), (15285, "numerics guild"), (15319, "async guild")]:
        add("github_then_memory", [f"{author(pr)} sits in the {team}."],
            f"Which group does the author of PR #{pr} sit in?", [team])

    # PR -> the issue it resolves -> where that issue is tracked
    for pr, board in [(15298, "RUN-7"), (15296, "DEP-3"), (15255, "TMP-12"),
                      (15245, "DOC-41"), (15202, "TERM-9"), (15192, "QA-205")]:
        add("through_an_issue", [f"Issue #{resolves(pr)} is tracked on the {board} board."],
            f"On which board is the issue that PR #{pr} resolves tracked?", [board])

    # PR -> its one file -> the team that owns it. These PRs change exactly one file.
    for pr, path, team in [(15257, "doc/en/reference/plugin_list.rst", "ecosystem team")]:
        assert len(pulls[pr]["files"]) == 1
        add("through_a_file", [f"The {team} owns {only_file(pr, path)}."],
            f"PR #{pr} changes one file. Which team owns that file?", [team])
    for pr, team in [(15246, "tooling team"), (15223, "supply chain team")]:
        # ownership was stated above, under memory_then_github
        assert len(pulls[pr]["files"]) == 1
        add("through_a_file", [], f"PR #{pr} changes one file. Which team owns that file?", [team])

    # the remembered half changed: only the newer value is right
    for pr, old, new in [(15309, "release squad", "security squad"), (15319, "triage squad", "ci squad"),
                         (15301, "core squad", "backports squad")]:
        (reviewer,) = reviewers(pr)
        add("join_after_update",
            [f"{reviewer} is in the {old}.", f"{reviewer} moved from the {old} to the {new}."],
            f"Which squad is the reviewer of PR #{pr} in?", [new], stale=[old])

    # one half of the join is missing, so the right answer is unknown
    add("join_missing", [], f"Which group does the author of PR #{15255} sit in?", ["unknown"])
    add("join_missing", [], f"On which board is the issue that PR #{15193} resolves tracked?", ["unknown"])
    add("join_missing", [], f"On which board is the issue that PR #{15285} resolves tracked?", ["unknown"])
    add("join_missing", [], "PR #15266 changes one file. Which team owns that file?", ["unknown"])
    add("join_missing", ["Avery-Quill sits in the benchmarks guild."],
        "Which group does the author of PR #9999 sit in?", ["unknown"])
    assert 9999 not in pulls and len(pulls[15266]["files"]) == 1
    # nobody above was given a group or squad who authored a "missing" PR
    stated = " ".join(s for t in tasks for s in t["statements"])
    assert author(15255) not in stated, author(15255)

    out = HERE / "tasks/join_pytest.json"
    lines = ",\n".join("    " + json.dumps(t) for t in tasks)
    out.write_text('{\n  "note": ' + json.dumps(NOTE) + ',\n  "tasks": [\n' + lines + "\n  ]\n}\n", encoding="utf-8")
    print(f"{len(tasks)} tasks -> {out.name}:", dict(Counter(t["category"] for t in tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
