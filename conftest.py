# coding: utf-8

import io
import zipfile


import pytest


@pytest.fixture
def zipfile_abcde():
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
    zf = zipfile.ZipFile(data, 'w')
    zf.writestr('a.txt', 'content of a')
    zf.writestr('b/', '')
    zf.writestr('b/c.txt', 'content of c')
    zf.writestr('b/d/', '')
    zf.writestr('b/d/e.txt', 'content of e')
    zf.filename = 'abcde.zip'
    return zf


@pytest.fixture
def zipfile_ondisk(zipfile_abcde, tmpdir):
    buffer = zipfile_abcde.fp
    zipfile_abcde.close()
    path = tmpdir / zipfile_abcde.filename
    with path.open('wb') as strm:
        strm.write(buffer.getvalue())
    return path
