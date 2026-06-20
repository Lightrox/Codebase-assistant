import chromadb

# Single ChromaDB client shared across the app
_client = None
_collection = None

COLLECTION_NAME = "codebase"


def get_collection():
    global _client, _collection

    if _collection is None:
        # PersistentClient saves to disk so data survives restarts
        _client = chromadb.PersistentClient(path="./chroma_db")
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}   # cosine similarity
        )
        print(f"[ChromaStore] Collection ready: '{COLLECTION_NAME}'")

    return _collection


def store(chunks: list[dict]):
    """
    Stores embedded chunks into ChromaDB.

    Args:
        chunks: list of chunk dicts with 'embedding' key attached
    """
    if not chunks:
        print("[ChromaStore] No chunks to store.")
        return

    collection = get_collection()

    ids         = [chunk["chunk_id"]  for chunk in chunks]
    embeddings  = [chunk["embedding"] for chunk in chunks]
    documents   = [chunk["code"]      for chunk in chunks]
    metadatas   = [
        {
            "file":       chunk["file"],
            "start_line": chunk["start_line"],
            "end_line":   chunk["end_line"],
        }
        for chunk in chunks
    ]

    # Upsert so re-ingesting the same repo doesn't duplicate
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )

    print(f"[ChromaStore] Stored {len(chunks)} chunks.")


def query(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """
    Finds the top-k most semantically similar chunks.

    Args:
        query_embedding: vector from embedder.embed_query()
        top_k: number of results to return

    Returns:
        List of result dicts:
        [
            {
                "code":       "def connect(): ...",
                "file":       "src/PeerConnection.java",
                "start_line": 42,
                "end_line":   78,
                "score":      0.91     ← cosine similarity
            },
            ...
        ]
    """
    collection = get_collection()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    # Handle empty/missing results
    if not results or not results.get("documents") or not results["documents"][0]:
        return []

    # Unpack ChromaDB's nested response format
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        chunks.append({
            "code":       doc,
            "file":       meta["file"],
            "start_line": meta["start_line"],
            "end_line":   meta["end_line"],
            "score":      round(1 - dist, 4)   # convert distance → similarity
        })

    return chunks


def clear():
    """
    Wipes the entire collection — called before re-ingesting a new repo.
    """
    global _collection
    collection = get_collection()
    
    # Safely clear by deleting and re-creating the collection
    global _client
    if _client is not None:
        try:
            _client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    _collection = None
    get_collection()
    print(f"[ChromaStore] Collection cleared.")
