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
        '.*/[^/][^/]*'
        """
        self.restrict_rglob(pattern)
        return self.assemble(self.tokenize(self.star_not_empty(pattern)))

    def tokenize(self, pattern):
        """
        Yield (greedy, regex) pairs for each piece of pattern, where
        greedy marks a ``*`` whose ``[^/]*`` may backtrack against a
        neighboring ``*`` in the same path segment.
        """
        for match in separate(pattern):
            captured = match.group('set')
            if captured:
                yield False, captured
                continue
            text = match.group(0)
            i = 0
            while i < len(text):
                if text.startswith('**', i):
                    yield False, r'.*'
                    i += 2
                elif text[i] == '*':
                    yield True, rf'[^{re.escape(self.seps)}]*'
                    i += 1
                elif text[i] == '?':
                    yield False, r'[^/]'
                    i += 1
                else:
                    yield False, re.escape(text[i])
                    i += 1

    def assemble(self, tokens):
        """
        Join translated tokens into a regex.

        When two ``*`` stars sit in the same path segment, the leading
        one is committed with an atomic group so that ``*a*a*...`` can no
        longer backtrack exponentially against a non-matching name.
        """
        tokens = list(tokens)
        res = []
        i = 0
        while i < len(tokens):
            greedy, regex = tokens[i]
            if not greedy:
                res.append(regex)
                i += 1
                continue
            j = i + 1
            fixed = []
            while j < len(tokens) and not tokens[j][0] and '/' not in tokens[j][1]:
                fixed.append(tokens[j][1])
                j += 1
            if j < len(tokens) and tokens[j][0]:
                name = f'g{len(res)}'
                res.append(f'(?=(?P<{name}>{regex}?{"".join(fixed)}))(?P={name})')
                i = j
            else:
                res.append(regex)
                res.extend(fixed)
                i = j
        return ''.join(res)

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
