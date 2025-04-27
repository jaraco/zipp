"""
A Path-like interface for zipfiles.

This codebase is shared between zipfile.Path in the stdlib
and zipp in PyPI. See
https://github.com/python/importlib_metadata/wiki/Development-Methodology
for more detail.
"""

import pathlib
import posixpath
import stat
import zipfile

import pathlib_abc

__all__ = ['PathInfo', 'Path']


class PathInfo(pathlib_abc.PathInfo):
    """
    A :class:`pathlib.types.PathInfo` interface for zip file members.

    An instance of this class replaces the :attr:`ZipFile.filelist` object,
    and represents the root of the zip member tree. To remain (mostly)
    compatible with the original list interface, this class provides a
    :meth:`~list.append` method, plus :meth:`~object.__iter__` and
    :meth:`~object.__len__` methods that traverse the tree.
    """

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
        if not name:
            info = self
        elif name in self.children:
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

    def __reduce__(self):
        return (self.__class__, (self.root.filename, self.at))

    def open(self, mode='r', *args, pwd=None, **kwargs):
        """
        Open this entry as text or binary following the semantics
        of ``pathlib.Path.open()`` by passing arguments through
        to io.TextIOWrapper().
        """
        old_pwd, self.root.pwd = self.root.pwd, pwd
        try:
            return pathlib_abc.magic_open(self, mode, -1, *args, **kwargs)
        finally:
            self.root.pwd = old_pwd

    def __open_rb__(self, buffering=-1):
        if self.is_dir():
            raise IsADirectoryError(self)
        elif not self.exists():
            raise FileNotFoundError(self)
        return self.root.open(self.info.zip_info, 'r')

    def __open_wb__(self, buffering=-1):
        if self.is_dir():
            raise IsADirectoryError(self)
        return self.root.open(self.at, 'w')

    def _base(self):
        return super() if self.at else pathlib.PurePosixPath(self.root.filename)

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

    @property
    def info(self):
        return self.root.filelist.resolve(self.at)

    def with_segments(self, *pathsegments):
        at = posixpath.join(*pathsegments)
        return self.__class__(self.root, at)

    def is_dir(self):
        return self.info.is_dir()

    def is_file(self):
        return self.info.is_file()

    def exists(self):
        return self.info.exists()

    def iterdir(self):
        if not self.is_dir():
            raise ValueError("Can't listdir a file")
        return (self / name for name in self.info.children)

    def match(self, path_pattern):
        return pathlib.PurePosixPath(self.at).match(path_pattern)

    def is_symlink(self):
        """
        Return whether this path is a symlink.
        """
        info = self.info.zip_info
        if not info:
            return False
        mode = info.external_attr >> 16
        return stat.S_ISLNK(mode)

    def readlink(self):
        raise NotImplementedError

    def rglob(self, pattern):
        return self.glob(f'**/{pattern}')

    def relative_to(self, other, *extra):
        return posixpath.relpath(str(self), str(other.joinpath(*extra)))

    def __str__(self):
        return self.at

    def __repr__(self):
        return self.__repr.format(self=self)

    @property
    def parent(self):
        if not self.at:
            return self.filename.parent
        return super().parent

    # Disable "free" features from pathlib-abc that we don't test
    # FIXME: enable these.
    __rtruediv__ = None
    anchor = None
    parts = None
    parents = None
    with_name = None
    with_stem = None
    with_suffix = None
    full_match = None
    walk = None
    copy = None
    copy_into = None
