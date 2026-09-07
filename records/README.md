# Game Records

Every file is an append-only JSONL Game Record: `game_start` (settings, Prompt
Version, both Agents), two `deployment` events, one `move` or `forfeit` per ply
(the Move, Combat result, Rationale, Scratchpad, native reasoning summary where
the provider returns one, thinking tokens with their source, seconds, and every
rejected attempt with its kind), and `game_end`. Replay any of them with
`python3 -m stratego.metrics <file>` or `python3 render_replay.py <file>`.

Matches, in the order they were played. `a` is the first Model named; a pair
plays one position twice with the Models swapped between the seats. Records at
Prompt Version `582e1248be6f` predate the prompt change described in the README
(material advice removed, threats after the legal list); `e1a5bb529c54` is the
current prompt.

| directory | a | b | thinking | ceiling | cap | games | a's W-L-D | by colour | prompt |
|---|---|---|---|---|---|---|---|---|---|
| `match-gptoss` | gpt-oss:20b | gpt-oss:20b | brief | 4000* | 60 | 6 | a 3-0-3 | R 2 / B 1 / draw 3 | fbf7e7d48db4 |
| `match-gptoss-brief` | gpt-oss:20b | gpt-oss:20b | brief | 16000 | 60 | 6 | a 2-1-3 | R 3 / B 0 / draw 3 | 582e1248be6f |
| `match-gptoss-standard` | gpt-oss:20b | gpt-oss:20b | standard | 16000 | 60 | 6 | a 2-3-1 | R 1 / B 4 / draw 1 | 582e1248be6f |
| `match-sonnet5-vs-gptoss-brief` | Sonnet 5 | gpt-oss:20b | brief | 16000 | 60 | 6 | a 2-2-2 | R 2 / B 2 / draw 2 | 582e1248be6f |
| `match-sonnet5-vs-gptoss-standard` | Sonnet 5 | gpt-oss:20b | standard | 16000 | 200 | 2 | a 2-0-0 | R 1 / B 1 / draw 0 | e1a5bb529c54 |
| `match-sonnet5-vs-terra-standard` | Sonnet 5 | gpt-5.6-terra | standard | 16000 | 200 | 6 | a 1-5-0 | R 2 / B 4 / draw 0 | e1a5bb529c54 |

`*` the first Match ran before `--max-tokens` existed, at the 4,000 default, inside
Ollama's 4,096-token context; its `thinking_tokens` field holds the provider's
completion count and reads back as `n/a` in metrics.

## Classic game

`classic-sonnet5-vs-terra/g1.jsonl`: Sonnet 5 (Red) vs gpt-5.6-terra (Blue), 40 pieces a side,
thinking `standard`, 500-ply cap, Prompt Version `e1a5bb529c54`. Both Deployments were
written by the Models and reviewed before play; they are in `classic-1.deploy.json`.
Result: Red by flag captured at ply 405, material 96 to 27.

Console logs (`*.log`) are not committed.
