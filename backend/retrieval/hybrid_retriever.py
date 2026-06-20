from retrieval import bm25_index
from retrieval import chroma_store
from ingestion import embedder

def retrieve(question: str, top_k: int = 5) -> list[dict]:
    """
    Retrieves the top_k most relevant chunks using a hybrid search of
    BM25 (keyword search) and ChromaDB (semantic search), fused with RRF.

    Args:
        question: user's query/question string
        top_k: number of chunks to return

    Returns:
        List of merged chunk results sorted by RRF score.
    """
    # Fetch slightly more candidates from each search to improve RRF fusion overlap
    candidate_k = max(top_k * 2, 10)

    # 1. BM25 Search
    try:
        bm25_results = bm25_index.search(question, top_k=candidate_k)
    except Exception as e:
        print(f"[HybridRetriever] BM25 search failed: {e}")
        bm25_results = []

    # 2. Semantic Search
    try:
        query_embedding = embedder.embed_query(question)
        semantic_results = chroma_store.query(query_embedding, top_k=candidate_k)
    except Exception as e:
        print(f"[HybridRetriever] ChromaStore search failed: {e}")
        semantic_results = []

    # 3. Reciprocal Rank Fusion (RRF)
    # Score(d) = sum_{m in models} 1 / (k + rank_m(d))
    k = 60
    rrf_scores = {}
    doc_map = {}

    def get_doc_key(doc: dict) -> tuple:
        return (doc["file"], doc["start_line"], doc["end_line"])

    # Rank BM25 results
    for rank, doc in enumerate(bm25_results, 1):
        key = get_doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k + rank))

    # Rank Semantic results
    for rank, doc in enumerate(semantic_results, 1):
        key = get_doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k + rank))

    if not rrf_scores:
        return []

    # Sort documents by their RRF score descending
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    # Compile the final top_k results
    final_results = []
    for key in sorted_keys[:top_k]:
        doc = doc_map[key]
        doc["score"] = round(rrf_scores[key], 6)
        final_results.append(doc)

    print(f"[HybridRetriever] Fused {len(bm25_results)} keyword and {len(semantic_results)} semantic results into {len(final_results)} chunks.")
    return final_results