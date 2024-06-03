import sys

from jaraco.test.cpython import from_test_support, try_import


os_helper = try_import('os_helper') or from_test_support(
    'FakePath',
    'temp_dir',
)

sys.modules[__name__ + '.os_helper'] = os_helper


try:
    from importlib.resources.abc import Traversable
except ImportError:
    try:
        # Python 3.9
        from importlib.abc import Traversable
    except ImportError:
        # Python 3.8
        from importlib_resources.abc import Traversable


__all__ = ['Traversable']
