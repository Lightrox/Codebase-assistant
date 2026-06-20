# Codebase Assistant

Chat with any GitHub repository in plain English. Paste a repo URL, and ask
questions like *"how does peer discovery work?"* — get grounded answers with
exact file and line citations.

Built and demoed on a [BitTorrent client](#) implemented from scratch in Java
(full wire protocol, SHA-1 piece verification, rarest-first piece selection).

## How it works

```
GitHub URL
   │
   ▼
Clone repo ──▶ Walk files ──▶ Chunk at function boundaries (AST for Python,
                                regex for Java/JS/Go/C++)
   │
   ▼
Embed each chunk (sentence-transformers, local, free)
   │
   ▼
Store in ChromaDB (semantic) + BM25 index (keyword)
   │
   ▼
Question ──▶ Hybrid retrieval (RRF fusion of both) ──▶ LLM (Groq) ──▶ Answer + citations
```

## Why hybrid search

Pure semantic search misses exact identifiers — searching `PeerManager` might
return "connection handler" instead of the actual class. Pure keyword search
misses paraphrased questions. Combining both with **Reciprocal Rank Fusion**
covers both blind spots.

## Why AST-based chunking

Naive RAG splits text by character count, which cuts functions in half and
destroys meaning. This project parses each file's structure and chunks at
function/class boundaries, so every chunk passed to the LLM is a complete,
self-contained unit of code.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI | Async, auto-generated docs at `/docs` |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Free, local, no API key |
| Vector store | ChromaDB | Zero-setup, persistent, local |
| Keyword search | BM25 (`rank-bm25`) | Catches exact identifier matches |
| LLM | Groq (`llama3-8b-8192`) | Fast, free tier, open-source model |
| Frontend | React + Vite | Lightweight chat UI |

## Project structure

```
backend/
├── main.py                 FastAPI routes (/ingest, /query, /clear)
├── models.py                Pydantic request/response schemas
├── ingestion/
│   ├── cloner.py            Clones GitHub repo
│   ├── file_walker.py       Finds supported code files
│   ├── ast_chunker.py       Splits files into functions/classes
│   └── embedder.py          Generates embeddings
├── retrieval/
│   ├── chroma_store.py      Semantic vector search
│   ├── bm25_index.py        Keyword search
│   └── hybrid_retriever.py  RRF fusion of both
└── llm/
    └── generator.py         Builds prompt, calls Groq, returns citations

frontend/
└── src/
    ├── App.jsx
    └── components/
        ├── RepoInput.jsx     Repo URL input + ingestion status
        ├── ChatBox.jsx        Chat interface
        └── CodeBlock.jsx      Citation display
```

## Running locally

**Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on Windows
pip install -r requirements.txt
# add your GROQ_API_KEY to .env
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Backend docs available at `http://localhost:8000/docs`.

## Running with Docker

```bash
docker build -t codebase-assistant .
docker run -p 8000:8000 --env-file backend/.env codebase-assistant
```

## API

| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Clone, chunk, embed, and index a GitHub repo |
| `/query` | POST | Ask a question, get an answer with citations |
| `/clear` | DELETE | Wipe the current index |

## Future improvements

- JWT auth + per-user search history
- Support for multi-repo ingestion
- Retrieval evaluation suite (precision@k on a golden Q&A set)
- Swap ChromaDB → Qdrant for production-scale deployments
