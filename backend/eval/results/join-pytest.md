Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Setup | memory_then_github | github_then_memory | through_an_issue | through_a_file | join_after_update | join_missing | all | stale answers on changed facts |
|---|---|---|---|---|---|---|---|---|
| full_context | 5/6 | 6/6 | 6/6 | 3/3 | 3/3 | 5/5 | 28/29 | 0/3 |
| none | 0/6 | 0/6 | 0/6 | 0/3 | 0/3 | 5/5 | 5/29 | 0/3 |
| episodic | 4/6 | 0/6 | 3/6 | 0/3 | 0/3 | 5/5 | 12/29 | 0/3 |
| graph_memory | 1/6 | 5/6 | 2/6 | 3/3 | 3/3 | 5/5 | 19/29 | 0/3 |

Extraction stored 25 facts from 26 statements; 1 statements stored nothing.

graph_memory vs episodic, 24 tasks: graph_memory alone right on 12, episodic alone on 5, two-sided sign test p=0.143.
