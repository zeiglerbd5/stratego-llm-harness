"""One OpenAI-compatible client for every Model.

OpenRouter and Ollama both return the native reasoning trace on
`choices[].message.reasoning`, so a single transport serves cloud and local.
Residency control is the one thing that needs Ollama's native API.
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


@dataclass
class Completion:
    content: str
    reasoning: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float

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
    body: dict = {
        "model": profile.name,
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
    return Completion(
        content=msg.get("content") or "",
        reasoning=msg.get("reasoning") or "",
        finish_reason=choice.get("finish_reason") or "",
        prompt_tokens=usage.get("prompt_tokens") or 0,
        completion_tokens=usage.get("completion_tokens") or 0,
        seconds=round(dt, 2),
    )


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
    if "11434" not in profile.base_url:
        return
    root = profile.base_url.rstrip("/").removesuffix("/v1")
    req = urllib.request.Request(
        root + "/api/generate",
        data=json.dumps({"model": profile.name, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass
