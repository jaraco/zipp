import re


def translate(pattern):
    """
    Given a glob pattern, produce a regex that matches it.
    """
    return extend(translate_core(pattern))


def extend(pattern):
    r"""
    Extend regex for pattern-wide concerns.

    Apply '(?s:)' to create a non-matching group that
    matches newlines (valid on Unix).

    Append '\Z' to imply fullmatch even when match is used.
    """
    return rf'(?s:{pattern})\Z'


def translate_core(pattern):
    r"""
    Given a glob pattern, produce a regex that matches it.

    >>> translate_core('*.txt')
    '[^/]*\\.txt'
    >>> translate_core('a?txt')
    'a[^/]txt'
    >>> translate_core('**/*')
    '.*/[^/]*'
    """
    return ''.join(map(replace, separate(pattern)))


def separate(pattern):
    """
    Separate out character sets to avoid translating their contents.

    >>> [m.group(0) for m in separate('*.txt')]
    ['*.txt']
    >>> [m.group(0) for m in separate('a[?]txt')]
    ['a', '[?]', 'txt']
    """
    return re.finditer(r'([^\[]+)|(?P<set>[\[].*?[\]])|([\[][^\]]*$)', pattern)


def replace(match):
    """
    Perform the replacements for a match from :func:`separate`.
    """

    return match.group('set') or (
        re.escape(match.group(0))
        .replace('\\*\\*', r'.*')
        .replace('\\*', r'[^/]*')
        .replace('\\?', r'[^/]')
    )
