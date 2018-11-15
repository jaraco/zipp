import zippath


def test_listdir_istype(zipfile_abcde):
    root = zippath.ZipPath(zipfile_abcde)
    a, b = root.listdir()
    assert a.isfile()
    assert b.isdir()
    c, d = b.listdir()
    assert c.isfile()
    e, = d.listdir()
    assert e.isfile()


def test_open(zipfile_abcde):
    root = zippath.ZipPath(zipfile_abcde)
    a, b = root.listdir()
    with a.open() as strm:
        data = strm.read()
    assert data == b'content of a'
