"""One OpenAI-compatible client for every Model.

OpenRouter and Ollama both return the native reasoning trace on
`choices[].message.reasoning`, so a single transport serves cloud and local.
Ollama's native API is needed for three things only: residency control,
counting the tokens in that trace (see `_thinking_tokens`), and giving a local
Model a context window big enough to think in (see `ensure_context`).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# Thinking Policy -> provider effort string. Per-Model overrides come from the
# Capability Probe, because these mappings are not reliably honored: qwen3:8b
# ignores "low" but honors "none".
DEFAULT_EFFORT = {"off": "none", "brief": "low", "standard": "medium", "deep": "high"}


@dataclass
class ModelProfile:
    """What the Capability Probe learned about a Model."""
    name: str
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str | None = None
    effort_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_EFFORT))
    honors_effort: bool = True
    supports_thinking: bool = True         # some Models 400 if the field is sent
    max_tokens: int = 4000
    ceiling_tokens: int | None = None      # open-mode, non-binding
    supports_schema: bool = True
    # Local only; cloud endpoints manage their own context. Ollama serves every
    # Model in a 4,096-token window by default, and /v1 has no way to widen it:
    # a ~1,500-token prompt then leaves ~2,600 tokens for thinking AND answer,
    # which gpt-oss:20b at `standard` exhausts on its first Move, every time.
    context_tokens: int | None = 32768
    served_name: str | None = None         # the derived Model actually asked for


@dataclass
class Completion:
    content: str
    reasoning: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int              # the provider's own count, recorded as-is
    seconds: float
    thinking_tokens: int = 0            # tokens in the native reasoning trace
    thinking_tokens_source: str = "none"    # provider | tokenizer | estimate | none
    context_bound: bool = False         # cut off by the context window, not max_tokens

    @property
    def budget_exhausted(self) -> bool:
        """A thinking model that spent its budget and returned nothing.

        Not an illegal move, and must never be scored as one.
        """
        return self.finish_reason == "length" and not self.content.strip()


class AdapterError(RuntimeError):
    pass


def complete(profile: ModelProfile, messages: list[dict], schema: dict | None,
             thinking: str = "standard", max_tokens: int | None = None,
             timeout: int = 600) -> Completion:
    ensure_context(profile)
    body: dict = {
        "model": _api_name(profile),
        "messages": messages,
        "max_tokens": max_tokens or profile.max_tokens,
        "temperature": 0.3,
    }
    if schema and profile.supports_schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "strict": True, "schema": schema},
        }
    effort = profile.effort_map.get(thinking)
    if effort and profile.honors_effort and profile.supports_thinking:
        body["reasoning_effort"] = effort

    headers = {"Content-Type": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"

    req = urllib.request.Request(
        profile.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(), headers=headers)
    t0 = time.time()
    try:
        raw = _send(req, timeout, profile.name)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300]
        # Self-calibration: some Models reject the thinking field outright
        # rather than ignoring it. Learn it once, then never send it again.
        if e.code == 400 and b"does not support thinking" in detail \
                and profile.supports_thinking:
            profile.supports_thinking = False
            return complete(profile, messages, schema, thinking, max_tokens, timeout)
        raise AdapterError(f"{profile.name}: HTTP {e.code} {detail!r}") from e
    except Exception as e:
        raise AdapterError(f"{profile.name}: {e}") from e
    dt = time.time() - t0

    choice = raw["choices"][0]
    msg = choice["message"]
    usage = raw.get("usage") or {}
    comp = Completion(
        content=msg.get("content") or "",
        reasoning=msg.get("reasoning") or "",
        finish_reason=choice.get("finish_reason") or "",
        prompt_tokens=usage.get("prompt_tokens") or 0,
        completion_tokens=usage.get("completion_tokens") or 0,
        seconds=round(dt, 2),           # the Model's time only; counting is excluded
    )
    comp.thinking_tokens, comp.thinking_tokens_source = \
        _thinking_tokens(profile, usage, comp.reasoning)
    if comp.finish_reason == "length" and profile.context_tokens \
            and _ollama_root(profile) is not None:
        # A budget hit is the Model's; a context hit is the harness's. Under
        # the schema completion_tokens may omit the trace, so take the larger.
        used = comp.prompt_tokens + max(comp.completion_tokens, comp.thinking_tokens)
        comp.context_bound = used >= profile.context_tokens - 32
    return comp


def ensure_context(profile: ModelProfile) -> None:
    """Serve a local Model through a derived variant with `context_tokens` of
    context. Ollama's /v1 ignores `options.num_ctx` (tested), so the only
    per-Model control is a PARAMETER baked into a derived Model. /api/create
    with `from` shares the weights and takes ~0.1 s; the name records what
    was served, e.g. `gpt-oss:20b-ctx32k`. Cloud endpoints are untouched."""
    root = _ollama_root(profile)
    if root is None or not profile.context_tokens or profile.served_name:
        return
    derived = f"{profile.name}-ctx{profile.context_tokens // 1024}k"
    req = urllib.request.Request(
        root + "/api/create",
        data=json.dumps({"model": derived, "from": profile.name, "stream": False,
                         "parameters": {"num_ctx": profile.context_tokens}}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        raw = json.loads(urllib.request.urlopen(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        raise AdapterError(f"{profile.name}: could not derive {derived}: "
                           f"HTTP {e.code} {e.read()[:300]!r}") from e
    except Exception as e:
        raise AdapterError(f"{profile.name}: could not derive {derived}: {e}") from e
    if raw.get("status") != "success":
        raise AdapterError(f"{profile.name}: could not derive {derived}: {raw!r}")
    profile.served_name = derived


def _api_name(profile: ModelProfile) -> str:
    return profile.served_name or profile.name


def _thinking_tokens(profile: ModelProfile, usage: dict,
                     reasoning: str) -> tuple[int, str]:
    """Tokens spent on the native reasoning trace, and where the number came from.

    Provider counters cannot be trusted for this. OpenRouter reports
    `completion_tokens_details.reasoning_tokens` for Models that expose it.
    Ollama's `completion_tokens` includes the trace for a plain request but
    drops it entirely under strict `response_format` (measured on gpt-oss:20b:
    216 reported for a Move whose visible JSON alone was ~214 tokens, with a
    444-character trace uncounted). So on Ollama the trace is tokenized
    separately, exactly, by `count_tokens`. The estimate is a last resort and
    is labelled as such: ADR-0001 equalizes on this number.
    """
    details = usage.get("completion_tokens_details") or {}
    if details.get("reasoning_tokens"):
        return int(details["reasoning_tokens"]), "provider"
    if not reasoning.strip():
        return 0, "none"
    n = count_tokens(profile, reasoning)
    if n is not None:
        return n, "tokenizer"
    # Reasoning text is dense (square names, arithmetic): measured ~2.9
    # characters per token on gpt-oss:20b, against ~4 for prose.
    return round(len(reasoning) / 3), "estimate"


def count_tokens(profile: ModelProfile, text: str) -> int | None:
    """Exact token count of `text` under a local Model's own tokenizer, or
    None when unavailable (cloud endpoint, or the call failed).

    Ollama has no tokenize endpoint. A raw generate of one token reports
    `prompt_eval_count`, which is the full count even when the prefix is
    cached (measured stable across repeats) and costs ~0.25 s when warm.
    """
    root = _ollama_root(profile)
    if root is None or not text:
        return None
    req = urllib.request.Request(
        root + "/api/generate",
        data=json.dumps({"model": _api_name(profile), "prompt": text, "raw": True,
                         "stream": False, "options": {"num_predict": 1}}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        raw = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except Exception:
        return None
    n = raw.get("prompt_eval_count")
    return int(n) if n else None


def _ollama_root(profile: ModelProfile) -> str | None:
    """The native-API base for a local Model, or None for a cloud endpoint."""
    if "11434" not in profile.base_url:
        return None
    return profile.base_url.rstrip("/").removesuffix("/v1")


CONNECT_RETRIES = 6          # a restarting local server needs a few seconds
CONNECT_BACKOFF = 5.0        # seconds, doubled each attempt (5,10,20,40,80)


def _send(req: urllib.request.Request, timeout: int, name: str) -> dict:
    """POST with retry on connection-level failures only. HTTP errors (a 4xx
    for a bad request) propagate immediately - retrying those cannot help."""
    delay = CONNECT_BACKOFF
    for attempt in range(CONNECT_RETRIES):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt == CONNECT_RETRIES - 1:
                raise AdapterError(f"{name}: unreachable after "
                                   f"{CONNECT_RETRIES} attempts: {e}") from e
            time.sleep(delay)
            delay *= 2
    raise AdapterError(f"{name}: unreachable")


def unload(profile: ModelProfile) -> None:
    """Free a local Model's RAM. keep_alive is absent from the /v1 schema."""
    root = _ollama_root(profile)
    if root is None:
        return
    req = urllib.request.Request(
        root + "/api/generate",
        data=json.dumps({"model": _api_name(profile), "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass
