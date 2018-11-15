"""
>>> root = ZipPath('./abcde.zip')
>>> list(root.listdir())
[ZipPath('./abcde.zip', 'a.txt'), ZipPath('./abcde.zip', 'b/')]
"""

import posixpath
import zipfile
import operator


class ZipPath:
    def __init__(self, root, at=''):
        self.root = root
        self.at = at

    def _is_child(self, path):
        return posixpath.dirname(path.at.rstrip('/')) == self.at.rstrip('/')

    def _next(self, at):
        return ZipPath(self.root, at)

    def isdir(self):
        return not self.at or self.at.endswith('/')

    def isfile(self):
        return not self.isdir()

    def listdir(self):
        if not self.isdir():
            raise ValueError("Can't listdir a file")
        zf = zipfile.ZipFile(self.root)
        names = map(operator.attrgetter('filename'), zf.infolist())
        subs = map(self._next, names)
        return filter(self._is_child, subs)

    def __str__(self):
        return posixpath.join(self.root, self.at)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.root!r}, {self.at!r})'
