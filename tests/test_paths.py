import pytest

from mitten.paths import PathPattern


@pytest.mark.parametrize(
    "pattern, path",
    [
        ("/test", "/test"),
        ("/test/", "/test"),
        ("/users/:id", "/users/42"),
        ("/users/:id/posts/:postId", "/users/42/posts/7"),
        ("/files/:*", "/files/a/b/c"),
        ("/users/:id/:*", "/users/42/posts/extra"),
        ("/a/:*", "/a"),  # :* matches zero segments
        ("/a/b/:*", "/a/b"),
        ("/a/:*/ignored", "/a/b/c"),  # anything after :* is ignored
        ("/users/a b", "/users/a%20b"),  # the request path is decoded
        ("/users/a%20b", "/users/a%20b"),  # and so is the pattern
        ("/s\u00f6ka", "/s%C3%B6ka"),
        ("/files/:name", "/files/a%2Fb"),  # an encoded slash stays in its segment
    ],
)
def test_matches(pattern, path):
    assert PathPattern.parse(pattern).matches(path)


@pytest.mark.parametrize(
    "pattern, path",
    [
        ("/test", "/other"),
        ("/api/people/1", "/test"),
        ("/users/:id", "/users/42/posts"),
        ("/users/:*/extra", "/other/thing"),
        ("/a/b/:*", "/a"),  # the segments before :* are required
        ("/a/b/:*", "/a/c"),
        ("/files/a/b", "/files/a%2Fb"),
    ],
)
def test_does_not_match(pattern, path):
    assert not PathPattern.parse(pattern).matches(path)


@pytest.mark.parametrize(
    "more, less",
    [
        ("/users/me", "/users/:id"),
        ("/users/:id/orders", "/users/:*"),
        ("/users/:*", "/:*"),
        ("/a/:x/c", "/:y/b/c"),
        ("/a", "/a/:*"),
        ("/a/b/:*", "/a/:*"),
        ("/a/:id", "/a/:*"),
    ],
)
def test_specificity_order(more, less):
    assert PathPattern.parse(more).specificity > PathPattern.parse(less).specificity


def test_param_names_dont_change_specificity():
    assert PathPattern.parse("/a/:id").specificity == PathPattern.parse("/a/:name").specificity
