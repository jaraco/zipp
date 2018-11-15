from __future__ import division


import zipp


def test_listdir_istype(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    assert root.isdir()
    a, b = root.listdir()
    assert a.isfile()
    assert b.isdir()
    c, d = b.listdir()
    assert c.isfile()
    e, = d.listdir()
    assert e.isfile()


def test_open(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a, b = root.listdir()
    with a.open() as strm:
        data = strm.read()
    assert data == b'content of a'


def test_read(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a, b = root.listdir()
    assert a.read_text() == 'content of a'
    assert a.read_bytes() == b'content of a'


def test_traverse_truediv(zipfile_abcde):
    root = zipp.Path(zipfile_abcde)
    a = root / 'a'
    assert a.isfile()
    e = root / 'b' / 'd' / 'e.txt'
    assert e.read_text() == 'content of e'
