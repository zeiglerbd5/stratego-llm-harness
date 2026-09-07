# Stratego LLM Benchmark Harness

A harness that makes language models play Stratego against each other in order to
benchmark them. It runs games headlessly, records every move together with the
reasoning behind it, and can export a finished game for visual replay.

## Language

### The contest

**Agent**:
A configured player in a game — a Model plus its prompt, settings, and identity.
_Avoid_: player, bot, AI, opponent

**Model**:
The underlying language model an Agent calls, identified by provider and name
(e.g. `anthropic/claude-opus-5`, `ollama/qwen3:8b`). Never used to mean the
domain model or a game-state object.
_Avoid_: LLM, engine

**Thinking Policy**:
The reasoning level requested of a Model — `off`, `brief`, `standard`, or `deep`
— translated per Model into whatever its provider actually accepts. Part of an
Agent's identity, so one Model at two levels is two Agents.
_Avoid_: reasoning effort, thinking budget, effort level

**Capability Probe**:
A calibration run against a fixed position that measures how a Model behaves —
which Thinking Policies it honors, what it costs, and whether its output stays
valid — before it is allowed to play.
_Avoid_: smoke test, warmup, benchmark

**Game**:
One complete Stratego game between two Agents, from deployment to a terminal result.
_Avoid_: run, episode, session

**Match**:
A fixed set of Games between the same two Agents, used to produce a result that
survives variance.
_Avoid_: series, competition, matchup

**Budget Mode**:
How a Match equalizes thinking budget across its two Agents. `matched` holds
every Agent to one shared thinking-token ceiling; `open` lets each Agent run its
own Thinking Policy under a ceiling set high enough never to bind.
_Avoid_: fairness mode, compute matching, handicap, difficulty

**Tournament**:
A set of Matches across three or more Agents, producing a ranking.
_Avoid_: league, bracket, competition, benchmark run

### Play

**Variant**:
The piece set a Game is played with. **Classic** is 40 pieces a side; **Barrage**
is 8 (Flag, Bomb, Spy, Scout, Miner, Sergeant, General, Marshal). Board and rules
are identical in both.
_Avoid_: mode, ruleset, format

**Deployment**:
A player's starting arrangement of its pieces in its own territory, chosen before
the first move.
_Avoid_: setup, placement, initial position, formation

**Move**:
One relocation of one piece by the Agent to move, whether or not it results in combat.
_Avoid_: turn, ply, action

**Combat**:
The resolution that occurs when a moving piece enters an occupied square, revealing
information to both players.
_Avoid_: attack, strike, battle, capture

**Forfeit**:
A turn where the Agent failed to supply a usable Move and the engine substituted
a random legal one. Distinct from a bad Move: a Forfeit is a failure to play,
not a failure to play well.
_Avoid_: pass, skip, error, timeout

**Observation**:
Everything one Agent is permitted to know at the moment it must move — rendered as
the text it actually receives.
_Avoid_: state, view, prompt, board

**Rationale**:
The Agent's own recorded account of why it chose a Move, written as a required
field of its response. Distinct from a provider's native reasoning trace.
_Avoid_: reasoning, thinking, explanation, chain of thought

**Move Log**:
The record of Moves already played, supplied by the harness inside every
Observation. Continuity of fact — never something an Agent must remember.
_Avoid_: history, past moves

**Scratchpad**:
Notes an Agent carries from one turn to the next, rewritten by the Agent itself
and capped in size. Continuity of intent, and the only thing an Agent authors
that outlives its turn.
_Avoid_: memory, notes, state, context

### What the Agent is given

**Rulebook**:
The document defining legal movement and Combat resolution, which an Agent is
directed to consult when a Move is rejected.
_Avoid_: move guide, rules, reference, manual

**Legal Move List**:
The complete set of Moves available to the Agent this turn, computed by the
engine and included in the Observation.
_Avoid_: options, candidates, available moves

**Threat List**:
The Agent's pieces the enemy could attack on its next Move, and by what.
The defensive mirror of the Legal Move List: the same facts from the other
side of the board.
_Avoid_: danger, attacks, exposure

**Strategy Guide**:
Optional advice on how to play well, appended to the Rulebook only when a run
declares it. Off for benchmark runs; its use is recorded in the Game Record.
_Avoid_: playbook, tips, hints, coaching

**Move Validation**:
The engine's check of a proposed Move against the rules, performed before the
Move is applied and never after.
_Avoid_: rule enforcement, legality check, verification

### Recording and output

**Game Record**:
The complete, replayable log of one Game: Deployment, every Move, Rationale,
Scratchpad, and Combat result, stamped with the Prompt Version it was played under.
_Avoid_: log, history, transcript, trace

**Prompt Version**:
A hash of everything that shapes what a Model is told. Two Games are comparable
only if it matches.
_Avoid_: prompt hash, config version

**Blind Play**:
Running a Game purely programmatically, with no board rendered for a human. The
normal way Games are played.
_Avoid_: headless mode, silent mode

**Replay Export**:
A Game Record rendered as a self-contained HTML page (`render_replay.py`) that
steps through every Move with the Rationale beside the board, and can show the
board as either side actually saw it.
_Avoid_: export, render, playback
