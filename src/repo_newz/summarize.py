from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from repo_newz.config import Config

log = logging.getLogger("repo_newz")

_SYSTEM_PROMPT = """\
you summarize github repository activity into concise, factual prose for a
developer's daily notes. you receive a JSON object describing events from one
or more repositories over a recent time window.

rules:
- only mention repos, users, and events that appear in the supplied JSON.
- do not invent, embellish, or hallucinate any names, numbers, or details.
- be terse. use short declarative sentences. no preamble or sign-off.
- return ONLY a JSON object with exactly two keys:
    "overview_prose"  - 2-4 sentences summarising the overall activity across all repos
    "per_repo_prose"  - object mapping "owner/repo" to a 1-3 sentence summary of that
                        repo's activity; mention the key contributors by login
- if there is no activity, set overview_prose to "no activity in this window."
  and leave per_repo_prose as an empty object.
"""


def fill_prose_slots(events: list[dict], cfg: "Config") -> dict:
    """call sonnet to fill prose slots. returns empty dict on any failure."""
    if not events:
        return {}

    payload = json.dumps({"events": events}, default=str)
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    try:
        response = client.messages.create(
            model=cfg.model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Summarise this GitHub activity:\n\n{payload}",
                }
            ],
        )
        raw = response.content[0].text.strip()
        return _parse_response(raw)
    except anthropic.AuthenticationError as exc:
        log.warning("anthropic auth error - skipping prose: %s", exc)
    except anthropic.RateLimitError as exc:
        log.warning("anthropic rate limit - skipping prose: %s", exc)
    except anthropic.APITimeoutError as exc:
        log.warning("anthropic timeout - skipping prose: %s", exc)
    except anthropic.APIError as exc:
        log.warning("anthropic api error - skipping prose: %s", exc)
        _log_raw_payload(payload)
    except Exception as exc:
        log.warning("unexpected error calling anthropic - skipping prose: %s", exc)

    return {}


def _parse_response(raw: str) -> dict:
    # strip markdown code fences the model sometimes wraps around JSON
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]  # drop opening fence line
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("anthropic returned non-JSON - skipping prose; raw=%r", raw[:200])
        return {}

    if not isinstance(data, dict):
        log.warning("anthropic response is not a JSON object - skipping prose")
        return {}

    per_repo = data.get("per_repo_prose", {})
    if not isinstance(per_repo, dict):
        per_repo = {}

    return {
        "overview_prose": str(data.get("overview_prose", "")),
        "per_repo_prose": {k: str(v) for k, v in per_repo.items()},
    }


def _log_raw_payload(payload: str) -> None:
    log.debug("raw anthropic payload: %s", payload[:500])
