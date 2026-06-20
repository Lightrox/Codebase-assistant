from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from models import IngestRequest, IngestResponse, QueryRequest, QueryResponse
from ingestion.cloner import clone_repo, delete_repo
from ingestion.file_walker import walk_files
from ingestion.ast_chunker import chunk_all_files
from ingestion.embedder import embed_chunks
from retrieval.chroma_store import store, clear as clear_chroma
from retrieval.bm25_index import build as build_bm25, clear as clear_bm25, load_from_cache
from retrieval.hybrid_retriever import retrieve
from llm.generator import generate

app = FastAPI(
    title="Codebase Assistant",
    description="Chat with any GitHub repository in plain English",
    version="1.0.0"
)

# Allow React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default port
        "https://Lightrox.github.io",  # GitHub Pages
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    """Load BM25 index from disk cache on server startup."""
    load_from_cache()


@app.get("/")
def root():
    return {"message": "Codebase Assistant is running. POST /ingest to start."}


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest):
    """
    Clones the repo, chunks all files, embeds them,
    and stores everything in ChromaDB + BM25 index.

    This is the heavy endpoint — takes 30s to 2min depending on repo size.
    """

    repo_path = None

    try:
        # Step 1 — Clone
        repo_path = clone_repo(request.repo_url)

        # Step 2 — Walk files
        files = walk_files(repo_path)
        if not files:
            raise HTTPException(status_code=400, detail="No supported code files found in repo.")

        # Step 3 — Chunk
        chunks = chunk_all_files(files)

        # Step 4 — Embed
        chunks = embed_chunks(chunks)

        # Step 5 — Clear old data, store new
        clear_chroma()
        clear_bm25()
        store(chunks)
        build_bm25(chunks)

        return IngestResponse(
            message=f"Successfully ingested {len(chunks)} chunks from {len(files)} files.",
            total_chunks=len(chunks),
            total_files=len(files)
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Always clean up cloned repo from disk
        if repo_path:
            delete_repo(repo_path)


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """
    Retrieves relevant code chunks and generates a grounded answer.
    Fast endpoint — typically responds in 1-3 seconds.
    """

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # Step 1 — Hybrid retrieval
        chunks = retrieve(request.question, top_k=5)

        if not chunks:
            raise HTTPException(status_code=404, detail="No relevant code found. Try ingesting a repo first.")

        # Step 2 — Generate answer
        result = generate(request.question, chunks)

        return QueryResponse(
            answer=result["answer"],
            citations=result["citations"]
        )

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clear")
def clear():
    """
    Wipes ChromaDB and BM25 index.
    Call this before ingesting a new repo.
    """
    clear_chroma()
    clear_bm25()
    return {"message": "All indexes cleared."}