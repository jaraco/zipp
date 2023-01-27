import sys

import pytest


class Flags:
    warn_default_encoding = 0

    def __getattr__(self, *args):
        return getattr(sys.flags, *args)


@pytest.fixture(scope="session")
def monkeysession():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest.fixture(scope="session", autouse=True)
def future_flags(monkeysession):
    if sys.version_info > (3, 10):
        return
    monkeysession.setattr(sys, 'flags', Flags())
