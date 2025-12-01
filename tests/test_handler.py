import logging
import sys

from django_discordo.handler import DiscordWebhookHandler, truncate


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
