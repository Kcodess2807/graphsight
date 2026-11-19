Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Setup | memory_then_github | github_then_memory | through_a_reporter | through_a_file | join_after_update | join_missing | all | stale answers on changed facts |
|---|---|---|---|---|---|---|---|---|
| full_context | 6/6 | 6/6 | 0/6 | 2/2 | 3/3 | 5/5 | 22/28 | 0/3 |
| none | 0/6 | 0/6 | 0/6 | 0/2 | 0/3 | 5/5 | 5/28 | 0/3 |
| episodic | 5/6 | 0/6 | 0/6 | 0/2 | 0/3 | 5/5 | 10/28 | 0/3 |
| graph_memory | 6/6 | 6/6 | 5/6 | 2/2 | 3/3 | 5/5 | 27/28 | 0/3 |

Extraction stored 25 facts from 25 statements; 0 statements stored nothing.

graph_memory vs episodic, 23 tasks: graph_memory alone right on 17, episodic alone on 0, two-sided sign test p=0.000.
