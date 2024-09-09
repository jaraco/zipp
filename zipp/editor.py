import os
import posixpath
import subprocess
import sys
import tempfile


class EditableFile:
    def __init__(self, data=None):
        self.data = data

    def __enter__(self):
        fobj, self.name = tempfile.mkstemp()
        if self.data:
            os.write(fobj, self.data)
        os.close(fobj)
        return self

    def read(self):
        with open(self.name, 'rb') as f:
            return f.read()

    def __exit__(self, *tb_info):
        os.remove(self.name)

    def edit(self, ipath):
        self.changed = False
        with self:
            editor = self.get_editor(ipath)
            cmd = [editor, self.name]
            try:
                res = subprocess.call(cmd)
            except Exception as e:
                print("Error launching editor {editor}".format(**vars()))
                print(e)
                return
            if res != 0:
                return
            new_data = self.read()
            if new_data != self.data:
                self.changed = True
                self.data = new_data

    @staticmethod
    def get_editor(filepath):
        """
        Give preference to an XML_EDITOR or EDITOR defined in the
        environment. Otherwise use notepad on Windows and edit on other
        platforms.
        """
        default_editor = ['edit', 'notepad'][sys.platform.startswith('win32')]
        return os.environ.get(
            'XML_EDITOR',
            os.environ.get('EDITOR', default_editor),
        )


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


def find_file(path):
    """
    Given a path to a part in a zip file, return a path to the file and
    the path to the part.

    Assuming /foo.zipx exists as a file,

    >>> find_file('/foo.zipx/dir/part') # doctest: +SKIP
    ('/foo.zipx', '/dir/part')

    >>> find_file('/foo.zipx') # doctest: +SKIP
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
