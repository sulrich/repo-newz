from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from repo_newz.config import Config
from repo_newz.summarize import fill_prose_slots
from pathlib import Path


def _cfg() -> Config:
    return Config(
        repos=["owner/repo"],
        window_hours=24,
        model="claude-sonnet-4-6",
        vault_subpath="{year}/repo-activity-{date}.md",
        anthropic_api_key="sk-ant-test",
        github_token="ghp_test",
        obsidian_home=Path("/tmp/vault"),
    )


_EVENTS = [
    {
        "repo": "owner/repo",
        "kind": "commit",
        "actor": "alice",
        "title": "fix bug",
        "url": "https://github.com/owner/repo/commit/abc1234",
        "at": "2026-05-19T06:00:00Z",
        "number": None,
        "sha": "abc1234",
    }
]

_GOOD_RESPONSE = {
    "overview_prose": "One commit landed.",
    "per_repo_prose": {"owner/repo": "One fix merged by alice."},
}


def _mock_message(text: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


class TestFillProseSlots:
    def test_returns_empty_dict_for_no_events(self):
        result = fill_prose_slots([], _cfg())
        assert result == {}

    def test_correct_request_shape(self):
        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = _mock_message(
                json.dumps(_GOOD_RESPONSE)
            )
            fill_prose_slots(_EVENTS, _cfg())

            call_kwargs = instance.messages.create.call_args.kwargs
            assert call_kwargs["model"] == "claude-sonnet-4-6"
            assert call_kwargs["max_tokens"] == 1024
            system = call_kwargs["system"]
            assert isinstance(system, list)
            assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_returns_parsed_prose_slots(self):
        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = _mock_message(
                json.dumps(_GOOD_RESPONSE)
            )
            result = fill_prose_slots(_EVENTS, _cfg())

        assert result["overview_prose"] == "One commit landed."
        assert "contributor_prose" not in result
        assert result["per_repo_prose"]["owner/repo"] == "One fix merged by alice."

    def test_auth_error_returns_empty_dict(self):
        import anthropic as ant

        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.side_effect = ant.AuthenticationError(
                message="bad key", response=MagicMock(), body={}
            )
            result = fill_prose_slots(_EVENTS, _cfg())
        assert result == {}

    def test_rate_limit_returns_empty_dict(self):
        import anthropic as ant

        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.side_effect = ant.RateLimitError(
                message="rate limit", response=MagicMock(), body={}
            )
            result = fill_prose_slots(_EVENTS, _cfg())
        assert result == {}

    def test_timeout_returns_empty_dict(self):
        import anthropic as ant

        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.side_effect = ant.APITimeoutError(
                request=MagicMock()
            )
            result = fill_prose_slots(_EVENTS, _cfg())
        assert result == {}

    def test_malformed_json_returns_empty_dict(self):
        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = _mock_message("not valid json {{{")
            result = fill_prose_slots(_EVENTS, _cfg())
        assert result == {}

    def test_missing_per_repo_key_returns_empty_string_no_key_error(self):
        response = {
            "overview_prose": "some overview",
            # per_repo_prose missing entirely
        }
        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = _mock_message(json.dumps(response))
            result = fill_prose_slots(_EVENTS, _cfg())
        # Should not KeyError; per_repo_prose absent means render gets empty dict
        assert result["per_repo_prose"] == {}

    def test_unknown_repo_in_per_repo_prose_no_key_error(self):
        response = {
            "overview_prose": "overview",
            "per_repo_prose": {"owner/repo": "summary", "extra/unknown": "ignored"},
        }
        with patch("repo_newz.summarize.anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = _mock_message(json.dumps(response))
            result = fill_prose_slots(_EVENTS, _cfg())
        # Render will just miss it via .get(); no crash here either
        assert "extra/unknown" in result["per_repo_prose"]
