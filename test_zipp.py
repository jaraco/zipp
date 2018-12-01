from __future__ import division, unicode_literals


try:
    import pathlib
except ImportError:
    import pathlib2 as pathlib

import zipp


def test_iterdir_istype(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    assert root.is_dir()
    a, b = root.iterdir()
    assert a.is_file()
    assert b.is_dir()
    c, d = b.iterdir()
    assert c.is_file()
    e, = d.iterdir()
    assert e.is_file()


def test_open(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a, b = root.iterdir()
    with a.open() as strm:
        data = strm.read()
    assert data == b'content of a'


def test_read(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a, b = root.iterdir()
    assert a.read_text() == 'content of a'
    assert a.read_bytes() == b'content of a'


def test_traverse_truediv(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a = root / 'a'
    assert a.is_file()
    e = root / 'b' / 'd' / 'e.txt'
    assert e.read_text() == 'content of e'


def test_traverse_simplediv(zipfile_abcde):
    """
    Disable the __future__.division when testing traversal.
    """
    code = compile(
        source="zipp.Path(zipfile_abcde) / 'a'",
        filename='(test)',
        mode='eval',
        dont_inherit=True,
    )
    eval(code)


def test_pathlike_construction(zipfile_ondisk):
    """
    zipp.Path should be constructable from a path-like object
    """
    pathlike = pathlib.Path(str(zipfile_ondisk))
    zipp.Path(pathlike)


def test_traverse_pathlike(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    root / pathlib.Path('a')
