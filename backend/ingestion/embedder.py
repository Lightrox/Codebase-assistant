from sentence_transformers import SentenceTransformer

# Using a lightweight model that works well for code
# Runs locally — no API key needed, completely free
MODEL_NAME = "all-MiniLM-L6-v2"

# Load once at module level so we don't reload on every request
_model = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"[Embedder] Loading model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
        print(f"[Embedder] Model loaded.")
    return _model


def embed_chunks(chunks: list[dict]) -> list[dict]:
    if not chunks:
        print("[Embedder] No chunks to embed.")
        return []

    model = get_model()

    # Extract just the code strings for batch encoding
    texts = [chunk["code"] for chunk in chunks]

    print(f"[Embedder] Embedding {len(texts)} chunks...")

    # Batch encode — much faster than one by one
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True
    )
    import numpy as np
    if isinstance(embeddings, np.ndarray):
        embeddings = embeddings.tolist()

    # Attach embedding back to each chunk
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    print(f"[Embedder] Done. Each vector has {len(embeddings[0])} dimensions.")
    return chunks


def embed_query(query: str) -> list[float]:
    model = get_model()
    res = model.encode(query)
    import numpy as np
    if isinstance(res, np.ndarray):
        return res.tolist()
    return res