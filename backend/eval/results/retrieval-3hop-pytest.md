Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Condition | lookup | multi_hop | enumerate | described | followup | unanswerable | all | avg prompt tokens |
|---|---|---|---|---|---|---|---|---|
| full_context | 20/20 | 24/26 | 7/7 | 20/21 | 14/14 | 5/6 | 90/94 | 82811 |
| bm25 | 19/20 | 26/26 | 7/7 | 15/21 | 10/14 | 5/6 | 82/94 | 12802 |
| vector | 2/20 | 5/26 | 3/7 | 20/21 | 12/14 | 5/6 | 47/94 | 10605 |
| graph_no_facts | 1/20 | 12/26 | 1/7 | 18/21 | 0/14 | 6/6 | 38/94 | 9825 |
| graph | 20/20 | 25/26 | 7/7 | 18/21 | 8/14 | 6/6 | 84/94 | 10433 |
| graph_memory | - | - | - | - | 13/14 | - | 13/14 | 6753 |
| graph_poisoned | 10/10 | - | - | - | - | - | 10/10 | 16246 |

Poisoned memories followed: 0/10
