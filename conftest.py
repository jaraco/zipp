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
    with zf.open('a.txt', 'w') as strm:
        strm.write(b'content of a')
    with zf.open('b/', 'w') as strm:
        pass
    with zf.open('b/c.txt', 'w') as strm:
        strm.write(b'content of c')
    with zf.open('b/d/', 'w') as strm:
        pass
    with zf.open('b/d/e.txt', 'w') as strm:
        strm.write(b'content of e')
    zf.filename = 'abcde.zip'
    return zf
