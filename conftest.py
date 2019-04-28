# coding: utf-8

import io
import zipfile
import posixpath

import pytest
from more_itertools import consume


def add_dirs(zipfile):
    """
    Given a writable zipfile, inject directory entries for
    any directories implied by the presence of children.
    """
    names = zipfile.namelist()
    consume(
        zipfile.writestr(name + '/', '')
        for name in map(posixpath.dirname, names)
        if name
        and name + '/' not in names
    )
    return zipfile


@pytest.fixture(params=[add_dirs, lambda x: x])
def zipfile_abcde(request):
    """
    Build the abcde zipfile with and without dir entries.
    """
    return request.param(build_abcde_files())


@pytest.fixture
def zipfile_abcde_full():
    return add_dirs(build_abcde_files())


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
    zf = zipfile.ZipFile(data, 'w')
    zf.writestr('a.txt', 'content of a')
    zf.writestr('b/c.txt', 'content of c')
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
