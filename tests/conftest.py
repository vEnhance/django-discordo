import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={},
            INSTALLED_APPS=[],
            SECRET_KEY="test-secret-key",
        )
        django.setup()
