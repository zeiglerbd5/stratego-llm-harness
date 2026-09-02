# Thinking budget is equalized by token count, in two declared modes

Language models expose reasoning control in incompatible ways — booleans, effort
strings, token budgets, or nothing at all — so there is no shared setting that
means the same thing to two different Models. Measurement on local models made
this concrete: `qwen3:8b` silently ignored `reasoning_effort: "low"` but honored
`"none"`, and `gpt-oss:20b` produced invalid JSON at `none`, played well at
`low`, and exhausted a 4,000-token budget at `high`. Each Model has a narrow
usable band and the bands do not line up.

We therefore equalize on **thinking tokens actually spent** — the only unit that
is both shared across providers and independent of hardware — and we run Matches
in one of two declared Budget Modes: `matched`, where every Agent is held to one
shared ceiling, and `open`, where each Agent runs its own Thinking Policy under a
per-Agent ceiling derived from its Capability Probe and set high enough never to
bind. Wall clock, cost, and actual thinking tokens are logged every Move so other
normalizations remain computable after the fact.

## Considered Options

- **Matched nominal setting** (every Agent at `standard`): rejected. The probe
  showed the unit is not shared — the same setting is ignored by one Model and
  fatal to another.
- **Matched wall clock or cost**, as in chess time controls: rejected as the
  default because it is not comparable between a local M4 and a cloud endpoint,
  though both are logged so it can be reconstructed.

## Consequences

- A Match's result is only meaningful alongside its Budget Mode; the two modes
  answer different questions ("who reasons more efficiently per token?" versus
  "who plays best unconstrained?") and may disagree.
- An `open` Match whose ceiling ever bound is contaminated — it has silently
  become a `matched` Match at the ceiling. The harness counts ceiling hits and
  marks such a Match rather than reporting a clean-looking number.
- Changing the axis later invalidates previously published Matches.
