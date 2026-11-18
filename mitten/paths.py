"""Path patterns: /users/:id, /files/:*, and which of several is most specific.

A pattern is parsed once, when its mock file loads, into segments that both
matching and the specificity ranking use, so the two can't disagree about
what a segment is.
"""

from dataclasses import dataclass
from functools import cached_property

# The specificity of each kind of segment: higher is more specific.
LITERAL_SEGMENT, PARAM_SEGMENT, PATTERN_END, WILDCARD_SEGMENT = 3, 2, 1, 0


def _segments(path: str) -> list[str]:
    """Path segments, ignoring empty ones, so trailing slashes don't matter."""
    return [p for p in path.split("/") if p]


def _is_wildcard(segment: str) -> bool:
    return segment.startswith(":*")


def _is_param(segment: str) -> bool:
    return segment.startswith(":")


@dataclass(frozen=True)
class PathPattern:
    """A mock's path pattern.

    - A literal segment matches itself.
    - :name matches exactly one segment.
    - :* matches the rest of the path, zero segments or more. Anything after
      it in the pattern is ignored.
    """

    text: str
    segments: tuple[str, ...]  # up to and including :*, if there is one
    has_wildcard: bool

    @classmethod
    def parse(cls, text: str) -> "PathPattern":
        segments = _segments(text)
        wildcard = next((i for i, s in enumerate(segments) if _is_wildcard(s)), None)
        if wildcard is not None:
            segments = segments[: wildcard + 1]
        return cls(text=text, segments=tuple(segments), has_wildcard=wildcard is not None)

    def __str__(self) -> str:
        return self.text

    def matches(self, path: str) -> bool:
        """Whether a request path, without its query string, matches."""
        parts = _segments(path)
        if self.has_wildcard:
            fixed = self.segments[:-1]
            if len(parts) < len(fixed):  # every segment before :* is required
                return False
        else:
            fixed = self.segments
            if len(parts) != len(fixed):
                return False
        return all(_is_param(s) or s == part for s, part in zip(fixed, parts))

    @cached_property
    def specificity(self) -> tuple[int, ...]:
        """A sort key: higher is more specific.

        Segments are compared left to right, and at the first that differs a
        literal beats a :param, which beats :*. A pattern without :* ends with
        PATTERN_END, so /a beats /a/:* for the path /a: two patterns matching
        the same path can only differ there by one ending where the other has
        :*.
        """
        key = []
        for segment in self.segments:
            if _is_wildcard(segment):
                key.append(WILDCARD_SEGMENT)
            elif _is_param(segment):
                key.append(PARAM_SEGMENT)
            else:
                key.append(LITERAL_SEGMENT)
        if not self.has_wildcard:
            key.append(PATTERN_END)
        return tuple(key)

