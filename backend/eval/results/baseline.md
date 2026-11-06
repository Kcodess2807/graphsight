Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Condition | lookup | multi_hop | enumerate | described | followup | unanswerable | all | avg prompt tokens |
|---|---|---|---|---|---|---|---|---|
| full_context | 20/20 | 10/10 | 11/11 | 21/21 | 13/13 | 5/6 | 80/81 | 32622 |
| bm25 | 20/20 | 10/10 | 11/11 | 18/21 | 11/13 | 5/6 | 75/81 | 5531 |
| vector | 3/20 | 1/10 | 5/11 | 18/21 | 9/13 | 6/6 | 42/81 | 3449 |
| graph_no_facts | 0/20 | 0/10 | 0/11 | 3/21 | 0/13 | 6/6 | 9/81 | 961 |
| graph | 20/20 | 5/10 | 11/11 | 3/21 | 0/13 | 6/6 | 45/81 | 1295 |
| graph_memory | - | - | - | - | 2/13 | - | 2/13 | 2132 |
| graph_poisoned | 10/10 | - | - | - | - | - | 10/10 | 3505 |

Poisoned memories followed: 0/10
