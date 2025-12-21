import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from django_discordo.handler import (
    ACTION_LOG_LEVEL,
    COLORS,
    EMOJIS,
    SUCCESS_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    DiscordWebhookHandler,
    truncate,
)

try:
    import django  # noqa: F401

    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False


def test_short_log():
    handler = DiscordWebhookHandler()
    factory = logging.getLogRecordFactory()
    msg = "You. This is a warning. Isn't that bad?"
    args = ()
    try:
        raise ValueError("HEY! Watch where you're going!")
    except ValueError:
        record = factory(
            __name__, logging.WARNING, "test_logger", 11, msg, args, sys.exc_info()
        )
        payload = handler.get_payload(record)
        assert len(payload["embeds"][0]["description"]) <= 2000
        resp = handler.post_response(record)
    if handler.get_url(record) is not None:
        resp = handler.post_response(record)
        assert resp is not None
        assert resp.status_code <= 299


def test_truncate():
    assert len(truncate("aoeu" * 1000, 800)) < 820


class TestTruncate:
    def test_string_below_limit(self):
        s = "short string"
        assert truncate(s, 100) == s

    def test_string_at_exact_limit(self):
        s = "a" * 100
        assert truncate(s, 100) == s

    def test_string_above_limit(self):
        s = "a" * 200
        result = truncate(s, 100)
        assert len(result) < 200
        assert "..." in result

    def test_empty_string(self):
        assert truncate("", 100) == ""

    def test_default_limit(self):
        s = "x" * 1000
        result = truncate(s)
        assert len(result) < 1000
        assert "..." in result


def test_long_log():
    handler = DiscordWebhookHandler()
    factory = logging.getLogRecordFactory()
    msg = "Whoa. Another warning. But this one is really long!\n" * 1000
    args = ()
    try:
        raise ValueError("OH NO. Your code is playing possum. WHY?\n" * 500)
    except ValueError:
        record = factory(
            __name__, logging.WARNING, "test_logger", 99, msg, args, sys.exc_info()
        )
        payload = handler.get_payload(record)
        assert len(payload["embeds"][0]["description"]) <= 2000
        if handler.get_url(record) is not None:
            resp = handler.post_response(record)
            assert resp is not None
            assert resp.status_code <= 299


def make_record(
    level: int = logging.WARNING,
    msg: str = "Test message",
    exc_info=None,
    **extras,
):
    """Helper to create log records for testing."""
    factory = logging.getLogRecordFactory()
    record = factory(__name__, level, "test_file.py", 42, msg, (), exc_info)
    for key, value in extras.items():
        setattr(record, key, value)
    return record


class TestLogLevels:
    @pytest.mark.parametrize(
        "level,level_name",
        [
            (logging.DEBUG, "debug"),
            (logging.INFO, "info"),
            (logging.WARNING, "warning"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "critical"),
            (VERBOSE_LOG_LEVEL, "verbose"),
            (SUCCESS_LOG_LEVEL, "success"),
            (ACTION_LOG_LEVEL, "action"),
        ],
    )
    def test_level_colors(self, level, level_name):
        handler = DiscordWebhookHandler()
        record = make_record(level=level)
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert embed["color"] == COLORS[level_name]

    @pytest.mark.parametrize(
        "level,level_name",
        [
            (logging.DEBUG, "debug"),
            (logging.INFO, "info"),
            (logging.WARNING, "warning"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "critical"),
            (VERBOSE_LOG_LEVEL, "verbose"),
            (SUCCESS_LOG_LEVEL, "success"),
            (ACTION_LOG_LEVEL, "action"),
        ],
    )
    def test_level_emojis(self, level, level_name):
        handler = DiscordWebhookHandler()
        record = make_record(level=level)
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert EMOJIS[level_name] in embed["title"]


class TestPayloadStructure:
    def test_single_line_message_in_title(self):
        handler = DiscordWebhookHandler()
        record = make_record(msg="Single line message")
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert "Single line message" in embed["title"]
        assert "description" not in embed or "MESSAGE" not in embed.get(
            "description", ""
        )

    def test_multiline_message_split(self):
        handler = DiscordWebhookHandler()
        record = make_record(msg="First line\nSecond line\nThird line")
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert "First line" in embed["title"]
        assert "Second line" in embed["description"]

    def test_status_code_formatting(self):
        handler = DiscordWebhookHandler()
        record = make_record(status_code=500)
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        status_field = next(f for f in embed["fields"] if f["name"] == "Status")
        assert "**500**" in status_field["value"]

    def test_no_status_code(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        status_field = next(f for f in embed["fields"] if f["name"] == "Status")
        assert status_field["value"] == "None"

    def test_exception_in_description(self):
        handler = DiscordWebhookHandler()
        try:
            raise ValueError("Test exception")
        except ValueError:
            record = make_record(exc_info=sys.exc_info())
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert "EXCEPTION" in embed["description"]
        assert "ValueError" in embed["description"]

    def test_no_exception(self):
        handler = DiscordWebhookHandler()
        record = make_record(msg="No exception here")
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        assert "description" not in embed or "EXCEPTION" not in embed.get(
            "description", ""
        )

    def test_required_fields_present(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        field_names = {f["name"] for f in embed["fields"]}
        assert field_names == {"Status", "Level", "Scope", "Module", "User", "Filename"}

    def test_long_message_truncated_in_title(self):
        handler = DiscordWebhookHandler()
        long_msg = "x" * 300
        record = make_record(msg=long_msg)
        payload = handler.get_payload(record)
        embed = payload["embeds"][0]
        # Title should be truncated to 200 chars + emoji
        assert len(embed["title"]) < 250


class TestGetUrl:
    def test_no_url_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "django_discordo.handler.settings", create=True
            ) as mock_settings:
                del mock_settings.DISCORD_WEBHOOK_URL
                del mock_settings.DISCORD_WEBHOOK_URLS
                # get_url will try to access settings attributes
                mock_settings.configure_mock(
                    **{"DISCORD_WEBHOOK_URL": None, "DISCORD_WEBHOOK_URLS": None}
                )
                type(mock_settings).DISCORD_WEBHOOK_URL = property(
                    lambda self: (_ for _ in ()).throw(AttributeError())
                )
                type(mock_settings).DISCORD_WEBHOOK_URLS = property(
                    lambda self: (_ for _ in ()).throw(AttributeError())
                )

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django not installed")
    def test_simple_string_url(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DISCORD_WEBHOOK_URL = "https://discord.com/webhook/123"
            mock_settings.configure_mock(spec=["DISCORD_WEBHOOK_URL"])
            url = handler.get_url(record)
            assert url == "https://discord.com/webhook/123"

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django not installed")
    def test_dict_url_with_level(self):
        handler = DiscordWebhookHandler()
        record = make_record(level=logging.ERROR)
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DISCORD_WEBHOOK_URLS = {
                "ERROR": "https://discord.com/webhook/errors",
                "DEFAULT": "https://discord.com/webhook/default",
            }
            url = handler.get_url(record)
            assert url == "https://discord.com/webhook/errors"

    @pytest.mark.skipif(not DJANGO_AVAILABLE, reason="Django not installed")
    def test_dict_url_fallback_to_default(self):
        handler = DiscordWebhookHandler()
        record = make_record(level=logging.INFO)
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DISCORD_WEBHOOK_URLS = {
                "ERROR": "https://discord.com/webhook/errors",
                "DEFAULT": "https://discord.com/webhook/default",
            }
            url = handler.get_url(record)
            assert url == "https://discord.com/webhook/default"

    def test_env_var_fallback(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        env = {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/env"}
        with patch.dict(os.environ, env, clear=True):
            url = handler.get_url(record)
            assert url == "https://discord.com/webhook/env"

    def test_env_var_level_specific(self):
        handler = DiscordWebhookHandler()
        record = make_record(level=logging.ERROR)
        env = {
            "DISCORD_WEBHOOK_URL": "https://discord.com/webhook/default",
            "DISCORD_WEBHOOK_URL_ERROR": "https://discord.com/webhook/errors",
        }
        with patch.dict(os.environ, env, clear=True):
            url = handler.get_url(record)
            assert url == "https://discord.com/webhook/errors"


class TestPostResponse:
    def test_returns_none_when_no_url(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        with patch.object(handler, "get_url", return_value=None):
            result = handler.post_response(record)
            assert result is None

    def test_posts_to_url(self):
        handler = DiscordWebhookHandler()
        record = make_record()
        with patch.object(handler, "get_url", return_value="https://example.com"):
            with patch("django_discordo.handler.requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                result = handler.post_response(record)
                assert result is not None
                mock_post.assert_called_once()


class TestCustomLogLevels:
    def test_verbose_level_registered(self):
        assert logging.getLevelName(VERBOSE_LOG_LEVEL) == "VERBOSE"

    def test_success_level_registered(self):
        assert logging.getLevelName(SUCCESS_LOG_LEVEL) == "SUCCESS"

    def test_action_level_registered(self):
        assert logging.getLevelName(ACTION_LOG_LEVEL) == "ACTION"

    def test_custom_level_values(self):
        assert VERBOSE_LOG_LEVEL == 15
        assert SUCCESS_LOG_LEVEL == 25
        assert ACTION_LOG_LEVEL == 35
