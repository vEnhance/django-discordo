import logging
import os
import pprint
import queue
import sys
import threading
import time
import traceback
from collections import OrderedDict
from typing import Any, TypedDict

import requests

VERBOSE_LOG_LEVEL = 15
SUCCESS_LOG_LEVEL = 25
ACTION_LOG_LEVEL = 35
logging.addLevelName(VERBOSE_LOG_LEVEL, "VERBOSE")
logging.addLevelName(SUCCESS_LOG_LEVEL, "SUCCESS")
logging.addLevelName(ACTION_LOG_LEVEL, "ACTION")

COLORS = {
    "default": 2040357,
    "error": 14362664,
    "critical": 14362664,
    "warning": 16497928,
    "info": 2196944,
    "verbose": 6559689,
    "debug": 2196944,
    "success": 2210373,
    "action": 17663,
}
EMOJIS = {
    "default": ":loudspeaker:",
    "error": ":x:",
    "critical": ":skull_crossbones:",
    "warning": ":warning:",
    "info": ":bell:",
    "verbose": ":mega:",
    "debug": ":microscope:",
    "success": ":rocket:",
    "action": ":factory_worker:",
}


def truncate(s: str, n: int = 800) -> str:
    if len(s) > n:
        return s[: n // 2] + "\n...\n" + s[-n // 2 :]
    return s


class Payload(TypedDict):
    embeds: list[dict[str, Any]]


#: connect timeout / read timeout, in seconds
DEFAULT_TIMEOUT = (3.05, 10.0)


class DiscordWebhookHandler(logging.Handler):
    """Logging handler that sends records to a Discord webhook.

    By default the HTTP request happens on a background worker thread, so
    emitting a log record never blocks the caller no matter how Discord is
    feeling. Pass ``blocking=True`` to post inline instead.
    """

    def __init__(
        self,
        level: int | str = logging.NOTSET,
        blocking: bool = False,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
        queue_size: int = 1000,
        shutdown_timeout: float = 5.0,
    ) -> None:
        super().__init__(level=level)
        self.blocking = blocking
        self.timeout = timeout
        self.queue_size = queue_size
        self.shutdown_timeout = shutdown_timeout
        self.dropped = 0

        # guards worker startup; deliberately not the handler's own lock
        self._worker_lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, Payload] | None] | None = None
        self._thread: threading.Thread | None = None
        self._session: requests.Session | None = None
        self._pid: int | None = None
        self._closed = False

    def get_payload(self, record: logging.LogRecord) -> Payload:
        self.format(record)
        level = record.levelname.lower().strip()
        emoji = EMOJIS.get(level, ":question:")
        color = COLORS.get(level, 0xAAAAAA)

        # this only works in django
        try:
            user = record.request.user.first_name + " " + record.request.user.last_name  # type: ignore
        except AttributeError:
            user = "anonymous"
        s = str(getattr(record, "status_code", ""))
        if s:
            s = "**" + s + "**"
        else:
            s = "None"

        dirname, filename = os.path.split(record.pathname)
        lastdirname = os.path.basename(dirname)

        resolver_match = getattr(
            getattr(record, "request", None), "resolver_match", None
        )
        module = (
            getattr(resolver_match, "_func_path", None)
            or getattr(resolver_match, "view_name", None)
            or record.module
        )

        fields = [
            {
                "name": "Status",
                "value": s,
                "inline": True,
            },
            {
                "name": "Level",
                "value": record.levelname.title(),
                "inline": True,
            },
            {
                "name": "Scope",
                "value": f"`{record.name}`",
                "inline": True,
            },
            {
                "name": "Module",
                "value": f"`{module}`",
                "inline": True,
            },
            {
                "name": "User",
                "value": user,
                "inline": True,
            },
            {
                "name": "Filename",
                "value": f"{record.lineno}:`{os.path.join(lastdirname, filename)}`",
                "inline": True,
            },
        ]

        description_parts = OrderedDict()

        # if the message is short (< 1 line), we set it as the title
        if "\n" not in record.message:
            title = f"{emoji} {record.message[:200]}"
        # otherwise, set the first line as title and include the rest in description
        else:
            i = record.message.index("\n")
            title = f"{emoji} {record.message[:i]}"
            msg_key = ":green_heart: MESSAGE :green_heart:"
            description_parts[msg_key] = truncate(record.message[i + 1 :])

        # if exc_text nonempty, add that to description
        if record.exc_text is not None:
            # always truncate r.exc_text to at most 600 chars since it's fking long
            msg_key = ":yellow_heart: EXCEPTION :yellow_heart:"
            description_parts[msg_key] = (
                "```" + "\n" + truncate(record.exc_text) + "\n" + "```"
            )

        # if request data is there, include that too
        if hasattr(record, "request"):
            request = record.request
            s = ""
            s += f"> **Method** {request.method}\n"
            s += f"> **Path** `{request.path}`\n"
            s += f"> **Content Type** {request.content_type}\n"
            s += f"> **Agent** {request.headers.get('User-Agent', 'Unknown')}\n"
            if request.user.is_authenticated:
                s += f"> **User** {getattr(request.user, 'username', 'wtf')}\n"
            try:
                post, files = request.POST, request.FILES
            except Exception as e:  # noqa: BLE001
                s += f"> **Body** unreadable ({type(e).__name__}: {e})\n"
                post, files = None, None

            if post is not None and request.method == "POST":
                # redact the token for evan's personal api
                d: dict[str, Any] = {}
                for k, v in post.items():
                    if "token" in k.lower() or "password" in k.lower():
                        d[k] = "<redacted>"
                    else:
                        d[k] = v
                s += r"POST data" + "\n"
                s += r"```" + "\n"
                pp = pprint.PrettyPrinter(indent=2)
                s += pp.pformat(d)
                s += r"```"
            if files:
                s += "Files included\n"
                for name, fileobj in files.items():
                    s += f"> `{name}` ({fileobj.size} bytes, {fileobj.content_type})\n"

            chars_remaining = 1800 - sum(len(v) for v in description_parts.values())
            description_parts[":blue_heart: REQUEST :blue_heart:"] = s[:chars_remaining]

        embed = {"title": title, "color": color, "fields": fields}

        desc = ""
        for k, v in description_parts.items():
            desc += k + "\n" + v.strip() + "\n"
        if desc:
            embed["description"] = desc

        data: Payload = {
            "embeds": [embed],
        }
        return data

    def _url_from_settings(self, record: logging.LogRecord) -> str | None:
        """Look up the webhook URL in Django settings, if that's available."""
        try:
            from django.conf import settings

            # Check for dictionary-style configuration
            if hasattr(settings, "DISCORD_WEBHOOK_URLS"):
                urls = settings.DISCORD_WEBHOOK_URLS
                if isinstance(urls, dict):
                    # Try level-specific URL first, then DEFAULT
                    url = urls.get(record.levelname.upper()) or urls.get("DEFAULT")
                    if url:
                        return url
                elif isinstance(urls, str):
                    return urls

            # Check for simple string configuration
            if hasattr(settings, "DISCORD_WEBHOOK_URL"):
                return settings.DISCORD_WEBHOOK_URL
        except Exception:  # noqa: BLE001
            # Django installed but unconfigured makes hasattr() raise
            # ImproperlyConfigured; any settings trouble should fall through to
            # the env vars rather than break the caller's logging call.
            return None
        return None

    def get_url(self, record: logging.LogRecord) -> str | None:
        """Get webhook URL from Django settings or environment variables.

        Checks in this order:
        1. settings.DISCORD_WEBHOOK_URLS[level]
        2. settings.DISCORD_WEBHOOK_URLS['DEFAULT']
        3. settings.DISCORD_WEBHOOK_URL
        4. Environment variable DISCORD_WEBHOOK_URL_{LEVEL}
        5. Environment variable DISCORD_WEBHOOK_URL
        """
        url = self._url_from_settings(record)
        if url is not None:
            return url

        # Fall back to environment variables
        return os.getenv(
            f"DISCORD_WEBHOOK_URL_{record.levelname.upper()}",
            os.getenv("DISCORD_WEBHOOK_URL"),
        )

    def _post(
        self, url: str, data: Payload, session: requests.Session | None = None
    ) -> requests.Response:
        """Actually send the payload. Blocks, but bounded by self.timeout."""
        poster = session or self._session or requests
        return poster.post(url, json=data, timeout=self.timeout)

    def post_response(self, record: logging.LogRecord) -> requests.Response | None:
        """Synchronously post a record, returning the response.

        This is the blocking primitive; prefer letting emit() handle delivery.
        """
        data = self.get_payload(record)
        url = self.get_url(record)
        if url is not None:
            return self._post(url, data)
        else:
            return None

    def _ensure_worker(self) -> queue.Queue[tuple[str, Payload] | None]:
        """Return the work queue, starting the worker thread if needed.

        Started lazily rather than in __init__ so that prefork servers
        (gunicorn, uWSGI) which build handlers in the master and then fork get
        a fresh thread per worker process; threads do not survive a fork.
        """
        with self._worker_lock:
            thread = self._thread
            if (
                thread is None
                or not thread.is_alive()
                or self._pid != os.getpid()  # we were forked
            ):
                self._pid = os.getpid()
                self._session = requests.Session()
                self._queue = queue.Queue(maxsize=self.queue_size)
                self._thread = threading.Thread(
                    target=self._worker,
                    args=(self._queue, self._session),
                    name="discordo-webhook",
                    daemon=True,
                )
                self._thread.start()
            assert self._queue is not None
            return self._queue

    def _worker(
        self,
        work: queue.Queue[tuple[str, Payload] | None],
        session: requests.Session,
    ) -> None:
        while True:
            item = work.get()
            try:
                if item is None:  # sentinel from close()
                    return
                url, data = item
                try:
                    self._post(url, data, session)
                except Exception:  # noqa: BLE001 -- a log sink must not raise
                    if logging.raiseExceptions:
                        traceback.print_exc(file=sys.stderr)
            finally:
                work.task_done()

    def emit(self, record: logging.LogRecord):
        # requests/urllib3 log too; if this handler is on the root logger at a
        # low level, posting would emit a record that triggers another post.
        if threading.current_thread() is self._thread:
            return
        try:
            url = self.get_url(record)
            if url is None:
                return
            data = self.get_payload(record)
            if self.blocking or self._closed:
                self._post(url, data)
                return
            try:
                self._ensure_worker().put_nowait((url, data))
            except queue.Full:
                # dropping is the right call: waiting for room would
                # reintroduce exactly the stall we are avoiding
                self.dropped += 1
        except Exception:  # noqa: BLE001 -- see logging.Handler.handleError
            self.handleError(record)

    def flush(self) -> None:
        """Wait (briefly) for queued records to be delivered."""
        work = self._queue
        if work is None or self._thread is None:
            return
        # queue.Queue.join() with a deadline: waiting forever on a hung
        # webhook would be the same bug in a different costume
        deadline = time.monotonic() + self.shutdown_timeout
        with work.all_tasks_done:
            while work.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                work.all_tasks_done.wait(remaining)

    def close(self) -> None:
        """Deliver anything still queued, then stop the worker thread.

        The sentinel goes through the same FIFO queue as real records, so
        joining the worker also drains the backlog -- no separate flush needed
        (logging.shutdown() calls flush() before close() regardless, and
        double-flushing would spend the timeout budget twice).
        """
        try:
            with self._worker_lock:
                thread, work, session = self._thread, self._queue, self._session
                self._thread = self._queue = self._session = None
                self._closed = True
            if work is not None:
                try:
                    work.put_nowait(None)
                except queue.Full:
                    pass
            if thread is not None:
                thread.join(self.shutdown_timeout)
            if session is not None:
                session.close()
        finally:
            super().close()
