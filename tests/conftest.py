try:
    import django
    from django.conf import settings

    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False


def pytest_configure():
    if DJANGO_AVAILABLE and not settings.configured:
        settings.configure(
            DEBUG=True,
            DATABASES={},
            INSTALLED_APPS=[],
            SECRET_KEY="test-secret-key",
        )
        django.setup()
