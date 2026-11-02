"""Heading-based chunking and BM25 search over the markdown knowledge base in docs/."""

import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_DOCS_DIR = Path(__file__).parent / "docs"
DEFAULT_K = 4
# The best chunk must reach this normalized score (0-1) or the search returns nothing. Chosen with
# a threshold sweep over eval/eval_cases.json: lower recalls more real reports but lets more
# off-topic ones through (the model's "not_covered" verdict and the Low-confidence caveat handle those).
DEFAULT_MIN_SCORE = 0.13
# Once the best chunk clears the threshold, lower-ranked chunks only need this fraction of it.
RELATED_FRACTION = 0.75

K1 = 1.5
B = 0.75
HEADING_BOOST = 2  # heading tokens are repeated this many extra times in the index

STOPWORDS = frozenset(
    """a an and are as at be but by can did do does for from has have how i if in is it its
    me my not of on or so that the then there this to was were what when where which why will
    with would you your
    about after again also another any because been being can cannot could didn doesn don get got
    into isn just s should some still t than their them they we wasn while""".split()
)

_RULE_ID = re.compile(r"^[A-Z]+(?:-[A-Z0-9]+)+$")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str
    heading: str
    chunk_id: str
    rule_id: str | None
    score: float = 0.0


# Irregular forms the suffix rules cannot join (the docs say "lost"/"won", users say "lose"/"win").
_IRREGULAR = {"lost": "lose", "won": "win", "ran": "run", "began": "begin"}


def _stem(token: str) -> str:
    """Crude stemmer: only needs to map word forms of the same word to the same token."""
    token = _IRREGULAR.get(token, token)
    if token.endswith(("sses", "xes", "ches", "shes")):
        token = token[:-2]
    elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        token = token[:-1]
    else:
        for suffix in ("ing", "ed"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                token = token[: -len(suffix)]
                break
    # Drop a trailing "e" so lose/losing, score/scored, type/typed share a stem.
    if token.endswith("e") and len(token) > 3:
        token = token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords, lightly stem."""
    return [_stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


def parse_heading(heading: str) -> tuple[str, str | None]:
    """Return (chunk_id, rule_id) for a '## ' heading like 'R-SCORE-01: Score formula'."""
    head, sep, _ = heading.partition(":")
    if sep and _RULE_ID.match(head.strip()):
        return head.strip(), head.strip()
    slug = "-".join(_TOKEN.findall(heading.lower()))
    return slug, None


def chunk_markdown(text: str, source: str) -> list[Chunk]:
    """Split markdown on '## ' headings. Text before the first '## ' is not a chunk."""
    chunks = []
    heading, lines = None, []

    def flush():
        if heading is None:
            return
        body = "\n".join(lines).strip()
        chunk_id, rule_id = parse_heading(heading)
        chunks.append(Chunk(f"## {heading}\n{body}", source, heading, chunk_id, rule_id))

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            heading, lines = line[3:].strip(), []
        elif heading is not None:
            lines.append(line)
    flush()
    return chunks


def load_chunks(docs_dir: Path | str = DEFAULT_DOCS_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.name))
    return chunks


class Retriever:
    """BM25 index over chunks. Scores are normalized to 0-1 so a threshold is meaningful."""

    def __init__(self, docs_dir: Path | str = DEFAULT_DOCS_DIR, chunks: list[Chunk] | None = None):
        self.chunks = chunks if chunks is not None else load_chunks(docs_dir)
        self._tf = []
        for c in self.chunks:
            tokens = tokenize(c.text) + tokenize(c.heading) * HEADING_BOOST
            self._tf.append(Counter(tokens))
        self._len = [sum(tf.values()) for tf in self._tf]
        n = len(self.chunks)
        self._avg_len = (sum(self._len) / n) if n else 0.0
        df = Counter(t for tf in self._tf for t in tf)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        # Terms absent from the corpus get the highest possible idf, so off-topic words
        # lower the normalized score instead of being ignored.
        self._max_idf = math.log(1 + (n + 0.5) / 0.5) if n else 0.0

    def _raw_score(self, query_terms: list[str], i: int) -> float:
        tf, dl = self._tf[i], self._len[i]
        score = 0.0
        for t in query_terms:
            f = tf.get(t, 0)
            if f:
                norm = f + K1 * (1 - B + B * dl / self._avg_len)
                score += self._idf[t] * f * (K1 + 1) / norm
        return score

    def search(self, query: str, k: int = DEFAULT_K, min_score: float = DEFAULT_MIN_SCORE) -> list[Chunk]:
        """Top-k chunks, best first, with scores normalized to 0-1.

        The best chunk must score at least min_score, otherwise the result is empty. An empty
        list means "no grounding found" and feeds the no-context guardrail.
        """
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not self.chunks:
            return []
        # Best possible score per term is idf * (K1 + 1); the sum bounds the raw score.
        bound = sum(self._idf.get(t, self._max_idf) for t in terms) * (K1 + 1)
        scored = []
        for i, chunk in enumerate(self.chunks):
            raw = self._raw_score(terms, i)
            if raw > 0:
                scored.append(replace(chunk, score=round(min(raw / bound, 1.0), 4)))
        scored.sort(key=lambda c: c.score, reverse=True)
        if not scored or scored[0].score < min_score:
            return []
        related_floor = min_score * RELATED_FRACTION
        return [c for c in scored if c.score >= related_floor][:k]
