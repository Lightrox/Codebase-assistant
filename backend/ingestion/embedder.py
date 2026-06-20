import os
import cohere

# Initialize Cohere client using environment variable
# Set COHERE_API_KEY in your .env file (local) or Render's Environment tab (production)
API_KEY = os.getenv("COHERE_API_KEY")
if not API_KEY:
    raise ValueError("COHERE_API_KEY environment variable not set")

_client = None


def get_client() -> cohere.Client:
    """Initialize Cohere client once and reuse it."""
    global _client
    if _client is None:
        print("[Embedder] Initializing Cohere client...")
        _client = cohere.Client(api_key=API_KEY)
        print("[Embedder] Cohere client ready.")
    return _client


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embeds a list of code chunks using Cohere's embed API.
    Batches requests in groups of 90 (Cohere's per-request limit).
    
    Args:
        chunks: list of dicts with "code" key
        
    Returns:
        Same chunks list with "embedding" key added to each chunk
    """
    if not chunks:
        print("[Embedder] No chunks to embed.")
        return []

    client = get_client()
    texts = [chunk["code"] for chunk in chunks]
    
    print(f"[Embedder] Embedding {len(texts)} chunks using Cohere...")
    
    # Batch in groups of 90 (Cohere's per-request limit)
    batch_size = 90
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        print(f"[Embedder] Processing batch {batch_num}/{total_batches} ({len(batch_texts)} texts)...")
        
        response = client.embed(
            texts=batch_texts,
            model="embed-english-light-v3.0",
            input_type="search_document"
        )
        all_embeddings.extend(response.embeddings)
    
    # Attach embedding back to each chunk
    for chunk, embedding in zip(chunks, all_embeddings):
        chunk["embedding"] = embedding
    
    print(f"[Embedder] Done. Each vector has {len(all_embeddings[0])} dimensions.")
    return chunks


def embed_query(query: str) -> list[float]:
    """
    Embeds a single user query using Cohere's embed API.
    Uses input_type="search_query" for better retrieval quality.
    
    Args:
        query: the user's question/search query
        
    Returns:
        Embedding vector as list of floats
    """
    client = get_client()
    print(f"[Embedder] Embedding query...")
    
    response = client.embed(
        texts=[query],
        model="embed-english-light-v3.0",
        input_type="search_query"
    )
    
    embedding = response.embeddings[0]
    print(f"[Embedder] Query embedding complete ({len(embedding)} dimensions).")
    return embedding