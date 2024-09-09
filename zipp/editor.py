import os
import pathlib
import platform
import posixpath
import shlex
import subprocess
from importlib.resources import as_file

from zipp.compat.overlay import zipfile

from jaraco.ui.main import main


def edit(path: pathlib.Path):
    default_editor = dict(Windows='start').get(platform.system(), 'edit')
    editor = shlex.split(os.environ.get('EDITOR', default_editor))
    orig = path.stat()
    try:
        res = subprocess.call([*editor, path])
    except Exception as exc:
        print(f"Error launching editor {editor}")
        print(exc)
        return
    if res != 0:
        return
    return path.stat() != orig


def split_all(path):
    """
    recursively call os.path.split until we have all of the components
    of a pathname suitable for passing back to os.path.join.
    """
    drive, path = os.path.splitdrive(path)
    head, tail = os.path.split(path)
    terminators = [os.path.sep, os.path.altsep, '']
    parts = split_all(head) if head not in terminators else [head]
    return [drive] + parts + [tail]


def split(path):
    """
    Given a path to an item in a zip file, return a path to the file and
    the path to the part.

    Assuming /foo.zipx exists as a file.

    >>> mp = getfixture('monkeypatch')
    >>> mp.setattr(os.path, 'isfile', lambda fn: fn == '/foo.zipx')

    >>> split('/foo.zipx/dir/part')
    ('/foo.zipx', 'dir/part')

    >>> split('/foo.zipx')
    ('/foo.zipx', '')
    """
    path_components = split_all(path)

    def get_assemblies():
        """
        Enumerate the various combinations of file paths and part paths
        """
        for n in range(len(path_components), 0, -1):
            file_c = path_components[:n]
            part_c = path_components[n:] or ['']
            yield (os.path.join(*file_c), posixpath.join(*part_c))

    for file_path, part_path in get_assemblies():
        if os.path.isfile(file_path):
            return file_path, part_path


@main
def cmd(path: str):
    zf = zipfile.Path(*split(path))
    with as_file(zf) as tmp_file:
        if edit(tmp_file):
            zf.root.close()
            with zipfile.ZipFile(zf.root.filename, 'a') as repl:
                repl.write(tmp_file, zf.at)
