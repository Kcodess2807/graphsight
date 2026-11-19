# Evaluation

Does the graph help, and does memory help? 81 tasks on a frozen snapshot of
`pallets/click` (25 PRs, 25 issues, 25 commits), with the same model and prompt
for every setup, and the same 81-task recipe repeated as 94 held-out tasks on
`pytest-dev/pytest`.

## Result

`anthropic/claude-haiku-5.5`, one run per repo. `pytest` is the held-out set: its tasks
were committed before any evaluation ran on it, and the engine wasn't changed afterwards.

| Setup | click (dev) | pytest (held-out) | both | pytest avg prompt tokens |
|---|---|---|---|---|
| full_context | 80/81 | 91/94 | 171/175 | 82,713 |
| bm25 | 75/81 | 80/94 | 155/175 | 12,704 |
| graph | 69/81 | 85/94 | 154/175 | 10,637 |
| vector | 42/81 | 46/94 | 88/175 | 10,507 |

- **The graph and BM25 are tied.** Across 175 tasks the graph alone was right on 18 and
  BM25 alone on 19. BM25 led on click and the graph led on pytest, and neither gap is more
  than noise (sign test p=0.24 and p=0.36).
- **Token savings don't generalize.** The graph used 43% of BM25's tokens on click and 84%
  on pytest. The click figure should not be quoted on its own.
- **Both beat vector search clearly:** the graph won 79 tasks to 13 (p<0.001). Plain
  embeddings can find a PR by meaning but can't answer who wrote it.
- **Graph facts carry the graph:** 92 tasks won to 1 against the same retrieval without them.
- **Full context is the most accurate,** at about eight times the tokens on pytest. It only
  fits because 75 records fit in a prompt.

**Memory.** On follow-up tasks, recall moved the graph from 8/13 to 10/13 on click and from
9/14 to 11/14 on pytest, with similar token use on pytest. That is 4 tasks improved and none
made worse (p=0.125), which is promising but not proof. These tasks were built so a past
run could help, so they test whether recall works when it should, not how often that happens.

**Poisoned memory.** A wrong answer planted as a successful run was followed 0 of 20 times
across both repos. In all 20 the graph held the right fact, so this says nothing about a
wrong memory when the graph has no answer.

## Memory writes

`run_memory.py`, from `results/memory-click.md`. 23 tasks: 10 facts stated earlier, 8 facts
that change between statements, and 5 questions about things never stated. The facts are
invented team knowledge about real click files, PRs and people, so GitHub can't hold them.
The tasks and the extraction prompt were committed before the run.

| Setup | new facts | changed facts | never stated | all | stale answers |
|---|---|---|---|---|---|
| none (graph only) | 0/10 | 0/8 | 4/5 | 4/23 | 0/8 |
| episodic | 0/10 | 0/8 | 5/5 | 5/23 | 0/8 |
| graph memory | 6/10 | 6/8 | 4/5 | 16/23 | 0/8 |

- **Graph memory against no memory:** 13 tasks right only with graph memory, 1 only without
  (sign test p=0.002).
- **Changed facts:** 6 of 8 right, and no stale value was ever given. Extraction marked 7 of the
  8 changes as replacing the old fact.
- **One answer memory made wrong:** asked where weekly *release* failures are tracked (never
  stated), graph memory answered INFRA-221, which was stated for *nightly CI* failures.
- **Without memory the agent guesses:** on 6 tasks it named recent contributors as owners or
  contacts. Graph memory did that on none.

**Why episodic scored so low, and why this doesn't settle graph against episodic.** Episodic
recall found the right statement on 18 of 23 tasks, but the agent answered on only 2. Its
prompt says past runs "can be out of date" and to trust the graph, so it set statements aside:
"The earlier run claimed that Rowlando13 covers it ... ANSWER: unknown". Graph-memory facts are
labelled "remembered" too, but arrive as graph facts and were trusted. A prompt that presents
statements as things the user said might close much of this gap. That is untested.

**Misses with the fact stored correctly.** Of graph memory's 6 misses on new and changed facts,
5 had the right fact in the graph. Agent facts weigh less than GitHub facts, and the walk keeps
only the top 5 neighbours by weight, so on busy nodes the agent's fact is cut. The sixth,
"sigstore toolchain" against the gold "sigstore", is arguably right.

**Limits.** 23 tasks, one repo, and both the tasks and the facts are mine.

### Held-out memory tasks, and the fixes

22 tasks on `pytest-dev/pytest` (`tasks/memory_pytest.json`), committed in 7775ab7 before any
memory run on that repo. They add retractions, where the right answer becomes unknown, and
near-miss questions that sound like a stated fact. The baseline ran on unchanged code (687f876).
Three fixes followed, written from the click run (7a30f2b): agent facts stay in reach on busy
nodes, retraction, and an agent prompt that uses a past run where the graph is silent. Then
one more run on each set.

| Setup | pytest before | pytest after | click before | click after |
|---|---|---|---|---|
| none | 5/22 | 5/22 | 4/23 | 4/23 |
| episodic | 5/22 | 14/22 | 5/23 | 13/23 |
| graph memory | 13/22 | 16/22 | 16/23 | 21/23 |

- **Graph memory beats no memory on held-out tasks:** 13 tasks to 2 (p=0.007).
- **Graph memory and episodic recall are tied on held-out tasks:** 5 tasks to 3 (p=0.73). The
  prompt fix alone took episodic from 5 to 14, which confirms the earlier gap was the prompt.
  On click graph memory leads 21 to 13, but click is where the fixes came from.
- **The fixes helped graph memory, not significantly:** 4 tasks gained and 1 lost on pytest
  (p=0.38). The lost one, "who is the release captain for pytest 10.0", went from right to
  unknown.
- **Confident wrong answers on pytest, after:** graph memory 5, episodic 4. Two of graph
  memory's are near-miss questions: asked which *team* owns `approx.py` it named bluetech, the
  person with the final say, and asked what PR #15285 *depends on* it named the issue it fixes.
  One retraction failed: asked what Issue #15341 is blocked by after the block was withdrawn,
  it named the PR that depends on that issue. "QA-88 board" against the gold "QA-88" is
  arguably right.
- **Changed facts:** graph memory 5 of 6 on pytest, episodic 3 of 6. Each gave one stale value.

### After the direction fix: pytest is no longer held out

Reading the pytest failures showed a bug and three weaknesses, and the fixes were written from
them. So `results/memory-pytest-nearmiss.md` is a check that the fixes work on the failures
they target, not a held-out result.

| Setup | pytest before these fixes | pytest after |
|---|---|---|
| none | 5/22 | 6/22 |
| episodic | 14/22 | 15/22 |
| graph memory | 16/22 | 20/22 |

- **The bug:** facts reached the model with no direction, as `A <-> B: BLOCKED_BY`. The failed
  retraction above was this: the retraction worked, and the model read another fact backwards.
  Facts now print in the direction they are stored, `PR #15255 BLOCKED_BY Issue #15341`.
- **Updates that missed:** an update named the same dashboard differently and used another
  relation, so it stood beside the old fact. The extractor now sees what is already remembered.
- **Relations folded together:** "has the final say" was stored as OWNED_BY. The extractor now
  names the relation after the message's own words.
- **Near misses:** the answer prompt, shared by every setup, now says a related fact is not
  the answer.
- **What it cost:** one task that passed now fails. Asked who is handling an issue, the agent
  found "xdist team" and answered unknown because it wanted a person.
- **Not rerun:** click, and the 175 retrieval tasks, which share the answer prompt and the fact
  format. Their numbers above are from before these changes.

## The join test: does the graph add anything over replaying statements?

29 tasks on pytest (`tasks/join_pytest.json`), committed in PR #17 before any run. Each needs a
fact the agent was told joined to a fact GitHub records, and the question never names the
entity in the middle. The reading was fixed first: graph memory has to beat episodic recall on
the 24 tasks where a join exists (sign test, p<0.05).

**It did not meet that bar.** From `results/join-pytest.md`:

| Setup | told, then GitHub | GitHub, then told | through an issue | through a file | after an update | one half missing | all |
|---|---|---|---|---|---|---|---|
| full context | 5/6 | 6/6 | 6/6 | 3/3 | 3/3 | 5/5 | 28/29 |
| none | 0/6 | 0/6 | 0/6 | 0/3 | 0/3 | 5/5 | 5/29 |
| episodic | 4/6 | 0/6 | 3/6 | 0/3 | 0/3 | 5/5 | 12/29 |
| graph memory | 1/6 | 5/6 | 2/6 | 3/3 | 3/3 | 5/5 | 19/29 |

- **The registered comparison:** on the 24 join tasks graph memory was alone in being right on
  12 and episodic on 5. Two-sided sign test p=0.143, so the difference is not established.
- **Full context won again,** 28 of 29, because 75 records and 26 statements fit in one prompt.
- **Where the graph is clearly better:** questions that start from GitHub and end at a told
  fact. It answered 11 of the 12 across three categories where episodic answered none, because
  word overlap between "the author of PR #15246" and "simukappu sits in the plugins guild" is
  nil. The graph reaches the statement through the author node.
- **Where the graph is worse:** told fact first, then GitHub, 1 of 6 against episodic's 4. The
  walk stops at two hops, so team -> file -> PR is found and the PR's author is not. Episodic
  recall returns the statement and the PR record together.
- **Four graph misses are the grader:** it answered "RUN-7 board" where the gold is "RUN-7",
  with the join done correctly. Counting those would give 14 wins to 3 (p=0.013). That is a
  reading made after seeing the answers, so it is reported here and not claimed.
- **One gold is debatable:** the reviewers of PR #15227 include its own author, which the
  baselines' records leave out. Full context missed it for that reason.

## How to read these numbers

- **click is a development set.** The fixes below were made against those tasks, so its
  graph score is optimistic. Only pytest is held out, and it is one repo.
- **The corpora are small.** 75 records each, all of which fit in one prompt, which a real
  repo's history would not. Larger corpora are untested.
- **BM25 is deliberately strong.** Its records spell out author, reviewers and files as
  text. BM25 over raw PR prose was not tested.
- **Two gold answers are debatable, and both were left as they are.** "Who reviewed" a PR
  with no reviews was answered "nobody" where the gold is "unknown", because the baselines'
  records say "Reviewed by: nobody". On pytest, the fix for #15284 is PR #15285 plus its
  backport #15301, and answering both counts as wrong. Counting these as right would give
  BM25 159/175 and the graph 155/175, which is still within noise.
- **Task bias.** The 34 described and follow-up tasks use hand-written descriptions. The
  rest, and every gold answer, come from GitHub's records, in `make_tasks.py`.

## What changed between runs

| Run | Change | Graph result |
|---|---|---|
| (discarded) | Prompt told the model to name PRs, people and files, so right answers failed exact match. Fixed the prompt, kept the grader | 40/81 |
| `baseline` | Clean harness | 45/81 |
| `with-titles` | Embed PR and issue titles, attach their text to the typed node | 60/81, but lookups fell to 15/20 |
| `linked-ids` | Find `PR #N` and `Issue #N` by exact match, fixing that regression | 69/81 |

## Run it

```bash
python eval/make_tasks.py pallets_click     # only if the snapshot or task list changes
python scripts/ingest_github.py --repo pallets/click --reset \
    --snapshot eval/corpus/pallets_click.json --db eval/click.lbug
python eval/run.py --corpus pallets_click --db eval/click.lbug --label my-run
```

A full run makes 430 to 500 model calls and cost $0.46 on click and $1.31 on pytest. Grading is in `grade.py`: the
final `ANSWER:` line must be exactly the right set, with no LLM judge. Every question's
context size, answer and grade is in `results/*.jsonl`, so each number above can be
checked by hand.
