from __future__ import annotations

import pytest
import respx
import httpx

from repo_newz.slack import post_summary


WEBHOOK = "https://hooks.slack.com/services/T000/B000/xxxx"

PROSE = {
    "overview_prose": "Active day across two repos.",
    "per_repo_prose": {
        "owner/alpha": "Two commits fixing the auth flow.",
        "owner/beta": "One PR merged by contributor.",
    },
}


@respx.mock
def test_posts_when_webhook_set(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.delenv("SLACK_USER_ID", raising=False)

    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200))
    post_summary(PROSE, "2026-06-12")

    assert route.called
    body = route.calls[0].request.content.decode()
    assert "repo-newz 2026-06-12" in body
    assert "Active day across two repos." in body
    assert "owner/alpha" in body


@respx.mock
def test_includes_url_footer_when_url_given(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.delenv("SLACK_USER_ID", raising=False)

    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200))
    post_summary(PROSE, "2026-06-12", "https://dyn.botwerks.net/repo-newz/repo-activity-20260612/")

    body = route.calls[0].request.content.decode()
    assert "https://dyn.botwerks.net/repo-newz/repo-activity-20260612/" in body


@respx.mock
def test_includes_mention_when_user_id_set(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("SLACK_USER_ID", "U12345678")

    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200))
    post_summary(PROSE, "2026-06-12")

    body = route.calls[0].request.content.decode()
    assert "<@U12345678>" in body


def test_no_op_when_webhook_not_set(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    # no httpx calls should be made; would raise if attempted
    post_summary(PROSE, "2026-06-12")


@respx.mock
def test_logs_warning_on_http_error(monkeypatch, caplog):
    import logging
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.delenv("SLACK_USER_ID", raising=False)

    respx.post(WEBHOOK).mock(return_value=httpx.Response(500))

    with caplog.at_level(logging.WARNING, logger="repo_newz"):
        post_summary(PROSE, "2026-06-12")

    assert any("slack post failed" in r.message for r in caplog.records)


@respx.mock
def test_empty_prose_posts_no_activity(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.delenv("SLACK_USER_ID", raising=False)

    route = respx.post(WEBHOOK).mock(return_value=httpx.Response(200))
    post_summary({}, "2026-06-12")

    body = route.calls[0].request.content.decode()
    assert "no activity in this window." in body
