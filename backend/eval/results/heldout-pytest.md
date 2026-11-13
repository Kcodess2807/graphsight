Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Condition | lookup | multi_hop | enumerate | described | followup | unanswerable | all | avg prompt tokens |
|---|---|---|---|---|---|---|---|---|
| full_context | 20/20 | 25/26 | 7/7 | 20/21 | 14/14 | 5/6 | 91/94 | 82713 |
| bm25 | 19/20 | 25/26 | 7/7 | 14/21 | 10/14 | 5/6 | 80/94 | 12704 |
| vector | 2/20 | 4/26 | 3/7 | 20/21 | 12/14 | 5/6 | 46/94 | 10507 |
| graph_no_facts | 3/20 | 11/26 | 2/7 | 18/21 | 0/14 | 6/6 | 40/94 | 10283 |
| graph | 20/20 | 25/26 | 7/7 | 18/21 | 9/14 | 6/6 | 85/94 | 10637 |
| graph_memory | - | - | - | - | 11/14 | - | 11/14 | 5308 |
| graph_poisoned | 10/10 | - | - | - | - | - | 10/10 | 17055 |

Poisoned memories followed: 0/10
