v0.5.2
======

#7: Parent of a directory now actually returns the parent.

v0.5.1
======

Declared package as backport.

v0.5.0
======

Add ``.joinpath()`` method and ``.parent`` property.

Now a backport release of the ``zipfile.Path`` class.

v0.4.0
======

#4: Add support for zip files with implied directories.

v0.3.3
======

#3: Fix issue where ``.name`` on a directory was empty.

v0.3.2
======

#2: Fix TypeError on Python 2.7 when classic division is used.

v0.3.1
======

#1: Fix TypeError on Python 3.5 when joining to a path-like object.

v0.3.0
======

Add support for constructing a ``zipp.Path`` from any path-like
object.

``zipp.Path`` is now a new-style class on Python 2.7.

v0.2.1
======

Fix issue with ``__str__``.

v0.2.0
======

Drop reliance on future-fstrings.

v0.1.0
======

Initial release with basic functionality.
