"""
Expose zipp.Path as .zipfile.Path.

Includes everything else in ``zipfile`` to match future usage. Just
use:

>>> from zipp.compat.overlay import zipfile

in place of ``import zipfile``.

Relative imports are supported too.

>>> from zipp.compat.overlay.zipfile import ZipInfo
"""

import importlib
import sys
import types

import zipp


zipfile = types.SimpleNamespace(**vars(importlib.import_module('zipfile')))
zipfile.Path = zipp.Path
zipfile._path = zipp

sys.modules[__name__ + '.zipfile'] = zipfile  # type: ignore[assignment]
