import sys

if sys.version_info >= (3, 11):
    from importlib.resources.abc import Traversable
else:  # pragma: no cover
    from importlib.abc import Traversable  # type: ignore[attr-defined, unused-ignore]


__all__ = ['Traversable']
