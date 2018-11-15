# coding: future-fstrings

"""
>>> root = Path(getfixture('zipfile_abcde'))
>>> list(root.listdir())
[Path('abcde.zip', 'a.txt'), Path('abcde.zip', 'b/')]
"""

import io
import posixpath
import zipfile
import operator
import functools


class Path:
    def __init__(self, root, at=''):
        self.root = root if isinstance(root, zipfile.ZipFile) \
            else zipfile.ZipFile(root)
        self.at = at

    @property
    def open(self):
        return functools.partial(self.root.open, self.at)

    def read_text(self, *args, **kwargs):
        with self.open() as strm:
            return io.TextIOWrapper(strm, *args, **kwargs).read()

    def read_bytes(self):
        with self.open() as strm:
            return strm.read()

    def _is_child(self, path):
        return posixpath.dirname(path.at.rstrip('/')) == self.at.rstrip('/')

    def _next(self, at):
        return Path(self.root, at)

    def isdir(self):
        return not self.at or self.at.endswith('/')

    def isfile(self):
        return not self.isdir()

    def listdir(self):
        if not self.isdir():
            raise ValueError("Can't listdir a file")
        names = map(operator.attrgetter('filename'), self.root.infolist())
        subs = map(self._next, names)
        return filter(self._is_child, subs)

    def __str__(self):
        return posixpath.join(self.root, self.at)

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.root.filename!r}, {self.at!r})'
        )

    def __truediv__(self, add):
        next = posixpath.join(self.at, add)
        next_dir = posixpath.join(self.at, add, '')
        names = self.root.namelist()
        return self._next(
            next_dir if next not in names and next_dir in names else next
        )
