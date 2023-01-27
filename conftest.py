import builtins
import sys


def pytest_configure():
    add_future_flags()


def add_future_flags():
    if sys.version_info > (3, 10):
        return

    builtins.EncodingWarning = type('EncodingWarning', (Warning,), {})
