import zippath


def test_zippath():
    root = zippath.ZipPath('./abcde.zip')
    a, b = root.listdir()
    assert a.isfile()
    assert b.isdir()
    c, d = b.listdir()
    assert c.isfile()
    e, = d.listdir()
    assert e.isfile()
