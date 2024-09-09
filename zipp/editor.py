import os
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
