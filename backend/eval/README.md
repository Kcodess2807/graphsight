# Evaluation

Does the graph help, and does memory help? 81 tasks on a frozen snapshot of
`pallets/click` (25 PRs, 25 issues, 25 commits), with the same model and prompt
for every setup.

## Latest result

`anthropic/claude-haiku-5.5`, from `results/linked-ids.md`:

| Setup | lookup | multi_hop | enumerate | described | followup | unanswerable | all | avg prompt tokens |
|---|---|---|---|---|---|---|---|---|
| full_context | 20/20 | 10/10 | 11/11 | 21/21 | 13/13 | 5/6 | 80/81 | 32,622 |
| bm25 | 20/20 | 10/10 | 11/11 | 18/21 | 11/13 | 5/6 | 75/81 | 5,531 |
| graph | 20/20 | 10/10 | 11/11 | 14/21 | 8/13 | 6/6 | 69/81 | 2,379 |
| vector | 3/20 | 1/10 | 5/11 | 18/21 | 9/13 | 6/6 | 42/81 | 3,449 |
| graph_no_facts | 0/20 | 3/10 | 0/11 | 14/21 | 0/13 | 6/6 | 23/81 | 2,113 |

- **BM25 beats the graph on accuracy.** The graph ties it on lookups, multi-hop and
  list questions, and loses on questions asked by meaning, because it still embeds
  only names and titles, not text.
- **The graph uses 43% of BM25's tokens,** at $0.00047 per correct answer against
  $0.00078. Full context is the most accurate and costs $0.00349.
- **Graph facts are what make the graph work:** 23/81 without them, 69/81 with them.

**Memory.** On the 13 follow-up tasks, recall moved the graph from 8/13 to 10/13 and
raised prompt tokens from 2,568 to 5,601. Two tasks changed. That is too few to show
memory helps. Three seed runs failed, so those tasks had nothing to recall.

**Poisoned memory.** A wrong answer planted as a successful run was followed 0 of 10
times. All 10 were lookups where the graph held the right fact, so this says nothing
about a wrong memory when the graph has no answer.

## How to read these numbers

- **No held-out set.** The fixes below were made against these same tasks, so the graph
  scores are development numbers. They need confirming on tasks that played no part.
- **The corpus is small.** All 75 records fit in one prompt, which a real repo's history
  would not. Larger corpora are untested.
- **BM25 is deliberately strong.** Its records spell out author, reviewers and files as
  text. BM25 over raw PR prose was not tested.
- **One gold answer is debatable.** Both "unanswerable" misses are `Who reviewed PR #3906?`,
  answered "nobody" where the gold is "unknown". The baselines' records literally say
  "Reviewed by: nobody", so this is not a hallucination.
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
python eval/make_tasks.py     # only if the snapshot or task list changes
python scripts/ingest_github.py --repo pallets/click --reset \
    --snapshot eval/corpus/pallets_click.json --db eval/click.lbug
python eval/run.py --db eval/click.lbug --label my-run
```

A full run makes about 430 model calls and cost $0.46. Grading is in `grade.py`: the
final `ANSWER:` line must be exactly the right set, with no LLM judge. Every question's
context size, answer and grade is in `results/*.jsonl`, so each number above can be
checked by hand.
