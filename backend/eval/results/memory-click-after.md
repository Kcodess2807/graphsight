Model: `anthropic/claude-haiku-5.5`. Correct means the exact answer set.

| Setup | new_info | update | never_stated | all | stale answers on changed facts |
|---|---|---|---|---|---|
| none | 0/10 | 0/8 | 4/5 | 4/23 | 0/8 |
| episodic | 6/10 | 2/8 | 5/5 | 13/23 | 1/8 |
| graph_memory | 9/10 | 8/8 | 4/5 | 21/23 | 0/8 |

Extraction stored 27 facts from 26 statements; 0 statements stored nothing.
