# Stratego LLM Benchmark Harness

Makes language models play Stratego against each other, headlessly, and records
every Move with the reasoning behind it. Cloud models via OpenRouter, local
models via Ollama, one OpenAI-compatible adapter for both. Stdlib only.

See `CONTEXT.md` for the vocabulary and `docs/adr/` for the decisions.

## Run

```bash
# one Game, local models, library openings (default)
python3 run_game.py --red gpt-oss:20b --blue llama3:latest --variant barrage

# a Match: paired Games, colours swapped, one pair per library opening
python3 run_match.py --a gpt-oss:20b --b gpt-oss:20b --pairs 3

# a cloud model through OpenRouter (OPENROUTER_API_KEY in the environment)
python3 run_game.py --red openrouter/anthropic/claude-sonnet-4.6 --blue gpt-oss:20b \
    --deployment model --thinking standard

# metrics and material adjudication over any Game Record
python3 -m stratego.metrics records/*.jsonl
```

Key switches: `--variant barrage|classic`, `--thinking off|brief|standard|deep`,
`--move-assist` / `--threat-assist none|hints|full`, `--deployment model|library`,
`--strategy-guide` (contaminates a benchmark; recorded when used).

## Layout

```
stratego/rules.py         ranks, variants, geometry, combat, material values
stratego/game.py          state, Move Validation, repetition, termination
stratego/observation.py   what the Agent sees each turn
stratego/rulebook.md      the rules as the Agent receives them
stratego/agent.py         retries, failure taxonomy, Rationale-first schema
stratego/adapter.py       OpenAI-compatible client, self-calibrating
stratego/deployments.py   Deployment Library
stratego/loop.py          one Game -> Game Record (JSONL)
stratego/match.py         paired Games, resume, aggregation
stratego/metrics.py       per-side metrics, material adjudication
records/                  Game Records and Match results
```
