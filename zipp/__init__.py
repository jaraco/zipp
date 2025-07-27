"""
A Path-like interface for zipfiles.

This codebase is shared between zipfile.Path in the stdlib
and zipp in PyPI. See
https://github.com/python/importlib_metadata/wiki/Development-Methodology
for more detail.
"""

import functools
import itertools
import pathlib
import posixpath
import stat
import zipfile

import pathlib_abc

from ._functools import save_method_args
from .compat.py310 import text_encoding

__all__ = ['Path']


def _parents(path):
    """
    Given a path with elements separated by
    posixpath.sep, generate all parents of that path.

    >>> list(_parents('b/d'))
    ['b']
    >>> list(_parents('/b/d/'))
    ['/b']
    >>> list(_parents('b/d/f/'))
    ['b/d', 'b']
    >>> list(_parents('b'))
    []
    >>> list(_parents(''))
    []
    """
    return itertools.islice(_ancestry(path), 1, None)


def _ancestry(path):
    """
    Given a path with elements separated by
    posixpath.sep, generate all elements of that path.

    >>> list(_ancestry('b/d'))
    ['b/d', 'b']
    >>> list(_ancestry('/b/d/'))
    ['/b/d', '/b']
    >>> list(_ancestry('b/d/f/'))
    ['b/d/f', 'b/d', 'b']
    >>> list(_ancestry('b'))
    ['b']
    >>> list(_ancestry(''))
    []

    Multiple separators are treated like a single.

    >>> list(_ancestry('//b//d///f//'))
    ['//b//d///f', '//b//d', '//b']
    """
    path = path.rstrip(posixpath.sep)
    while path.rstrip(posixpath.sep):
        yield path
        path, tail = posixpath.split(path)


_dedupe = dict.fromkeys
"""Deduplicate an iterable in original order"""


def _difference(minuend, subtrahend):
    """
    Return items in minuend not in subtrahend, retaining order
    with O(1) lookup.
    """
    return itertools.filterfalse(set(subtrahend).__contains__, minuend)


class InitializedState:
    """
    Mix-in to save the initialization state for pickling.
    """

    @save_method_args
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getstate__(self):
        return self._saved___init__.args, self._saved___init__.kwargs

    def __setstate__(self, state):
        args, kwargs = state
        super().__init__(*args, **kwargs)


class CompleteDirs(InitializedState, zipfile.ZipFile):
    """
    A ZipFile subclass that ensures that implied directories
    are always included in the namelist.

    >>> list(CompleteDirs._implied_dirs(['foo/bar.txt', 'foo/bar/baz.txt']))
    ['foo/', 'foo/bar/']
    >>> list(CompleteDirs._implied_dirs(['foo/bar.txt', 'foo/bar/baz.txt', 'foo/bar/']))
    ['foo/']
    """

    @staticmethod
    def _implied_dirs(names):
        parents = itertools.chain.from_iterable(map(_parents, names))
        as_dirs = (p + posixpath.sep for p in parents)
        return _dedupe(_difference(as_dirs, names))

    def namelist(self):
        names = super().namelist()
        return names + list(self._implied_dirs(names))

    def _name_set(self):
        return set(self.namelist())

    def resolve_dir(self, name):
        """
        If the name represents a directory, return that name
        as a directory (with the trailing slash).
        """
        names = self._name_set()
        dirname = name + '/'
        dir_match = name not in names and dirname in names
        return dirname if dir_match else name

    def getinfo(self, name):
        """
        Supplement getinfo for implied dirs.
        """
        try:
            return super().getinfo(name)
        except KeyError:
            if not name.endswith('/') or name not in self._name_set():
                raise
            return zipfile.ZipInfo(filename=name)

    @classmethod
    def make(cls, source):
        """
        Given a source (filename or zipfile), return an
        appropriate CompleteDirs subclass.
        """
        if isinstance(source, CompleteDirs):
            return source

        if not isinstance(source, zipfile.ZipFile):
            return cls(source)

        # Only allow for FastLookup when supplied zipfile is read-only
        if 'r' not in source.mode:
            cls = CompleteDirs

        source.__class__ = cls
        return source

    @classmethod
    def inject(cls, zf: zipfile.ZipFile) -> zipfile.ZipFile:
        """
        Given a writable zip file zf, inject directory entries for
        any directories implied by the presence of children.
        """
        for name in cls._implied_dirs(zf.namelist()):
            zf.writestr(name, b"")
        return zf


class FastLookup(CompleteDirs):
    """
    ZipFile subclass to ensure implicit
    dirs exist and are resolved rapidly.
    """

    def namelist(self):
        return self._namelist

    @functools.cached_property
    def _namelist(self):
        return super().namelist()

    def _name_set(self):
        return self._name_set_prop

    @functools.cached_property
    def _name_set_prop(self):
        return super()._name_set()


class PathInfo(pathlib_abc.PathInfo):
    """
    A :class:`pathlib.types.PathInfo` interface for zip file members.

    An instance of this class replaces the :attr:`ZipFile.filelist` object,
    and represents the root of the zip member tree. To remain (mostly)
    compatible with the original list interface, this class provides a
    :meth:`~list.append` method, plus :meth:`~object.__iter__` and
    :meth:`~object.__len__` methods that traverse the tree.
    """

    __slots__ = ('_exists', 'zip_info', 'children')

    def __init__(self, items=tuple(), exists=True):
        self._exists = exists
        self.zip_info = None
        self.children = {}
        for zip_info in items:
            self.append(zip_info)

    def __iter__(self):
        if self.zip_info:
            yield self.zip_info
        for child in self.children.values():
            yield from child

    def __len__(self):
        length = 1 if self.zip_info else 0
        for child in self.children.values():
            length += len(child)
        return length

    def append(self, zip_info):
        self.resolve(zip_info.filename, create=True).zip_info = zip_info

    def resolve(self, path, create=False):
        if not path:
            return self
        name, _, path = path.partition('/')
        if name in self.children:
            info = self.children[name]
        elif create:
            info = self.children[name] = PathInfo()
        else:
            return PathInfo(exists=False)
        return info.resolve(path, create)

    def exists(self, follow_symlinks=True):
        return self._exists

    def is_dir(self, follow_symlinks=True):
        if self.zip_info:
            return self.zip_info.filename.endswith('/')
        return self._exists

    def is_file(self, follow_symlinks=True):
        if self.zip_info:
            return not self.zip_info.filename.endswith('/')
        return False

    def is_symlink(self):
        if self.zip_info:
            return stat.S_ISLNK(self.zip_info.external_attr >> 16)
        return False


class Path(pathlib_abc.ReadablePath):
    """
    A :class:`importlib.resources.abc.Traversable` interface for zip files.

    Implements many of the features users enjoy from
    :class:`pathlib.Path`.

    Consider a zip file with this structure::

        .
        ├── a.txt
        └── b
            ├── c.txt
            └── d
                └── e.txt

    >>> import io
    >>> data = io.BytesIO()
    >>> zf = zipfile.ZipFile(data, 'w')
    >>> zf.writestr('a.txt', 'content of a')
    >>> zf.writestr('b/c.txt', 'content of c')
    >>> zf.writestr('b/d/e.txt', 'content of e')
    >>> zf.filename = 'mem/abcde.zip'

    Path accepts the zipfile object itself or a filename

    >>> path = Path(zf)

    From there, several path operations are available.

    Directory iteration (including the zip file itself):

    >>> a, b = path.iterdir()
    >>> a
    Path('mem/abcde.zip', 'a.txt')
    >>> b
    Path('mem/abcde.zip', 'b')

    name property:

    >>> b.name
    'b'

    join with divide operator:

    >>> c = b / 'c.txt'
    >>> c
    Path('mem/abcde.zip', 'b/c.txt')
    >>> c.name
    'c.txt'

    Read text:

    >>> c.read_text(encoding='utf-8')
    'content of c'

    existence:

    >>> c.exists()
    True
    >>> (b / 'missing.txt').exists()
    False

    Coercion to string:

    >>> import os
    >>> str(c).replace(os.sep, posixpath.sep)
    'mem/abcde.zip/b/c.txt'

    At the root, ``name``, ``filename``, and ``parent``
    resolve to the zipfile.

    >>> str(path)
    'mem/abcde.zip/'
    >>> path.name
    'abcde.zip'
    >>> path.filename == pathlib.Path('mem/abcde.zip')
    True
    >>> str(path.parent)
    'mem'

    If the zipfile has no filename, such attributes are not
    valid and accessing them will raise an Exception.

    >>> zf.filename = None
    >>> path.name
    Traceback (most recent call last):
    ...
    TypeError: ...

    >>> path.filename
    Traceback (most recent call last):
    ...
    TypeError: ...

    >>> path.parent
    Traceback (most recent call last):
    ...
    TypeError: ...

    # workaround python/cpython#106763
    >>> pass
    """

    __slots__ = ('_initial_arg', 'root', 'at')
    __repr = "{self.__class__.__name__}({self.root.filename!r}, {self.at!r})"
    parser = posixpath

    def __init__(self, root, at=""):
        """
        Construct a Path from a ZipFile or filename.

        Note: When the source is an existing ZipFile object,
        its type (__class__) will be mutated to a
        specialized type. If the caller wishes to retain the
        original type, the caller should either create a
        separate ZipFile object or pass a filename.
        """
        self._initial_arg = root
        if not isinstance(root, zipfile.ZipFile):
            root = zipfile.ZipFile(root)
        if not isinstance(root.filelist, PathInfo):
            root.filelist = PathInfo(root.filelist)
        self.root = root
        self.at = at

    def __eq__(self, other):
        """
        >>> import io
        >>> Path(zipfile.ZipFile(io.BytesIO(), 'w')) == 'foo'
        False
        """
        if self.__class__ is not other.__class__:
            return NotImplemented
        return (self.root, self.at) == (other.root, other.at)

    def __hash__(self):
        return hash((self.root, self.at))

    def open(self, mode='r', encoding=None, errors=None, newline=None, pwd=None):
        """
        Open this entry as text or binary following the semantics
        of ``pathlib.Path.open()`` by passing arguments through
        to io.TextIOWrapper().
        """
        if self.is_dir():
            raise IsADirectoryError(self)
        elif 'b' not in mode:
            encoding = text_encoding(encoding)
        old_pwd, self.root.pwd = self.root.pwd, pwd
        try:
            return pathlib_abc.vfsopen(self, mode, -1, encoding, errors, newline)
        finally:
            self.root.pwd = old_pwd

    def __open_reader__(self):
        if not self.exists():
            raise FileNotFoundError(self)
        return self.root.open(self.info.zip_info, 'r')

    def __open_writer__(self, mode):
        return self.root.open(self.at, mode)

    def _base(self):
        return super() if self.at else self.filename

    @property
    def parent(self):
        return self._base().parent

    @property
    def name(self):
        return self._base().name

    @property
    def suffix(self):
        return self._base().suffix

    @property
    def suffixes(self):
        return self._base().suffixes

    @property
    def stem(self):
        return self._base().stem

    @property
    def filename(self):
        return pathlib.Path(self.root.filename).joinpath(self.at)

    def with_segments(self, *pathsegments):
        at = posixpath.join(*pathsegments)
        path = self.__class__(self.root, at)
        path._initial_arg = self._initial_arg
        return path

    @property
    def info(self):
        return self.root.filelist.resolve(self.at)

    def is_dir(self):
        return self.info.is_dir()

    def is_file(self):
        return self.info.is_file()

    def exists(self):
        return self.info.exists()

    def iterdir(self):
        if not self.is_dir():
            raise ValueError("Can't listdir a file")
        return (self / name for name in self.info.children if name)

    def match(self, path_pattern):
        return pathlib.PurePosixPath(self.at).match(path_pattern)

    def is_symlink(self):
        """
        Return whether this path is a symlink.
        """
        return self.info.is_symlink()

    def rglob(self, pattern):
        return self.glob(f'**/{pattern}')

    def relative_to(self, other, *extra):
        return posixpath.relpath(str(self), str(other.joinpath(*extra)))

    def __str__(self):
        return posixpath.join(self.root.filename, self.at)

    def __repr__(self):
        return self.__repr.format(self=self)

    def __reduce__(self):
        return self.__class__, (self._initial_arg, self.at)

    def __vfspath__(self):
        return self.at

    # Disable "free" features from pathlib-abc that we don't test
    # FIXME: enable these.
    __rtruediv__ = None
    anchor = None
    copy_into = None
    copy = None
    full_match = None
    parts = None
    readlink = None
    walk = None
    with_name = None
    with_stem = None
    with_suffix = None
