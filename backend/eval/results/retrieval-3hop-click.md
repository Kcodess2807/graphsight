Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Condition | lookup | multi_hop | enumerate | described | followup | unanswerable | all | avg prompt tokens |
|---|---|---|---|---|---|---|---|---|
| full_context | 20/20 | 10/10 | 11/11 | 21/21 | 13/13 | 5/6 | 80/81 | 32720 |
| bm25 | 20/20 | 10/10 | 11/11 | 18/21 | 11/13 | 5/6 | 75/81 | 5629 |
| vector | 3/20 | 1/10 | 5/11 | 17/21 | 9/13 | 6/6 | 41/81 | 3547 |
| graph_no_facts | 0/20 | 2/10 | 0/11 | 14/21 | 0/13 | 6/6 | 22/81 | 2475 |
| graph | 20/20 | 10/10 | 11/11 | 14/21 | 8/13 | 6/6 | 69/81 | 2849 |
| graph_memory | - | - | - | - | 10/13 | - | 10/13 | 2491 |
| graph_poisoned | 10/10 | - | - | - | - | - | 10/10 | 5493 |

Poisoned memories followed: 0/10
