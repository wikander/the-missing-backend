import pytest
from missingbe import MissingBe

@pytest.fixture
def sut(monkeypatch):
    monkeypatch.setattr(MissingBe, "loadResponseFiles", lambda *_: None)
    return MissingBe()

def test_exact_match(sut):
    assert sut.comparePaths("/test", "/test") == {}

def test_no_match(sut):
    assert sut.comparePaths("/test", "/other") is None

def test_different_length(sut):
    assert sut.comparePaths("/api/people/1", "/test") is None

def test_single_param(sut):
    assert sut.comparePaths("/users/:id", "/users/42") == {"id": "42"}

def test_multiple_params(sut):
    assert sut.comparePaths("/users/:id/posts/:postId", "/users/42/posts/7") == {"id": "42", "postId": "7"}

def test_wildcard(sut):
    assert sut.comparePaths("/files/:*", "/files/a/b/c") == {}

def test_wildcard_with_param_before(sut):
    assert sut.comparePaths("/users/:id/:*", "/users/42/posts/extra") == {"id": "42"}

def test_no_match_with_wildcard(sut):
    assert sut.comparePaths("/users/:*/extra", "/other/thing") is None

def test_no_match_different_structure(sut):
    assert sut.comparePaths("/api/people/1", "/test") is None