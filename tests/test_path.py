import gc
import io
import itertools
import pathlib
import pickle
import posixpath
import stat
import sys
import unittest
import warnings
import weakref
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

import jaraco.itertools
from jaraco.functools import compose
from test.support.os_helper import FakePath, temp_dir

from zipp.compat.overlay import zipfile

from ._test_params import Invoked, parameterize
from .compat.py313 import ForArchive


def _make_link(info: zipfile.ZipInfo):  # type: ignore[name-defined]
    info.external_attr |= stat.S_IFLNK << 16


def build_alpharep_fixture():
    """
    Create a zip file with this structure:

    .
    ├── a.txt
    ├── n.txt (-> a.txt)
    ├── b
    │   ├── c.txt
    │   ├── d
    │   │   └── e.txt
    │   └── f.txt
    ├── g
    │   └── h
    │       └── i.txt
    └── j
        ├── k.bin
        ├── l.baz
        └── m.bar

    This fixture has the following key characteristics:

    - a file at the root (a)
    - a file two levels deep (b/d/e)
    - multiple files in a directory (b/c, b/f)
    - a directory containing only a directory (g/h)
    - a directory with files of different extensions (j/klm)
    - a symlink (n) pointing to (a)

    "alpha" because it uses alphabet
    "rep" because it's a representative example
    """
    data = io.BytesIO()
    zf = zipfile.ZipFile(data, "w")
    zf.writestr("a.txt", b"content of a")
    zf.writestr("b/c.txt", b"content of c")
    zf.writestr("b/d/e.txt", b"content of e")
    zf.writestr("b/f.txt", b"content of f")
    zf.writestr("g/h/i.txt", b"content of i")
    zf.writestr("j/k.bin", b"content of k")
    zf.writestr("j/l.baz", b"content of l")
    zf.writestr("j/m.bar", b"content of m")
    zf.writestr("n.txt", b"a.txt")
    _make_link(zf.infolist()[-1])

    zf.filename = "alpharep.zip"
    return zf


alpharep_generators = [
    Invoked.wrap(build_alpharep_fixture),
    Invoked.wrap(compose(zipfile._path.CompleteDirs.inject, build_alpharep_fixture)),
]

pass_alpharep = parameterize(['alpharep'], alpharep_generators)


class TestPath(unittest.TestCase):
    def zipfile_ondisk(self, alpharep):
        tmpdir = pathlib.Path(self.enterContext(temp_dir()))
        buffer = alpharep.fp
        alpharep.close()
        path = tmpdir / alpharep.filename
        with path.open("wb") as strm:
            strm.write(buffer.getvalue())
        return path

    @pass_alpharep
    def test_iterdir_and_types(self, alpharep):
        root = zipfile.Path(alpharep)
        assert root.is_dir()
        a, n, b, g, j = root.iterdir()  # noqa: RUF059
        assert a.is_file()
        assert b.is_dir()
        assert g.is_dir()
        c, f, d = b.iterdir()
        assert c.is_file() and f.is_file()
        (e,) = d.iterdir()
        assert e.is_file()
        (h,) = g.iterdir()
        (i,) = h.iterdir()
        assert i.is_file()

    @pass_alpharep
    def test_is_file_missing(self, alpharep):
        root = zipfile.Path(alpharep)
        assert not root.joinpath('missing.txt').is_file()

    @pass_alpharep
    def test_iterdir_on_file(self, alpharep):
        root = zipfile.Path(alpharep)
        a, n, b, g, j = root.iterdir()  # noqa: RUF059
        with self.assertRaises(NotADirectoryError):
            a.iterdir()

    @pass_alpharep
    def test_subdir_is_dir(self, alpharep):
        root = zipfile.Path(alpharep)
        assert (root / 'b').is_dir()
        assert (root / 'b/').is_dir()
        assert (root / 'g').is_dir()
        assert (root / 'g/').is_dir()

    @pass_alpharep
    def test_open(self, alpharep):
        root = zipfile.Path(alpharep)
        a, n, b, g, j = root.iterdir()  # noqa: RUF059
        with a.open(encoding="utf-8") as strm:
            data = strm.read()
        self.assertEqual(data, "content of a")
        with a.open('r', "utf-8") as strm:  # not a kw, no gh-101144 TypeError
            data = strm.read()
        self.assertEqual(data, "content of a")

    def test_open_encoding_utf16(self):
        in_memory_file = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(in_memory_file, "w"))
        zf.writestr("path/16.txt", "This was utf-16".encode("utf-16"))
        zf.filename = "test_open_utf16.zip"
        root = zipfile.Path(zf)
        (path,) = root.iterdir()
        u16 = path.joinpath("16.txt")
        with u16.open('r', "utf-16") as strm:
            data = strm.read()
        assert data == "This was utf-16"
        with u16.open(encoding="utf-16") as strm:
            data = strm.read()
        assert data == "This was utf-16"

    def test_open_encoding_errors(self):
        in_memory_file = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(in_memory_file, "w"))
        zf.writestr("path/bad-utf8.bin", b"invalid utf-8: \xff\xff.")
        zf.filename = "test_read_text_encoding_errors.zip"
        root = zipfile.Path(zf)
        (path,) = root.iterdir()
        u16 = path.joinpath("bad-utf8.bin")

        # encoding= as a positional argument for gh-101144.
        data = u16.read_text("utf-8", errors="ignore")
        assert data == "invalid utf-8: ."
        with u16.open("r", "utf-8", errors="surrogateescape") as f:
            assert f.read() == "invalid utf-8: \udcff\udcff."

        # encoding= both positional and keyword is an error; gh-101144.
        with self.assertRaisesRegex(TypeError, "encoding"):
            data = u16.read_text("utf-8", encoding="utf-8")

        # both keyword arguments work.
        # error during decoding with wrong codec.
        with (
            u16.open("r", encoding="utf-8", errors="strict") as f,
            self.assertRaises(UnicodeDecodeError),
        ):
            f.read()

    @unittest.skipIf(
        not getattr(sys.flags, 'warn_default_encoding', 0),
        "Requires warn_default_encoding",
    )
    @pass_alpharep
    def test_encoding_warnings(self, alpharep):
        """EncodingWarning must blame the read_text and open calls."""
        assert sys.flags.warn_default_encoding
        root = zipfile.Path(alpharep)
        with self.assertWarns(EncodingWarning) as wc:
            root.joinpath("a.txt").read_text()
        assert __file__ == wc.filename
        with self.assertWarns(EncodingWarning) as wc:
            root.joinpath("a.txt").open("r").close()
        assert __file__ == wc.filename

    def test_open_write(self):
        """
        If the zipfile is open for write, it should be possible to
        write bytes or text to it.
        """
        zip_file = self.enterContext(zipfile.ZipFile(io.BytesIO(), mode='w'))
        zf = zipfile.Path(zip_file)
        with zf.joinpath('file.bin').open('wb') as strm:
            strm.write(b'binary contents')
        with zf.joinpath('file.txt').open('w', encoding="utf-8") as strm:
            strm.write('text file')

    @pass_alpharep
    def test_open_extant_directory(self, alpharep):
        """
        Attempting to open a directory raises IsADirectoryError.
        """
        zf = zipfile.Path(alpharep)
        with self.assertRaises(IsADirectoryError):
            zf.joinpath('b').open()

    @pass_alpharep
    def test_open_binary_invalid_args(self, alpharep):
        root = zipfile.Path(alpharep)
        with self.assertRaises(ValueError):
            root.joinpath('a.txt').open('rb', encoding='utf-8')
        with self.assertRaises(ValueError):
            root.joinpath('a.txt').open('rb', 'utf-8')

    @pass_alpharep
    def test_open_missing_directory(self, alpharep):
        """
        Attempting to open a missing directory raises FileNotFoundError.
        """
        zf = zipfile.Path(alpharep)
        with self.assertRaises(FileNotFoundError):
            zf.joinpath('z').open()

    @pass_alpharep
    def test_read(self, alpharep):
        root = zipfile.Path(alpharep)
        a, n, b, g, j = root.iterdir()  # noqa: RUF059
        assert a.read_text(encoding="utf-8") == "content of a"
        # Also check positional encoding arg (gh-101144).
        assert a.read_text("utf-8") == "content of a"
        assert a.read_bytes() == b"content of a"

    @pass_alpharep
    def test_joinpath(self, alpharep):
        root = zipfile.Path(alpharep)
        a = root.joinpath("a.txt")
        assert a.is_file()
        e = root.joinpath("b").joinpath("d").joinpath("e.txt")
        assert e.read_text(encoding="utf-8") == "content of e"

    @pass_alpharep
    def test_joinpath_multiple(self, alpharep):
        root = zipfile.Path(alpharep)
        e = root.joinpath("b", "d", "e.txt")
        assert e.read_text(encoding="utf-8") == "content of e"

    @pass_alpharep
    def test_traverse_truediv(self, alpharep):
        root = zipfile.Path(alpharep)
        a = root / "a.txt"
        assert a.is_file()
        e = root / "b" / "d" / "e.txt"
        assert e.read_text(encoding="utf-8") == "content of e"

    @pass_alpharep
    def test_pathlike_construction(self, alpharep):
        """
        zipfile.Path should be constructable from a path-like object
        """
        zipfile_ondisk = self.zipfile_ondisk(alpharep)
        pathlike = FakePath(str(zipfile_ondisk))
        root = zipfile.Path(pathlike)
        root.root.close()

    @pass_alpharep
    def test_traverse_pathlike(self, alpharep):
        root = zipfile.Path(alpharep)
        root / FakePath("a")

    @pass_alpharep
    def test_parent(self, alpharep):
        root = zipfile.Path(alpharep)
        assert (root / 'a').parent.at == ''
        assert (root / 'a' / 'b').parent.at == 'a/'

    @pass_alpharep
    def test_dir_parent(self, alpharep):
        root = zipfile.Path(alpharep)
        assert (root / 'b').parent.at == ''
        assert (root / 'b/').parent.at == ''

    @pass_alpharep
    def test_missing_dir_parent(self, alpharep):
        root = zipfile.Path(alpharep)
        assert (root / 'missing dir/').parent.at == ''

    @pass_alpharep
    def test_mutability(self, alpharep):
        """
        If the underlying zipfile is changed, the Path object should
        reflect that change.
        """
        root = zipfile.Path(alpharep)
        a, n, b, g, j = root.iterdir()  # noqa: RUF059
        alpharep.writestr('foo.txt', 'foo')
        alpharep.writestr('bar/baz.txt', 'baz')
        assert any(child.name == 'foo.txt' for child in root.iterdir())
        assert (root / 'foo.txt').read_text(encoding="utf-8") == 'foo'
        (baz,) = (root / 'bar').iterdir()
        assert baz.read_text(encoding="utf-8") == 'baz'

    HUGE_ZIPFILE_NUM_ENTRIES = 2**13

    def huge_zipfile(self):
        """Create a read-only zipfile with a huge number of entries."""
        strm = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(strm, "w"))
        for entry in map(str, range(self.HUGE_ZIPFILE_NUM_ENTRIES)):
            zf.writestr(entry, entry)
        zf.mode = 'r'
        return zf

    def test_joinpath_constant_time(self):
        """
        Ensure joinpath on items in zipfile is linear time.
        """
        root = zipfile.Path(self.huge_zipfile())
        entries = jaraco.itertools.Counter(root.iterdir())
        for entry in entries:
            entry.joinpath('suffix')
        # Check the file iterated all items
        assert entries.count == self.HUGE_ZIPFILE_NUM_ENTRIES

    @pass_alpharep
    def test_read_does_not_close(self, alpharep):
        alpharep = self.zipfile_ondisk(alpharep)
        with zipfile.ZipFile(alpharep) as file:
            for rep in range(2):
                zipfile.Path(file, 'a.txt').read_text(encoding="utf-8")

    @pass_alpharep
    def test_subclass(self, alpharep):
        class Subclass(zipfile.Path):
            pass

        root = Subclass(alpharep)
        assert isinstance(root / 'b', Subclass)

    def test_at(self):
        zip_file = self.enterContext(zipfile.ZipFile(io.BytesIO(), 'w'))
        root = zipfile.Path(zip_file)
        assert root.at == ''
        assert (root / 'foo' / 'bar').at == 'foo/bar'

    def test_str(self):
        """
        An unnamed zip file is indicated by ":zipfile:"
        """
        zip_file = self.enterContext(zipfile.ZipFile(io.BytesIO(), 'w'))
        root = zipfile.Path(zip_file)
        assert str(root) == ':zipfile:'
        assert str(root / 'foo' / 'bar') == ':zipfile:/foo/bar'

    @pass_alpharep
    def test_filename(self, alpharep):
        root = zipfile.Path(alpharep)
        assert root.filename == pathlib.Path('alpharep.zip')

    @pass_alpharep
    def test_root_name(self, alpharep):
        """
        The name of the root should be the name of the zipfile
        """
        root = zipfile.Path(alpharep)
        assert root.name == 'alpharep.zip' == root.filename.name

    @pass_alpharep
    def test_root_on_disk(self, alpharep):
        """
        The name/stem of the root should match the zipfile on disk.

        This condition must hold across platforms.
        """
        root = zipfile.Path(self.zipfile_ondisk(alpharep))
        assert root.name == 'alpharep.zip' == root.filename.name
        assert root.stem == 'alpharep' == root.filename.stem
        root.root.close()

    @pass_alpharep
    def test_suffix(self, alpharep):
        """
        The suffix of the root should be the suffix of the zipfile.
        The suffix of each nested file is the final component's last suffix, if any.
        Includes the leading period, just like pathlib.Path.
        """
        root = zipfile.Path(alpharep)
        assert root.suffix == '.zip' == root.filename.suffix

        b = root / "b.txt"
        assert b.suffix == ".txt"

        c = root / "c" / "filename.tar.gz"
        assert c.suffix == ".gz"

        d = root / "d"
        assert d.suffix == ""

    @pass_alpharep
    def test_suffixes(self, alpharep):
        """
        The suffix of the root should be the suffix of the zipfile.
        The suffix of each nested file is the final component's last suffix, if any.
        Includes the leading period, just like pathlib.Path.
        """
        root = zipfile.Path(alpharep)
        assert root.suffixes == ['.zip'] == root.filename.suffixes

        b = root / 'b.txt'
        assert b.suffixes == ['.txt']

        c = root / 'c' / 'filename.tar.gz'
        assert c.suffixes == ['.tar', '.gz']

        d = root / 'd'
        assert d.suffixes == []

        e = root / '.hgrc'
        assert e.suffixes == []

    @pass_alpharep
    def test_suffix_no_filename(self, alpharep):
        alpharep.filename = None
        root = zipfile.Path(alpharep)
        assert root.joinpath('example').suffix == ""
        assert root.joinpath('example').suffixes == []

    @pass_alpharep
    def test_stem(self, alpharep):
        """
        The final path component, without its suffix
        """
        root = zipfile.Path(alpharep)
        assert root.stem == 'alpharep' == root.filename.stem

        b = root / "b.txt"
        assert b.stem == "b"

        c = root / "c" / "filename.tar.gz"
        assert c.stem == "filename.tar"

        d = root / "d"
        assert d.stem == "d"

        assert (root / ".gitignore").stem == ".gitignore"

    @pass_alpharep
    def test_root_parent(self, alpharep):
        root = zipfile.Path(alpharep)
        assert root.parent == pathlib.Path('.')
        root.root.filename = 'foo/bar.zip'
        assert root.parent == pathlib.Path('foo')

    @pass_alpharep
    def test_root_unnamed(self, alpharep):
        """
        It is an error to attempt to get the name
        or parent of an unnamed zipfile.
        """
        alpharep.filename = None
        root = zipfile.Path(alpharep)
        with self.assertRaises(TypeError):
            root.name
        with self.assertRaises(TypeError):
            root.parent

        # .name and .parent should still work on subs
        sub = root / "b"
        assert sub.name == "b"
        assert sub.parent

    @pass_alpharep
    def test_match_and_glob(self, alpharep):
        root = zipfile.Path(alpharep)
        assert not root.match("*.txt")

        assert list(root.glob("b/c.*")) == [zipfile.Path(alpharep, "b/c.txt")]
        assert list(root.glob("b/*.txt")) == [
            zipfile.Path(alpharep, "b/c.txt"),
            zipfile.Path(alpharep, "b/f.txt"),
        ]

    @pass_alpharep
    def test_glob_recursive(self, alpharep):
        root = zipfile.Path(alpharep)
        files = root.glob("**/*.txt")
        assert all(each.match("*.txt") for each in files)

        assert list(root.glob("**/*.txt")) == list(root.rglob("*.txt"))

    @pass_alpharep
    def test_glob_dirs(self, alpharep):
        root = zipfile.Path(alpharep)
        assert list(root.glob('b')) == [zipfile.Path(alpharep, "b/")]
        assert list(root.glob('b*')) == [zipfile.Path(alpharep, "b/")]

    @pass_alpharep
    def test_glob_subdir(self, alpharep):
        root = zipfile.Path(alpharep)
        assert list(root.glob('g/h')) == [zipfile.Path(alpharep, "g/h/")]
        assert list(root.glob('g*/h*')) == [zipfile.Path(alpharep, "g/h/")]

    @pass_alpharep
    def test_glob_subdirs(self, alpharep):
        root = zipfile.Path(alpharep)

        assert list(root.glob("*/i.txt")) == []
        assert list(root.rglob("*/i.txt")) == [zipfile.Path(alpharep, "g/h/i.txt")]

    @pass_alpharep
    def test_glob_does_not_overmatch_dot(self, alpharep):
        root = zipfile.Path(alpharep)

        assert list(root.glob("*.xt")) == []

    @pass_alpharep
    def test_glob_single_char(self, alpharep):
        root = zipfile.Path(alpharep)

        assert list(root.glob("a?txt")) == [zipfile.Path(alpharep, "a.txt")]
        assert list(root.glob("a[.]txt")) == [zipfile.Path(alpharep, "a.txt")]
        assert list(root.glob("a[?]txt")) == []

    @pass_alpharep
    def test_glob_chars(self, alpharep):
        root = zipfile.Path(alpharep)

        assert list(root.glob("j/?.b[ai][nz]")) == [
            zipfile.Path(alpharep, "j/k.bin"),
            zipfile.Path(alpharep, "j/l.baz"),
        ]

    @parameterize(
        ['alpharep', 'pattern', 'expected'],
        [
            (alpharep, pattern, expected)
            for alpharep in alpharep_generators
            for pattern, expected in [
                ('[!a].txt', {'n.txt'}),
                ('[!an].txt', set()),
                ('[!b]', {'g/', 'j/'}),
                ('j/[!k].b*', {'j/l.baz', 'j/m.bar'}),
                ('j/[^k].b*', {'j/k.bin'}),
                ('j/[!k-l].b*', {'j/m.bar'}),
                ('j/[k-l].b*', {'j/k.bin', 'j/l.baz'}),
                ('b[!x]c.txt', set()),
            ]
        ],
    )
    def test_glob_character_class_syntax(self, alpharep, pattern, expected):
        root = zipfile.Path(alpharep)
        assert {path.at for path in root.glob(pattern)} == expected

    def test_glob_empty(self):
        zip_file = self.enterContext(zipfile.ZipFile(io.BytesIO(), 'w'))
        root = zipfile.Path(zip_file)
        with self.assertRaises(ValueError):
            root.glob('')

    @pass_alpharep
    def test_eq_hash(self, alpharep):
        root = zipfile.Path(alpharep)
        assert root == zipfile.Path(alpharep)

        assert root != (root / "a.txt")
        assert (root / "a.txt") == (root / "a.txt")

        root = zipfile.Path(alpharep)
        assert root in {root}

    @pass_alpharep
    def test_is_symlink(self, alpharep):
        root = zipfile.Path(alpharep)
        assert not root.joinpath('a.txt').is_symlink()
        assert root.joinpath('n.txt').is_symlink()

    @pass_alpharep
    def test_relative_to(self, alpharep):
        root = zipfile.Path(alpharep)
        relative = root.joinpath("b", "c.txt").relative_to(root / "b")
        assert str(relative) == "c.txt"

        relative = root.joinpath("b", "d", "e.txt").relative_to(root / "b")
        assert str(relative) == "d/e.txt"

    @pass_alpharep
    def test_inheritance(self, alpharep):
        cls = type('PathChild', (zipfile.Path,), {})
        file = cls(alpharep).joinpath('some dir').parent
        assert isinstance(file, cls)

    @parameterize(
        ['alpharep', 'path_type', 'subpath'],
        itertools.product(
            alpharep_generators,
            [str, FakePath],
            ['', 'b/'],
        ),
    )
    def test_pickle(self, alpharep, path_type, subpath):
        zipfile_ondisk = path_type(str(self.zipfile_ondisk(alpharep)))
        root = zipfile.Path(zipfile_ondisk, at=subpath)
        saved_1 = pickle.dumps(root)
        root.root.close()
        restored_1 = pickle.loads(saved_1)
        first, *_rest = restored_1.iterdir()
        assert first.read_text(encoding='utf-8').startswith('content of ')
        restored_1.root.close()

    @pass_alpharep
    def test_extract_orig_with_implied_dirs(self, alpharep):
        """
        A zip file wrapped in a Path should extract even with implied dirs.
        """
        source_path = self.zipfile_ondisk(alpharep)
        zf = zipfile.ZipFile(source_path)
        # wrap the zipfile for its side effect
        zipfile.Path(zf)
        zf.extractall(source_path.parent)
        zf.close()

    @pass_alpharep
    def test_getinfo_missing(self, alpharep):
        """
        Validate behavior of getinfo on original zipfile after wrapping.
        """
        zipfile.Path(alpharep)
        with self.assertRaises(KeyError):
            alpharep.getinfo('does-not-exist')

    def test_malformed_paths(self):
        """
        Path should handle malformed paths gracefully.

        Paths with leading slashes are not visible.

        Paths with dots are treated like regular files.
        """
        data = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(data, "w"))
        zf.writestr("/one-slash.txt", b"content")
        zf.writestr("//two-slash.txt", b"content")
        zf.writestr("../parent.txt", b"content")
        zf.filename = ''
        root = zipfile.Path(zf)
        assert list(map(str, root.iterdir())) == ['../']
        assert root.joinpath('..').joinpath('parent.txt').read_bytes() == b'content'

    def test_unsupported_names(self):
        """
        Path segments with special characters are readable.

        On some platforms or file systems, characters like
        ``:`` and ``?`` are not allowed, but they are valid
        in the zip file.
        """
        data = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(data, "w"))
        zf.writestr("path?", b"content")
        zf.writestr("V: NMS.flac", b"fLaC...")
        zf.filename = ''
        root = zipfile.Path(zf)
        contents = root.iterdir()
        assert next(contents).name == 'path?'
        assert next(contents).name == 'V: NMS.flac'
        assert root.joinpath('V: NMS.flac').read_bytes() == b"fLaC..."

    def test_backslash_not_separator(self):
        """
        In a zip file, backslashes are not separators.
        """
        data = io.BytesIO()
        zf = self.enterContext(zipfile.ZipFile(data, "w"))
        zf.writestr(DirtyZipInfo("foo\\bar")._for_archive(zf), b"content")
        zf.filename = ''
        root = zipfile.Path(zf)
        (first,) = root.iterdir()
        assert not first.is_dir()
        assert first.name == 'foo\\bar'

    @pass_alpharep
    def test_interface(self, alpharep):
        from importlib.resources.abc import Traversable

        zf = zipfile.Path(alpharep)
        assert isinstance(zf, Traversable)


class DirtyZipInfo(zipfile.ZipInfo, ForArchive):  # type: ignore[name-defined]
    """
    Bypass name sanitization.
    """

    def __init__(self, filename, *args, **kwargs):
        super().__init__(filename, *args, **kwargs)
        self.filename = filename


class TestDirectoryIndex(unittest.TestCase):
    def make_path(self, names, path_type=zipfile.Path):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as zf, warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            for name in names:
                zf.writestr(DirtyZipInfo(name)._for_archive(zf), b'content')
        zf = self.enterContext(zipfile.ZipFile(data))
        zf.filename = 'index.zip'
        return path_type(zf)

    def test_order_and_duplicates(self):
        names = ['a/one', 'top', 'a/', 'a/two', 'a/one', 'b/leaf', 'empty/']
        root = self.make_path(names)
        assert [p.at for p in root.iterdir()] == ['top', 'a/', 'empty/', 'b/']
        assert [p.at for p in (root / 'a').iterdir()] == ['a/one', 'a/two', 'a/one']
        assert root.root.namelist() == names + ['b/']
        assert list((root / 'empty').iterdir()) == []
        assert list((root / 'missing/').iterdir()) == []

    def test_unusual_names(self):
        names = [
            'a//b//file',
            'a///',
            '/abs/file',
            '//double/file',
            '../up.txt',
            './dot.txt',
            'a/../q',
            'back\\slash',
            '/',
            '//',
            'unicodé/文件',
            'line\nbreak/file',
        ]
        root = self.make_path(names)
        reference = names + list(zipfile._path.CompleteDirs._implied_dirs(names))
        assert root.root.namelist() == reference
        queries = ['', '/', '//', 'missing/', 'a/', 'a//'] + [
            name for name in reference if name.endswith('/')
        ]
        for at in queries:
            with self.subTest(at=at):
                expected = [
                    name
                    for name in reference
                    if posixpath.dirname(name.rstrip('/')) == at.rstrip('/')
                ]
                assert [p.at for p in zipfile.Path(root.root, at).iterdir()] == expected

    def test_empty_archive(self):
        assert list(self.make_path([]).iterdir()) == []

    def test_file_directory_collision(self):
        root = self.make_path(['a', 'a/file'])
        assert [p.at for p in root.iterdir()] == ['a', 'a/']
        assert (root / 'a').is_file()
        assert [p.at for p in (root / 'a/').iterdir()] == ['a/file']
        with self.assertRaises(NotADirectoryError):
            (root / 'a').iterdir()

    def test_writable_modes(self):
        for mode in ['w', 'a', 'x']:
            with self.subTest(mode=mode), zipfile.ZipFile(io.BytesIO(), mode) as zf:
                root = zipfile.Path(zf)
                assert list(root.iterdir()) == []
                zf.writestr('a/first', b'first')
                (directory,) = root.iterdir()
                assert [p.at for p in directory.iterdir()] == ['a/first']
                zf.writestr('a/second', b'second')
                assert [p.at for p in directory.iterdir()] == ['a/first', 'a/second']

    def test_subclass_hooks(self):
        class AllEntries(zipfile.Path):
            def _is_child(self, path):
                return True

        class RenamedEntries(zipfile.Path):
            def _next(self, at):
                return super()._next('visible.txt')

        class BasenameEntries(zipfile.Path):
            def __init__(self, root, at=''):
                super().__init__(root, posixpath.basename(at.rstrip('/')))

        for cls in [AllEntries, RenamedEntries, BasenameEntries]:
            with self.subTest(cls=cls):
                root = self.make_path(['a/one', 'top'], cls)
                children = list(root.iterdir())
                assert len(children) == len(root.root.namelist())
                assert all(isinstance(child, cls) for child in children)

    def test_subclass_uses_original_listing(self):
        class SubPath(zipfile.Path):
            pass

        root = self.make_path(['a/one', 'top'], SubPath)
        children = list(root.iterdir())
        assert [child.at for child in children] == ['top', 'a/']
        assert all(isinstance(child, SubPath) for child in children)
        assert '_dir_index' not in root.root.__dict__

    def test_pickle_after_listing(self):
        directory = pathlib.Path(self.enterContext(temp_dir()))
        filename = directory / 'index.zip'
        with zipfile.ZipFile(filename, 'w') as zf:
            zf.writestr('a/file', b'content')
        root = zipfile.Path(filename)
        assert [p.at for p in root.iterdir()] == ['a/']
        saved = pickle.dumps(root)
        root.root.close()
        restored = pickle.loads(saved)
        self.addCleanup(restored.root.close)
        assert [p.at for p in restored.iterdir()] == ['a/']
        assert (restored / 'a' / 'file').read_bytes() == b'content'

    def test_recursive_iterdir_constructs_only_children(self):
        root = self.make_path([f'd{i}/f{j}' for i in range(100) for j in range(3)])
        original = zipfile.Path.__init__
        constructed = 0

        def counted_init(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            original(self, *args, **kwargs)

        with mock.patch.object(zipfile.Path, '__init__', counted_init):
            pending = [root]
            while pending:
                pending.extend(
                    child for child in pending.pop().iterdir() if child.is_dir()
                )
        assert constructed == 400

    def test_repeated_listings_do_not_rescan_names(self):
        root = self.make_path(['a/one', 'a/two', 'top'])
        list(root.iterdir())
        names = mock.MagicMock()
        names.__iter__.side_effect = AssertionError('Rescanned the archive namelist')
        with mock.patch.object(root.root, 'namelist', return_value=names):
            for _ in range(2):
                assert [p.at for p in root.iterdir()] == ['top', 'a/']
                directory = zipfile.Path(root.root, 'a/')
                assert [p.at for p in directory.iterdir()] == ['a/one', 'a/two']

    def test_nonlisting_operations_do_not_build_index(self):
        root = self.make_path(['a/one', 'top'])
        root.root.namelist()
        assert (root / 'a').exists()
        assert (root / 'top').read_text(encoding='utf-8') == 'content'
        assert [p.at for p in root.glob('a/*')] == ['a/one']
        assert '_dir_index' not in root.root.__dict__
        with self.assertRaises(NotADirectoryError):
            (root / 'top').iterdir()
        assert '_dir_index' not in root.root.__dict__

    def test_first_listing_builds_shared_index(self):
        root = self.make_path(['a/one', 'top'])
        assert '_dir_index' not in root.root.__dict__
        iterator = (root / 'a').iterdir()
        assert '_dir_index' in root.root.__dict__
        index = root.root._dir_index
        assert [p.at for p in iterator] == ['a/one']
        assert [p.at for p in root.iterdir()] == ['top', 'a/']
        assert root.root._dir_index is index

    def test_close_releases_index_and_preserves_metadata_listing(self):
        class Index(dict):
            pass

        root = self.make_path(['a/one', 'top'])
        iterator = root.iterdir()
        root.root._dir_index = Index(root.root._dir_index)
        index_ref = weakref.ref(root.root._dir_index)
        root.root.close()
        assert index_ref() is None
        assert '_dir_index' not in root.root.__dict__
        assert [p.at for p in iterator] == ['top', 'a/']
        assert [p.at for p in root.iterdir()] == ['top', 'a/']
        assert [p.at for p in (root / 'a').iterdir()] == ['a/one']
        assert '_dir_index' not in root.root.__dict__
        root.root.close()

    def test_close_during_index_construction_does_not_retain_index(self):
        root = self.make_path(['a/one', 'top'])
        names = root.root.namelist()

        def closing_names():
            root.root.close()
            return names

        with mock.patch.object(root.root, 'namelist', closing_names):
            assert [p.at for p in root.iterdir()] == ['top', 'a/']
        assert '_dir_index' not in root.root.__dict__

    def test_index_lifetime_follows_archive(self):
        class Index(dict):
            pass

        directory = pathlib.Path(self.enterContext(temp_dir()))
        filename = directory / 'index.zip'
        with zipfile.ZipFile(filename, 'w') as zf:
            zf.writestr('a/file', b'content')
        root = zipfile.Path(filename)
        list(root.iterdir())
        root.root._dir_index = Index(root.root._dir_index)
        index_ref = weakref.ref(root.root._dir_index)
        archive_ref = weakref.ref(root.root)
        stream = root.root.fp
        del root
        gc.collect()
        assert archive_ref() is None
        assert index_ref() is None
        assert stream.closed

    def test_concurrent_index_construction(self):
        root = self.make_path(['a/one', 'a/two'])
        barrier = Barrier(4)
        original = zipfile.ZipFile.namelist
        builds = []

        def names(archive):
            builds.append(archive)
            barrier.wait(timeout=10)
            return original(archive)

        def listing(_):
            return [p.at for p in zipfile.Path(root.root, 'a/').iterdir()]

        with (
            mock.patch.object(zipfile.ZipFile, 'namelist', names),
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            results = list(executor.map(listing, range(4)))
        assert results == [['a/one', 'a/two']] * 4
        assert len(builds) == 4
