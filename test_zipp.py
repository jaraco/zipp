from __future__ import division


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
