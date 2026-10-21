import sys
import unittest

if sys.version_info >= (3, 11):
    from importlib.resources.abc import Traversable
else:  # pragma: no cover
    from importlib.abc import Traversable  # type: ignore[attr-defined, unused-ignore]


__all__ = ['TestCase', 'Traversable']


class _TestCase(unittest.TestCase):  # pragma: no cover
    def enterContext(self, cm):
        result = cm.__enter__()
        self.addCleanup(lambda: cm.__exit__(None, None, None))
        return result


TestCase = unittest.TestCase if sys.version_info >= (3, 11) else _TestCase
