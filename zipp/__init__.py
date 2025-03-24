"""
A Path-like interface for zipfiles.

This codebase is shared between zipfile.Path in the stdlib
and zipp in PyPI. See
https://github.com/python/importlib_metadata/wiki/Development-Methodology
for more detail.
"""

import io
import pathlib
import posixpath
import stat
import zipfile

import pathlib_abc


__all__ = ['Path']


class MissingInfo(pathlib_abc.PathInfo):
    zip_info = None
    children = {}
    def exists(self, follow_symlinks=True): return False
    def is_dir(self, follow_symlinks=True): return False
    def is_file(self, follow_symlinks=True): return False
    def is_symlink(self): return False


class PathInfo(pathlib_abc.PathInfo):
    def __init__(self):
        self.zip_info = None
        self.children = {}

    def exists(self, follow_symlinks=True):
        return True

    def is_dir(self, follow_symlinks=True):
        if self.zip_info is None:
            return True
        else:
            return self.zip_info.filename.endswith('/')

    def is_file(self, follow_symlinks=True):
        if self.zip_info is None:
            return False
        else:
            return not self.zip_info.filename.endswith('/')

    def is_symlink(self):
        return False

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
            return MissingInfo()
        return info.resolve(path, create)


class FileList:
    def __init__(self, items):
        self._tree = PathInfo()
        self._items = []
        for item in items:
            self.append(item)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def append(self, item):
        info = self._tree.resolve(item.filename, create=True)
        info.zip_info = item
        self._items.append(item)



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
    Path('mem/abcde.zip', 'b/')

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
        if not isinstance(root.filelist, FileList):
            root.filelist = FileList(root.filelist)
        self.root = root
        self.at = at

    def __eq__(self, other):
        """
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
        return pathlib_abc.magic_open(self, mode, -1, *args, **kwargs)

    def __open_rb__(self, buffering=-1):
        if self.is_dir():
            raise IsADirectoryError(self)
        elif not self.exists():
            raise FileNotFoundError(self)
        path = self.info.zip_info or str(self)
        return self.root.open(path, 'r')

    def __open_wb__(self, buffering=-1):
        if self.is_dir():
            raise IsADirectoryError(self)
        path = self.info.zip_info or str(self)
        return self.root.open(path, 'w')

    @property
    def name(self):
        if not self.at:
            return self.filename.name
        return super().name

    @property
    def filename(self):
        return pathlib.Path(self.root.filename).joinpath(self.at)

    def is_dir(self):
        return self.info.is_dir()

    def is_file(self):
        return self.info.is_file()

    def exists(self):
        return self.info.exists()

    def iterdir(self):
        if not self.is_dir():
            raise ValueError("Can't listdir a file")
        # FIXME: This rigmarole is a workaround for #130.
        names1 = []
        names2 = []
        for name, info in self.info.children.items():
            names = names1 if info.zip_info else names2
            names.append(name)
        return (self / name for name in names1 + names2)

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

    def with_segments(self, *pathsegments):
        at = self.parser.join(*pathsegments)
        return type(self)(self.root, at)

    @property
    def info(self):
        return self.root.filelist._tree.resolve(str(self))

    def readlink(self):
        raise NotImplementedError

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
