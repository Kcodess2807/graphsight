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
