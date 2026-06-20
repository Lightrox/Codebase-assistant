import pickle
import os
from rank_bm25 import BM25Okapi

# In-memory BM25 index — rebuilt each time a repo is ingested
_bm25: BM25Okapi = None
_chunks: list[dict] = []          # keeps original chunks for retrieval

INDEX_CACHE_PATH = "./bm25_index.pkl"


def _tokenize(text: str) -> list[str]:
    """
    Simple tokenizer — lowercases and splits on non-alphanumeric chars.
    Good enough for code: splits "PeerManager" → ["PeerManager"]
    and "peer_manager" → ["peer", "manager"]
    """
    import re
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def build(chunks: list[dict]):
    """
    Builds a BM25 index from all code chunks.
    Called once during ingestion, after chunking.

    Args:
        chunks: list of chunk dicts from ast_chunker
    """
    global _bm25, _chunks

    if not chunks:
        print("[BM25] No chunks to build index.")
        _bm25 = None
        _chunks = []
        if os.path.exists(INDEX_CACHE_PATH):
            try:
                os.remove(INDEX_CACHE_PATH)
            except Exception:
                pass
        return

    _chunks = chunks
    tokenized = [_tokenize(chunk["code"]) for chunk in chunks]

    _bm25 = BM25Okapi(tokenized)

    # Cache to disk so it survives if the server restarts
    with open(INDEX_CACHE_PATH, "wb") as f:
        pickle.dump({"bm25": _bm25, "chunks": _chunks}, f)

    print(f"[BM25] Index built with {len(chunks)} chunks.")


def load_from_cache():
    """
    Loads the BM25 index from disk if available.
    Called on server startup so we don't lose the index on restart.
    """
    global _bm25, _chunks

    if os.path.exists(INDEX_CACHE_PATH):
        try:
            with open(INDEX_CACHE_PATH, "rb") as f:
                data = pickle.load(f)
                _bm25  = data["bm25"]
                _chunks = data["chunks"]
            print(f"[BM25] Loaded index from cache ({len(_chunks)} chunks).")
        except Exception as e:
            print(f"[BM25] Failed to load index from cache: {e}")
    else:
        print("[BM25] No cache found. Ingest a repo first.")


def search(query: str, top_k: int = 5) -> list[dict]:
    """
    Searches the BM25 index for keyword-matching chunks.

    Args:
        query:  user's question string
        top_k:  number of results to return

    Returns:
        List of result dicts with a 'score' key (BM25 score, not normalized):
        [
            {
                "code":       "class PeerManager { ...",
                "file":       "src/peer/PeerManager.java",
                "start_line": 10,
                "end_line":   120,
                "score":      4.72
            },
            ...
        ]
    """
    if _bm25 is None or not _chunks:
        print("[BM25] Index not built yet or empty. Call build() first.")
        return []

    tokens = _tokenize(query)
    scores = _bm25.get_scores(tokens)

    # Pair each chunk with its score, sort descending
    scored = sorted(
        zip(_chunks, scores),
        key=lambda x: x[1],
        reverse=True
    )

    results = []
    for chunk, score in scored[:top_k]:
        results.append({
            "code":       chunk["code"],
            "file":       chunk["file"],
            "start_line": chunk["start_line"],
            "end_line":   chunk["end_line"],
            "score":      round(float(score), 4)
        })

    return results


def clear():
    """
    Clears the in-memory index and deletes disk cache.
    Called before re-ingesting a new repo.
    """
    global _bm25, _chunks
    _bm25   = None
    _chunks = []

    if os.path.exists(INDEX_CACHE_PATH):
        try:
            os.remove(INDEX_CACHE_PATH)
        except Exception:
            pass

    print("[BM25] Index cleared.")
