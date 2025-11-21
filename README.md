# django-discordo

A janky Discord webhook handler for Django logging
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

## Configuration

### 1. Create a Discord Webhook

1. Go to Server Settings → Integrations → Webhooks
2. Click "New Webhook"
3. Copy the webhook URL

### 2. Configure Webhook URL

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

**Alternative**: You can also use environment variables
(the handler will check settings first, then fall back to environment variables):

```bash
# In your .env file
WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
# Or level-specific
WEBHOOK_URL_ERROR=https://discord.com/api/webhooks/YOUR_ERROR_WEBHOOK_URL
```

### 3. Update Django Settings

Add the Discord handler to your Django `settings.py`:

```python
import logging
from django_discordo import ACTION_LOG_LEVEL, SUCCESS_LOG_LEVEL, VERBOSE_LOG_LEVEL

# Custom log levels are automatically registered when you import django_discordo

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "discord": {
            "class": "django_discordo.DiscordWebhookHandler",
            "level": "WARNING",  # Adjust as needed
        },
    },
    "root": {
        "handlers": ["discord"],
        "level": "INFO",
    },
}
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
logger.log(VERBOSE_LOG_LEVEL, "Detailed operation info")
logger.log(SUCCESS_LOG_LEVEL, "User registration completed successfully")
logger.log(ACTION_LOG_LEVEL, "Admin user modified critical settings")
```

## Advanced Configuration

### Filtering Logs

You can add filters to prevent certain logs from being sent to Discord:

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

### Level-Specific Webhooks

You can route different log levels to different Discord channels by setting level-specific webhook URLs:

```bash
WEBHOOK_URL_CRITICAL=https://discord.com/api/webhooks/CRITICAL_CHANNEL
WEBHOOK_URL_ERROR=https://discord.com/api/webhooks/ERROR_CHANNEL
WEBHOOK_URL_WARNING=https://discord.com/api/webhooks/WARNING_CHANNEL
WEBHOOK_URL=https://discord.com/api/webhooks/DEFAULT_CHANNEL
```

The handler will check for `WEBHOOK_URL_{LEVELNAME}` first, then fall back to `WEBHOOK_URL`.

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
