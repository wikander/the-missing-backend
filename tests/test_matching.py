import pytest

from tests.helpers import make_flow, with_mocks


def test_method_must_match_case_insensitively(sut):
    with_mocks(sut, {"path": "/test", "method": "post"})
    assert sut.find_mock(make_flow("POST")) is not None
    assert sut.find_mock(make_flow("GET")) is None

def test_method_array_matches_each_method(sut):
    with_mocks(sut, {"path": "/test", "method": ["GET", "DELETE"]})
    assert sut.find_mock(make_flow("DELETE")) is not None
    assert sut.find_mock(make_flow("GET")) is not None
    assert sut.find_mock(make_flow("POST")) is None

def test_head_uses_get_mocks(sut):
    with_mocks(sut, {"path": "/test", "method": ["GET", "POST"]}, {"path": "/other", "method": "POST"})
    assert sut.find_mock(make_flow("HEAD", body=b"")) is not None
    assert sut.find_mock(make_flow("HEAD", path="/other", body=b"")) is None

def test_query_string_is_ignored_when_matching(sut):
    with_mocks(sut, {"path": "/test", "method": "GET"})
    assert sut.find_mock(make_flow(path="/test?a=1")) is not None


def best_match(sut, path, *patterns):
    with_mocks(sut, *({"path": p, "method": "GET"} for p in patterns))
    picks = {sut.find_mock(make_flow(path=path)).path.text for _ in range(50)}
    return picks.pop() if len(picks) == 1 else picks

@pytest.mark.parametrize("path, patterns, winner", [
    ("/users/me", ["/users/:id", "/users/me"], "/users/me"),
    ("/users/1/orders", ["/users/:*", "/users/:id/orders"], "/users/:id/orders"),
    ("/users/1", ["/:*", "/users/:*"], "/users/:*"),
    ("/a/b/c", ["/:y/b/c", "/a/:x/c"], "/a/:x/c"),
    ("/a", ["/a/:*", "/a"], "/a"),
    ("/a/b", ["/a/:*", "/a/b/:*"], "/a/b/:*"),
    ("/a/b", ["/a/:*", "/a/:id"], "/a/:id"),
])
def test_most_specific_pattern_wins(sut, path, patterns, winner):
    assert best_match(sut, path, *patterns) == winner

def test_equally_specific_patterns_are_variants(sut):
    with_mocks(sut, {"path": "/a/:id", "method": "GET"}, {"path": "/a/:id", "method": "GET"},
               {"path": "/:*", "method": "GET"})
    picks = {sut.find_mock(make_flow(path="/a/1")).source for _ in range(100)}
    assert picks == {"mitten-mock-0.json", "mitten-mock-1.json"}

def test_differently_named_params_are_variants(sut):
    assert best_match(sut, "/a/1", "/a/:id", "/a/:name") == {"/a/:id", "/a/:name"}

def test_less_specific_mock_used_for_other_methods(sut):
    with_mocks(sut, {"path": "/users/me", "method": "POST"}, {"path": "/users/:id", "method": "GET"})
    assert sut.find_mock(make_flow(path="/users/me")).path.text == "/users/:id"
