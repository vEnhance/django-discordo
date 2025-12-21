# django-discordo

A janky Discord webhook handler
originally written for [OTIS-WEB](https://github.com/vEnhance/otis-web).

## Features, apparently

- 🎨 Color-coded log levels with emoji indicators
- 📝 Automatic formatting of Django request data
- 🔒 Automatic redaction of sensitive data (passwords, tokens)
- 🎯 Support for custom log levels (VERBOSE, SUCCESS, ACTION)
- 🔧 Configurable webhook URLs per log level
- 📊 Rich metadata including user info, status codes, and stack traces

## Installation

For example, if using `uv`:

```bash
uv add django-discordo
```

Contrary to the name, **Django is actually an optional dependency**.
This can also be used for logging in non-Django applications;
in that case Django-specific functionality is turned off.

## Configuration

### 1. Create a Discord Webhook

1. Go to Server Settings → Integrations → Webhooks
2. Click "New Webhook"
3. Copy the webhook URL

### 2. Configure Webhook URL

There are two possible ways to do this (first one takes precedence):

#### Use settings.py (for Django applications)

Add your webhook URL to your Django `settings.py`:

```python
# Simple configuration - single webhook for all log levels
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# OR: Advanced configuration - different webhooks per log level
DISCORD_WEBHOOK_URLS = {
    "CRITICAL": "https://discord.com/api/webhooks/CRITICAL_WEBHOOK",
    "ERROR": "https://discord.com/api/webhooks/ERROR_WEBHOOK",
    "WARNING": "https://discord.com/api/webhooks/WARNING_WEBHOOK",
    "DEFAULT": "https://discord.com/api/webhooks/DEFAULT_WEBHOOK",  # Fallback for other levels
}
```

(Webhook URL's are considered secrets,
so you probably don't want to actually hardcode the URL's into `settings.py`
if your source code is public.)

#### Using environment variables directly

If the URLs are not configured in `settings.py` (or Django is not present at
all) then `django-discordo` will check environment variables instead:

```bash
# In your .env file
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
# Or level-specific
DISCORD_WEBHOOK_URL_ERROR=https://discord.com/api/webhooks/YOUR_ERROR_WEBHOOK_URL
```

### 3. Using the handler

In Django, add the Discord handler to your Django `settings.py`, e.g.

```python
import logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "discord": {
            "class": "django_discordo.DiscordWebhookHandler",
            "level": "WARNING",
        },
    },
    "root": {
        "handlers": ["discord"],
        "level": "INFO",
    },
}
```

Otherwise, import the webhook handler directly, say:

```python
from django_discordo import DiscordWebhookHandler
logger = logging.getLogger("root")
logger.setLevel(logging.INFO)
logger.addHandler(DiscordWebhookHandler())
logger.addHandler(logging.StreamHandler())
```

## Custom Log Levels

django-discordo provides three custom log levels in addition to Django's standard levels:

- **VERBOSE** (level 15): Between DEBUG and INFO, for detailed but not critical information
- **SUCCESS** (level 25): Between INFO and WARNING, for successful operations
- **ACTION** (level 35): Between WARNING and ERROR, for important user actions

### Usage Example

```python
import logging
from django_discordo import VERBOSE_LOG_LEVEL, SUCCESS_LOG_LEVEL, ACTION_LOG_LEVEL

logger = logging.getLogger(__name__)

# Using custom log levels
logger.log(VERBOSE_LOG_LEVEL, "Student has submitted the problem set.")
logger.log(SUCCESS_LOG_LEVEL, "Student has found new diamond.")
logger.log(ACTION_LOG_LEVEL, "Student has updated a link in ARCH, please check it.")
```

## Advanced Configuration

### Filtering Logs

You can add filters to prevent certain logs from being sent to Discord;
e.g. OTIS-WEB filters out certain 404 errors

```python
def filter_useless_404(record):
    if record.args and len(record.args) >= 2:
        return "wp-include" not in str(record.args[1])
    return True

LOGGING = {
    "filters": {
        "filter_useless_404": {
            "()": "django.utils.log.CallbackFilter",
            "callback": filter_useless_404,
        },
    },
    "handlers": {
        "discord": {
            "class": "django_discordo.DiscordWebhookHandler",
            "level": "WARNING",
            "filters": ["filter_useless_404"],
        },
    },
}
```

## Testing Mode

When running tests, you may want to disable Discord logging to avoid spam:

```python
import logging
from django_discordo import ACTION_LOG_LEVEL

if TESTING:
    logging.disable(ACTION_LOG_LEVEL)
```

This disables all logs at ACTION level and below (including SUCCESS, INFO, VERBOSE, and DEBUG).

## How It Works

When a log record is emitted:

1. The handler formats the log message with appropriate emoji and color
2. Extracts metadata (user, module, filename, line number, status code)
3. Includes Django request details (method, path, user agent, POST data)
4. Redacts sensitive fields (passwords, tokens)
5. Sends a beautifully formatted embed to Discord via webhook

## Discord Embed Format

Each log message appears as a Discord embed with:

- **Title**: Log message (with emoji indicator)
- **Color**: Coded by log level (red for errors, yellow for warnings, etc.)
- **Fields**: Status code, log level, module, user, filename
- **Description**: Detailed message, exception traceback, and request data
