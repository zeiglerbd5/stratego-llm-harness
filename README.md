# Stratego LLM Benchmark Harness

Language models play Stratego against each other, headlessly, and every move
is recorded with the model's own reasoning beside it. Cloud models through the
Claude API or OpenRouter, local models through Ollama, all through one adapter.
Python 3.10+, standard library only, no dependencies.

Stratego is a good benchmark for this because it is a game of hidden
information: a model has to reason about what it has seen, what it has been
told, and what it can infer, and the record shows whether it did.

## What it found so far

| match | thinking | games | result |
|---|---|---|---|
| gpt-oss:20b vs itself | brief | 6 | 3 draws, 3 decided on material, 4 illegal moves |
| gpt-oss:20b vs itself | standard | 6 | 12x the thinking, 14 illegal moves, 6 Marshals thrown away |
| Sonnet 5 vs gpt-oss:20b | brief | 6 | 2-2-2 |
| Sonnet 5 vs gpt-oss:20b | standard | 2 | Sonnet 2-0, both by capturing every mobile piece |
| Sonnet 5 vs gpt-5.6-terra | standard | 6 | Terra 5-1, every game decided on the board |
| Sonnet 5 vs gpt-5.6-terra, Classic | standard | 1 | Sonnet by flag capture at ply 405, from setups the models wrote |

Three things the records show:

- **A 20B local model is the floor, not a prompt problem.** Every rejected move
  and every blunder traced back had the correct fact in the Observation. More
  thinking made gpt-oss:20b worse: it attacked pieces it had been told were
  Marshals, walked Scouts into Bombs, and picked moves off a list it was told
  was complete.
- **Frontier models play the game, and use exactly the facts supplied.** Their
  rationales read like a player's: "moved 21 times, so it must be their
  Sergeant"; "a1/a2 never moved, they're the Bomb/Flag pair". The Classic game
  turned on a Spy trap: a Captain left beside the Spy, the enemy Marshal took
  it, the Spy took the Marshal.
- **The harness's incentives show through a model that follows instructions.**
  Under a 60-ply cap with material adjudication and a line in the rulebook about
  protecting material, Sonnet 5 spent six games retreating. Removing the line,
  lengthening the cap, and listing threats after the legal moves changed that.

The Game Records for all of it are in [`records/`](records/README.md).

## Quick start

```bash
# tests, no network
python3 -m unittest discover -s tests

# a local game (Ollama running, model pulled)
python3 run_game.py --red gpt-oss:20b --blue gpt-oss:20b --variant barrage --thinking brief

# a Claude model through the Claude API (ANTHROPIC_API_KEY in the environment)
# against an OpenAI model through OpenRouter (OPENROUTER_API_KEY)
python3 run_match.py --a anthropic/claude-sonnet-5 --b openrouter/openai/gpt-5.6-terra \
    --pairs 3 --thinking standard

# let the models write their own setups, review them, then play a full 40-piece game
python3 run_deploy.py --red anthropic/claude-sonnet-5 --blue openrouter/openai/gpt-5.6-terra \
    --variant classic --out records/my-game.deploy.json
python3 run_game.py --red anthropic/claude-sonnet-5 --blue openrouter/openai/gpt-5.6-terra \
    --variant classic --deployment file --deployment-file records/my-game.deploy.json \
    --move-cap 500 --out records/my-game.jsonl

# metrics, and a replay page you can open in a browser
python3 -m stratego.metrics records/my-game.jsonl
python3 render_replay.py records/my-game.jsonl
```

Model names: `gpt-oss:20b` is local Ollama, `anthropic/<model>` is the Claude
API, `openrouter/<vendor>/<model>` is OpenRouter. Local models are served
through a derived 32k-context variant (`gpt-oss:20b-ctx32k`, created on first
use), because Ollama's 4k default truncates any real reasoning trace.

Switches that matter: `--thinking off|brief|standard|deep` (mapped per
provider to its effort setting), `--max-tokens` (the output ceiling; a game in
which it binds is marked, since a thinking model that ran out of room did not
play), `--move-cap`, `--variant barrage|classic`, `--deployment
library|model|file|random`, and `--strategy-guide`, which contaminates a
benchmark and is recorded when used.

## How a game works

Each turn the model receives an Observation: the board, its own pieces, every
enemy piece with what is publicly known about it (revealed rank, moves made,
whether it has moved like a Scout), material, the move log, its own notes from
last turn, the complete list of legal moves, and the pieces the enemy could
attack next. Bookkeeping is the harness's job; judgment is the model's. It
answers with a rationale, a move, and notes to itself, as JSON.

The engine validates the move before applying it. A rejected move is returned
with the rule it broke and retried; three failures forfeit the turn to a random
legal move. Every attempt is recorded with its kind, so the record can say
whether a model misread the board or broke a rule. Thinking tokens are counted
from the provider's own numbers or its tokenizer, never estimated silently.

A Match plays each position twice with the models swapped between the seats,
so colour and setup luck cancel. Red's opening and Blue's differ, because the
same setup on both sides is a mirror and the Marshals simply walk into each
other.

## Layout

```
stratego/rules.py            ranks, variants, board, combat, material values
stratego/game.py             state, move validation with typed rejections, repetition, termination
stratego/observation.py      what the model sees each turn
stratego/rulebook.md         the rules as the model receives them
stratego/agent.py            the retry loop, failure taxonomy, rationale-first schema
stratego/adapter.py          one client for OpenRouter/Ollama, one for the Claude API; token accounting
stratego/deployments.py      the opening library and non-mirrored pairing
stratego/loop.py             one game -> one Game Record (JSONL)
stratego/match.py            paired games, resume, aggregation
stratego/metrics.py          per-side metrics and material adjudication
stratego/replay_template.html  the replay page
run_game.py  run_match.py  run_deploy.py  render_replay.py
records/                     Game Records and match summaries, indexed in records/README.md
tests/                       stdlib unittest; runs in CI
docs/adr/                    decisions, starting with how thinking budgets are equalised
CONTEXT.md                   the vocabulary used throughout
```

## Adding a model

A cloud model that speaks the OpenAI chat shape works through OpenRouter with
no code. A Claude model works through the `anthropic/` prefix. Anything else
needs a `ModelProfile` and, if its wire format differs, a branch in
`stratego/adapter.py` that returns the same `Completion`, including how its
thinking tokens are counted.

Before trusting a new model in a benchmark, run a short game and read the
record: which thinking settings it honours, whether it hits the output
ceiling, and whether its JSON stays valid are all visible there.

## License

MIT. See [LICENSE](LICENSE).
