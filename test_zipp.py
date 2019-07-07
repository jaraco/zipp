# coding: utf-8

from __future__ import division, unicode_literals

import io
import zipfile
import posixpath
import contextlib
import tempfile
import shutil

try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib

try:
    from contextlib import ExitStack
except ImportError:
    from contextlib2 import ExitStack

try:
    import unittest

    unittest.TestCase.subTest
except AttributeError:
    import unittest2 as unittest

import zipp

__metaclass__ = type
consume = tuple


def add_dirs(zipfile):
    """
    Given a writable zipfile, inject directory entries for
    any directories implied by the presence of children.
    """
    names = zipfile.namelist()
    consume(
        zipfile.writestr(name + "/", b"")
        for name in map(posixpath.dirname, names)
        if name and name + "/" not in names
    )
    return zipfile


def build_abcde_files():
    """
    Create a zip file with this structure:

    .
    ├── a.txt
    └── b
        ├── c.txt
        └── d
            └── e.txt
    """
    data = io.BytesIO()
    zf = zipfile.ZipFile(data, "w")
    zf.writestr("a.txt", b"content of a")
    zf.writestr("b/c.txt", b"content of c")
    zf.writestr("b/d/e.txt", b"content of e")
    zf.filename = "abcde.zip"
    return zf


@contextlib.contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield pathlib.Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir)


class TestEverything(unittest.TestCase):
    def setUp(self):
        self.fixtures = ExitStack()
        self.addCleanup(self.fixtures.close)

    def zipfile_abcde(self):
        with self.subTest():
            yield build_abcde_files()
        with self.subTest():
            yield add_dirs(build_abcde_files())

    def zipfile_ondisk(self):
        tmpdir = self.fixtures.enter_context(tempdir())
        for zipfile_abcde in self.zipfile_abcde():
            buffer = zipfile_abcde.fp
            zipfile_abcde.close()
            path = tmpdir / zipfile_abcde.filename
            with path.open("wb") as strm:
                strm.write(buffer.getvalue())
            yield path

    def test_iterdir_istype(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            assert root.is_dir()
            a, b = root.iterdir()
            assert a.is_file()
            assert b.is_dir()
            c, d = b.iterdir()
            assert c.is_file()
            e, = d.iterdir()
            assert e.is_file()

    def test_open(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            a, b = root.iterdir()
            with a.open() as strm:
                data = strm.read()
            assert data == b"content of a"

    def test_read(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            a, b = root.iterdir()
            assert a.read_text() == "content of a"
            assert a.read_bytes() == b"content of a"

    def test_joinpath(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            a = root.joinpath("a")
            assert a.is_file()
            e = root.joinpath("b").joinpath("d").joinpath("e.txt")
            assert e.read_text() == "content of e"

    def test_traverse_truediv(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            a = root / "a"
            assert a.is_file()
            e = root / "b" / "d" / "e.txt"
            assert e.read_text() == "content of e"

    def test_traverse_simplediv(self):
        """
        Disable the __future__.division when testing traversal.
        """
        for zipfile_abcde in self.zipfile_abcde():
            code = compile(
                source="zipp.Path(zipfile_abcde) / 'a'",
                filename="(test)",
                mode="eval",
                dont_inherit=True,
            )
            eval(code)

    def test_pathlike_construction(self):
        """
        zipp.Path should be constructable from a path-like object
        """
        for zipfile_ondisk in self.zipfile_ondisk():
            pathlike = pathlib.Path(str(zipfile_ondisk))
            zipp.Path(pathlike)

    def test_traverse_pathlike(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            root / pathlib.Path("a")

    def test_parent(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            assert (root / 'a').parent.at == ''
            assert (root / 'a' / 'b').parent.at == 'a/'

    def test_dir_parent(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            assert (root / 'b').parent.at == ''
            assert (root / 'b/').parent.at == ''

    def test_missing_dir_parent(self):
        for zipfile_abcde in self.zipfile_abcde():
            root = zipp.Path(zipfile_abcde)
            assert (root / 'missing dir/').parent.at == ''
