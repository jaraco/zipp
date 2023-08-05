import os
import re


_default_seps = os.sep + str(os.altsep) * bool(os.altsep)


class Translator:
    seps: str

    def __init__(self, seps: str = _default_seps):
        assert seps in ('/', '\\', '\\/')
        self.seps = _default_seps

    def translate(self, pattern):
        """
        Given a glob pattern, produce a regex that matches it.
        """
        return self.extend(self.translate_core(pattern))

    def extend(self, pattern):
        r"""
        Extend regex for pattern-wide concerns.

        Apply '(?s:)' to create a non-matching group that
        matches newlines (valid on Unix).

        Append '\Z' to imply fullmatch even when match is used.
        """
        return rf'(?s:{pattern})\Z'

    def translate_core(self, pattern):
        r"""
        Given a glob pattern, produce a regex that matches it.

        >>> t = Translator()
        >>> t.translate_core('*.txt').replace('\\\\', '')
        '[^/]*\\.txt'
        >>> t.translate_core('a?txt')
        'a[^/]txt'
        >>> t.translate_core('**/*').replace('\\\\', '')
        '.*/[^/]*'
        """
        return ''.join(map(self.replace, separate(pattern)))

    def replace(self, match):
        """
        Perform the replacements for a match from :func:`separate`.
        """
        return match.group('set') or (
            re.escape(match.group(0))
            .replace('\\*\\*', r'.*')
            .replace('\\*', rf'[^{re.escape(self.seps)}]*')
            .replace('\\?', r'[^/]')
        )


def separate(pattern):
    """
    Separate out character sets to avoid translating their contents.

    >>> [m.group(0) for m in separate('*.txt')]
    ['*.txt']
    >>> [m.group(0) for m in separate('a[?]txt')]
    ['a', '[?]', 'txt']
    """
    return re.finditer(r'([^\[]+)|(?P<set>[\[].*?[\]])|([\[][^\]]*$)', pattern)
