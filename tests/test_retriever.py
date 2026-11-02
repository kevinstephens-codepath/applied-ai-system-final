import pytest

from rag_retriever import Retriever, chunk_markdown, parse_heading, tokenize


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


# --- chunking ---

def test_chunk_markdown_splits_on_h2_and_skips_preamble():
    text = "# Title\nintro text\n\n## R-TEST-01: First\nbody one\n\n## Second thing\nbody two\n"
    chunks = chunk_markdown(text, "x.md")
    assert [c.chunk_id for c in chunks] == ["R-TEST-01", "second-thing"]
    assert chunks[0].rule_id == "R-TEST-01"
    assert chunks[1].rule_id is None
    assert "intro text" not in chunks[0].text
    assert "body one" in chunks[0].text
    assert chunks[0].source == "x.md"


def test_parse_heading_requires_rule_id_shape():
    assert parse_heading("R-SCORE-01: Score formula") == ("R-SCORE-01", "R-SCORE-01")
    assert parse_heading("B-10: Score could go negative") == ("B-10", "B-10")
    chunk_id, rule_id = parse_heading("Note: something else")
    assert rule_id is None and chunk_id == "note-something-else"


def test_tokenize_drops_stopwords():
    tokens = tokenize("The scores are what I cannot see after another guess")
    assert len(tokens) == 3  # scores, see, guess
    assert not {"the", "are", "what", "after", "another", "cannot"} & set(tokens)


def test_tokenize_matches_word_forms():
    for a, b in [("score", "scores"), ("attempt", "attempts"), ("guess", "guesses"),
                 ("lose", "losing"), ("type", "typed"), ("score", "scored")]:
        assert tokenize(a) == tokenize(b), (a, b)


def test_docs_load_with_unique_ids(retriever):
    ids = [c.chunk_id for c in retriever.chunks]
    assert len(ids) == len(set(ids))
    assert {"R-SCORE-01", "B-10", "S-RERUN-02"} <= set(ids)


# --- search ---

def _top(retriever, query):
    results = retriever.search(query)
    return results[0].chunk_id if results else None


@pytest.mark.parametrize("query, expected", [
    ("my score went negative after a few wrong guesses", "B-10"),
    ("hint says go higher when my guess is too high", "B-02"),
    ("I typed 45.7 and the game said I won", "B-06"),
    ("new game button does nothing after I win", "B-07"),
    ("changing difficulty does not reset the game", "R-DIFF-03"),
    ("attempts left is one lower than the limit", "R-DIFF-02"),
    ("empty guess uses up an attempt", "B-05"),
    ("After I lose on Easy mode the New Game button does nothing and I cannot start another round.", "B-07"),
    ("When I typed 45.7 and the secret was 45, the game said I won. Why does the decimal count as a correct guess?", "B-06"),
])
def test_symptom_query_finds_matching_entry(retriever, query, expected):
    assert _top(retriever, query) == expected


def test_attempts_query_also_returns_known_bug(retriever):
    ids = [c.chunk_id for c in retriever.search("attempts left is one lower than the limit")]
    assert "B-04" in ids


def test_score_query_also_returns_spec_rule(retriever):
    ids = [c.chunk_id for c in retriever.search("score goes negative")]
    assert "R-SCORE-01" in ids


def test_out_of_scope_feature_hits_scope_rule(retriever):
    assert _top(retriever, "can I play multiplayer with a leaderboard") == "R-SCOPE-01"


@pytest.mark.parametrize("query", [
    "what's the weather in Paris",
    "the score of the Lakers game tonight",     # shares words with the docs but is off-topic
    "show me a picture of a cat",
    "my python install is broken and pip fails",
    "",
    "   ",
    "the a an of",
])
def test_unrelated_or_empty_query_returns_no_chunks(retriever, query):
    assert retriever.search(query) == []


def test_results_sorted_scored_and_limited(retriever):
    results = retriever.search("score attempts difficulty hint", k=3)
    assert 0 < len(results) <= 3
    scores = [c.score for c in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s <= 1 for s in scores)


def test_min_score_gates_results(retriever):
    assert retriever.search("score goes negative", min_score=1.1) == []


def test_empty_corpus_returns_nothing():
    assert Retriever(chunks=[]).search("score") == []
