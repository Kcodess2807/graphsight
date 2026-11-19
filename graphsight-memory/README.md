# graphsight-memory

Project memory for coding agents. It reads a repo's GitHub history into a typed graph, lets
your agent add the team facts GitHub doesn't hold, and hands back the facts for a question
with the source of each one.

```bash
pip install graphsight-memory
```

```python
from graphsight_memory import Memory

mem = Memory("team.lbug")                         # one local file
mem.sync_github("org/repo")                       # PRs, issues, people, files
mem.remember("src/checkout.py", "OWNED_BY", "payments team", source="standup")

r = mem.recall("Who wrote the last change to the file payments owns?")
print(r)                                          # facts and evidence, ready for a prompt
```

No API key and no GPU are needed. The embedding model is MiniLM on ONNX, downloaded once on
first use (about 90 MB).

## What a recall returns

```python
>>> r.facts
[Fact(text='src/checkout.py OWNED_BY payments team', remembered=True, source='standup'),
 Fact(text='PR #7 TOUCHES src/checkout.py', remembered=False, source=None),
 Fact(text='alice AUTHORED PR #7', remembered=False, source=None), ...]
```

Every fact reads in its own direction, SUBJECT RELATION OBJECT. Facts an agent wrote are
marked `remembered`, with their source. The answer model is told which is which, so a note
from a standup never passes for a record from GitHub.

## Changing what it knows

```python
mem.remember("src/checkout.py", "OWNED_BY", "billing team", source="reorg", replace=True)
mem.retract("src/checkout.py", "OWNED_BY")        # no owner now
mem.forget("src/checkout.py", "OWNED_BY", "payments team")
```

- **`replace=True`** ends the old fact. It stops being recalled and stays in the store as
  history.
- **`retract`** ends a fact with nothing in its place, so the answer becomes "unknown"
  rather than the last value.
- **`forget`** deletes a fact the agent wrote, history included. Facts read from GitHub
  can't be forgotten.

## Relations

`remember` takes a fixed list of relations (`graphsight_memory.RELATIONS`), such as
OWNED_BY, MEMBER_OF, BLOCKED_BY and TRACKED_IN. A fixed list is what lets an update replace
the old fact instead of being stored next to it under a different name. Open the store with
`Memory(path, relations=None)` to allow any name.

## Learning from text

```python
pip install "graphsight-memory[llm]"              # and set OPENROUTER_API_KEY

mem.learn("Ownership of checkout moved to the billing team.", source="reorg-memo")
```

An LLM pulls the facts out, using only the allowed relations, and each one is remembered. It
sees what is already stored, so an update replaces the old fact.

## Without the network

```python
mem.load("org/repo", "snapshot.json")             # {pulls, issues, commits}, as saved by sync
```

## How well it works

Measured on frozen repos with tasks written before any run and graded by exact match. On 28
questions that join a told fact to a GitHub fact, on a repo nothing was tuned on, graph
memory answered 27, replaying past statements answered 10, and no memory 5. On plain
lookups it ties keyword search. Every repo tested so far fits in one prompt, and putting
everything in the prompt did as well. [The full evaluation](https://github.com/Kcodess2807/graphsight/tree/main/backend/eval).

## Requirements

Python 3.12 or later. The store is [LadybugDB](https://github.com/LadybugDB/ladybug), an
embedded graph database with a vector index, in a single file.
