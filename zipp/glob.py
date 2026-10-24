import fnmatch
import os
import re

from .compat.py313 import legacy_end_marker

_default_seps = os.sep + str(os.altsep) * bool(os.altsep)


class Translator:
    """
    >>> Translator('xyz')
    Traceback (most recent call last):
    ...
    AssertionError: Invalid separators

    >>> Translator('')
    Traceback (most recent call last):
    ...
    AssertionError: Invalid separators
    """

    seps: str

    #: Placeholder for a non-trailing '**/' segment (including its trailing
    #: separator), substituted back in :meth:`translate_core` after the rest
    #: of the pattern has been translated. Kept out of the way of the
    #: character classes used elsewhere in this module (no '*', '?', '/',
    #: '[', or ']'), and left untouched by :func:`re.escape`.
    any_dirs_sentinel = '\x00'

    def __init__(self, seps: str = _default_seps):
        assert seps and set(seps) <= set(_default_seps), "Invalid separators"
        self.seps = seps

    def translate(self, pattern):
        """
        Given a glob pattern, produce a regex that matches it.
        """
        return self.extend(self.match_dirs(self.translate_core(pattern)))

    @legacy_end_marker
    def extend(self, pattern):
        r"""
        Extend regex for pattern-wide concerns.

        Apply '(?s:)' to create a non-matching group that
        matches newlines (valid on Unix).

        Append '\z' to imply fullmatch even when match is used.
        """
        return rf'(?s:{pattern})\z'

    def match_dirs(self, pattern):
        """
        Ensure that zipfile.Path directory names are matched.

        zipfile.Path directory names always end in a slash.
        """
        return rf'{pattern}[/]?'

    def translate_core(self, pattern):
        r"""
        Given a glob pattern, produce a regex that matches it.

        >>> t = Translator()
        >>> t.translate_core('*.txt').replace('\\\\', '')
        '[^/]*\\.txt'
        >>> t.translate_core('a?txt')
        'a[^/]txt'
        >>> t.translate_core('**/*').replace('\\\\', '')
        '(?:.*[/])?[^/][^/]*'
        >>> t.translate_core('**').replace('\\\\', '')
        '.*'
        >>> t.translate_core('a/**').replace('\\\\', '')
        'a/.*'
        """
        self.restrict_rglob(pattern)
        core = ''.join(
            map(self.replace, separate(self.mark_any_dirs(self.star_not_empty(pattern))))
        )
        seps_pattern = rf'[{re.escape(self.seps)}]'
        return core.replace(self.any_dirs_sentinel, rf'(?:.*{seps_pattern})?')

    def replace(self, match):
        """
        Perform the replacements for a match from :func:`separate`.
        """
        handler = self._replace_set if match.group('set') else self._replace_plain
        return handler(match.group(0))

    def _replace_set(self, character_set):
        r"""
        Translate a character set using shell-style semantics.

        Glob character sets treat a leading ``!`` as negation and ``^``
        as a literal (unlike regex), so defer to fnmatch, but guard
        against matching a separator.

        >>> Translator('/')._replace_set('[!a]')
        '(?![/])[^a]'
        >>> Translator('/')._replace_set('[^a]')
        '(?![/])[\\^a]'
        """
        translated = _strip_fnmatch(fnmatch.translate(character_set))
        return rf'(?![{re.escape(self.seps)}]){translated}'

    def _replace_plain(self, text):
        """
        Escape the text, translating any wildcards.
        """
        return (
            re
            .escape(text)
            .replace('\\*\\*', r'.*')
            .replace('\\*', rf'[^{re.escape(self.seps)}]*')
            .replace('\\?', r'[^/]')
        )

    def restrict_rglob(self, pattern):
        """
        Raise ValueError if ** appears in anything but a full path segment.

        >>> Translator().translate('**foo')
        Traceback (most recent call last):
        ...
        ValueError: ** must appear alone in a path segment
        """
        seps_pattern = rf'[{re.escape(self.seps)}]+'
        segments = re.split(seps_pattern, pattern)
        if any('**' in segment and segment != '**' for segment in segments):
            raise ValueError("** must appear alone in a path segment")

    def mark_any_dirs(self, pattern):
        r"""
        Replace non-trailing '**' segments (i.e. those followed by a
        separator and more pattern) with a sentinel, so that after the
        remainder of the pattern is translated, the sentinel can be
        expanded into a regex alternative that matches zero *or more*
        path segments, per glob's and pathlib's documented '**' semantics.

        A trailing bare '**' (nothing follows it) is left alone; its
        existing translation to '.*' already matches zero or more of
        anything, directories included.

        >>> t = Translator()
        >>> t.mark_any_dirs('**/*.txt') == t.any_dirs_sentinel + '*.txt'
        True
        >>> t.mark_any_dirs('a/**/b') == 'a/' + t.any_dirs_sentinel + 'b'
        True
        >>> t.mark_any_dirs('a/**') == 'a/**'
        True
        >>> t.mark_any_dirs('**') == '**'
        True
        """
        seps_pattern = rf'[{re.escape(self.seps)}]'
        return re.sub(rf'[*]{{2}}{seps_pattern}', self.any_dirs_sentinel, pattern)

    def star_not_empty(self, pattern):
        """
        Ensure that * will not match an empty segment.
        """

        def handle_segment(match):
            segment = match.group(0)
            return '?*' if segment == '*' else segment

        not_seps_pattern = rf'[^{re.escape(self.seps)}]+'
        return re.sub(not_seps_pattern, handle_segment, pattern)


def separate(pattern):
    """
    Separate out character sets to avoid translating their contents.

    >>> [m.group(0) for m in separate('*.txt')]
    ['*.txt']
    >>> [m.group(0) for m in separate('a[?]txt')]
    ['a', '[?]', 'txt']
    """
    return re.finditer(r'([^\[]+)|(?P<set>[\[].*?[\]])|([\[][^\]]*$)', pattern)


def _strip_fnmatch(translated):
    r"""
    Strip fnmatch's outer group and end marker.

    >>> _strip_fnmatch(r'(?s:[^a])\z')
    '[^a]'
    >>> _strip_fnmatch(r'(?s:[^a])\Z')
    '[^a]'
    """
    return re.fullmatch(r'\(\?s:(.*)\)\\[zZ]', translated, re.DOTALL).group(1)
