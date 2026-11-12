"""
Standalone regression tests for gh-102: a non-trailing '**' segment (e.g.
'**/*.txt') must match zero or more directory levels, so it also matches
files at the root, not just nested ones -- matching the semantics of the
stdlib glob module and pathlib.Path.glob() on Python 3.13+.

These are intentionally self-contained (only zipp, zipfile, pathlib, io,
and os) and avoid tests/_support.py and tests/compat, which depend on the
stdlib's private ``test.support`` module. That module ships only with a
full CPython source/test checkout, not with a normal interpreter
installation, so importing it fails in this environment with
``ModuleNotFoundError: No module named 'test.support'`` -- unrelated to
this fix. Once that dependency is available again, this coverage would
more naturally live alongside the other glob tests in tests/test_path.py
using its existing ``build_alpharep_fixture``-style fixtures.
"""

import io
import pathlib
import zipfile

import pytest

import zipp

PATTERNS = ['**', '**/*', '**/*.txt', '*.txt']


def _build_layout(base_writer):
    """
    Populate a layout with a root-level file alongside nested files/dirs:

    .
    ├── a.txt
    ├── other.bin
    └── b
        ├── c.txt
        └── d
            └── e.txt

    ``base_writer`` is called with (relative posix path, content bytes)
    for each file to create.
    """
    base_writer('a.txt', b'root')
    base_writer('other.bin', b'root binary')
    base_writer('b/c.txt', b'nested')
    base_writer('b/d/e.txt', b'deeply nested')


@pytest.fixture
def real_dir(tmp_path):
    def write(rel, content):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    _build_layout(write)
    return tmp_path


@pytest.fixture
def zip_root():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        _build_layout(lambda rel, content: zf.writestr(rel, content))
    return zipp.Path(buffer)


def _pathlib_results(base, pattern):
    """
    Relative, POSIX-separated paths matched by pathlib, directories
    suffixed with '/' to align with zipp.Path's string form. Excludes the
    root itself, which pathlib's '**' includes but zip archives have no
    entry for.
    """
    results = set()
    for match in base.glob(pattern):
        if match == base:
            continue
        rel = match.relative_to(base).as_posix()
        if match.is_dir():
            rel += '/'
        results.add(rel)
    return results


def _zipp_results(root, pattern):
    return {match.at for match in root.glob(pattern)}


@pytest.mark.parametrize('pattern', PATTERNS)
def test_glob_matches_pathlib(real_dir, zip_root, pattern):
    """
    zipp.Path.glob() should agree with pathlib.Path.glob() (current,
    Python 3.13+ semantics) on which entries a pattern matches, including
    root-level files for a non-trailing '**' segment.
    """
    expected = _pathlib_results(pathlib.Path(real_dir), pattern)
    actual = _zipp_results(zip_root, pattern)
    assert actual == expected


def test_glob_star_star_slash_txt_includes_root_file(zip_root):
    """
    Directly pins the gh-102 regression: '**/*.txt' must match a
    root-level file, not just nested ones.
    """
    names = {match.at for match in zip_root.glob('**/*.txt')}
    assert 'a.txt' in names
    assert 'b/c.txt' in names
    assert 'b/d/e.txt' in names
