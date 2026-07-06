# Codebase Assistant — Complete Project Reference for LLMs

> **Purpose of this document**: A fully self-contained technical reference covering every file, function, data contract, design decision, and runtime behavior in the project. Intended to be pasted as context into an LLM before asking it to work on this codebase.

---

## 1. What the Project Does

**Codebase Assistant** is a Retrieval-Augmented Generation (RAG) system that lets users "chat" with any public GitHub repository in plain English. The user pastes a GitHub URL; the system clones it, indexes it, and then answers natural-language questions about the code with exact file + line citations.

Example: *"How does peer discovery work?"* → LLM answers citing `src/peer/PeerManager.java:42–120`.

The system is **not** a code-execution tool; it is a read-only code-understanding tool.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (React + Vite)            │
│  RepoInput.jsx ──POST /ingest──► App.jsx             │
│  ChatBox.jsx   ──POST /query───► CodeBlock.jsx       │
└─────────────────────────┬───────────────────────────┘
                          │ HTTP JSON
┌─────────────────────────▼───────────────────────────┐
│              BACKEND (FastAPI on Uvicorn)             │
│                                                      │
│  POST /ingest                POST /query             │
│  ──────────────              ─────────────           │
│  cloner.py                   hybrid_retriever.py     │
│  file_walker.py              ├── bm25_index.py       │
│  ast_chunker.py              ├── embedder.py         │
│  embedder.py                 └── chroma_store.py     │
│  chroma_store.py             generator.py            │
│  bm25_index.py                                       │
│                                                      │
│  Persistent storage:                                 │
│  ./chroma_db/       ← ChromaDB HNSW vector index    │
│  ./bm25_index.pkl   ← BM25 serialized index         │
└─────────────────────────────────────────────────────┘
         │ Cohere API          │ Groq API
         ▼                     ▼
   Embedding model       LLM (llama-3.1-8b-instant)
   embed-english-light-v3.0
```

---

## 3. Repository Layout

```
codebase-assistant/
├── Dockerfile                    # Production container (backend only)
├── README.md
├── backend/
│   ├── .env                      # GROQ_API_KEY, COHERE_API_KEY, GROQ_MODEL
│   ├── .env.example
│   ├── requirements.txt
│   ├── main.py                   # FastAPI app, all routes
│   ├── models.py                 # Pydantic request/response schemas
│   ├── bm25_index.pkl            # Auto-generated: serialized BM25 index
│   ├── chroma_db/                # Auto-generated: ChromaDB persistent store
│   ├── ingestion/
│   │   ├── cloner.py             # git clone → temp dir
│   │   ├── file_walker.py        # os.walk → filter supported files
│   │   ├── ast_chunker.py        # split files into function/class chunks
│   │   └── embedder.py           # Cohere embed API wrapper
│   ├── retrieval/
│   │   ├── chroma_store.py       # ChromaDB read/write
│   │   ├── bm25_index.py         # BM25Okapi build/search/persist
│   │   └── hybrid_retriever.py   # RRF fusion of BM25 + semantic
│   └── llm/
│       └── generator.py          # Groq API, prompt construction, citations
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.jsx              # React entrypoint
        ├── App.jsx               # Root component, state machine
        ├── App.css               # All styles (dark theme, design tokens)
        └── components/
            ├── RepoInput.jsx     # URL input + POST /ingest trigger
            ├── ChatBox.jsx       # Chat UI + POST /query trigger
            └── CodeBlock.jsx     # Citation card renderer
```

---

## 4. Backend — File-by-File Reference

### 4.1 `main.py` — FastAPI Application

**Imports and boot sequence**:
- Loads `.env` via `python-dotenv` before any other import (important: env vars must exist before `embedder.py` initializes the Cohere client).
- On `@app.on_event("startup")`, calls `load_from_cache()` in `bm25_index.py` to restore the BM25 index from `./bm25_index.pkl` — so queries work immediately after a server restart without re-ingesting.

**CORS**: Whitelists `http://localhost:5173` (local Vite dev) and `https://lightrox.github.io` (deployed GitHub Pages frontend). All methods and headers are allowed.

**Routes**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check, returns `{"message": "..."}` |
| `POST` | `/ingest` | Full ingestion pipeline. Heavy: 30s–2min. |
| `POST` | `/query` | Retrieval + generation. Fast: 1–3s. |
| `DELETE` | `/clear` | Wipes ChromaDB collection + BM25 index + pkl file. |

**`POST /ingest` — step by step**:
1. `clone_repo(request.repo_url)` → `repo_path: str` (temp dir)
2. `walk_files(repo_path)` → `files: list[dict]`
3. `chunk_all_files(files)` → `chunks: list[dict]`
4. `embed_chunks(chunks)` → same `chunks` with `"embedding"` key added
5. `clear_chroma()` then `store(chunks)` — wipe old data before storing new
6. `clear_bm25()` then `build_bm25(chunks)` — rebuild keyword index
7. `delete_repo(repo_path)` in `finally` block — always cleans up disk
8. Returns `IngestResponse(message, total_chunks, total_files)`

**Error handling**:
- `ValueError` (bad URL, no supported files) → HTTP 400
- `RuntimeError` (clone failed, API errors) → HTTP 500
- Repo cleanup always runs in `finally`, even on exception

**`POST /query` — step by step**:
1. Validates `request.question` is not blank
2. `retrieve(request.question, top_k=5)` → `chunks: list[dict]`
3. If no chunks → HTTP 404
4. `generate(request.question, chunks)` → `result: dict`
5. Returns `QueryResponse(answer, citations)`

---

### 4.2 `models.py` — Pydantic Schemas

```python
class IngestRequest(BaseModel):
    repo_url: str   # GitHub HTTPS URL

class IngestResponse(BaseModel):
    message: str
    total_chunks: int
    total_files: int

class QueryRequest(BaseModel):
    question: str   # Natural language question

class Citation(BaseModel):
    file: str         # relative path e.g. "src/Main.java"
    start_line: int
    end_line: int

class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
```

These are the only contracts between frontend and backend. FastAPI auto-validates and serializes them.

---

### 4.3 `ingestion/cloner.py`

**`clone_repo(repo_url: str) -> str`**
- Validates URL matches `^https?://(www\.)?github\.com/` with regex. Raises `ValueError` if not.
- Creates a unique temp directory with `tempfile.mkdtemp(prefix="codebase_assistant_")`.
- Uses `gitpython`'s `Repo.clone_from(url, temp_dir)`.
- On `GitCommandError` → removes temp dir, raises `RuntimeError`.
- Returns the temp dir path string.

**`delete_repo(repo_path: str)`**
- Checks `os.path.exists(repo_path)` then calls `shutil.rmtree(repo_path, ignore_errors=True)`.
- Always called in the `finally` block of `/ingest`.

**Design note**: The repo is never persisted beyond the ingestion call. The server is stateless on disk — only indexes persist.

---

### 4.4 `ingestion/file_walker.py`

**Constants**:
```python
SUPPORTED_EXTENSIONS = {".py", ".java", ".js", ".ts", ".go", ".cpp", ".c"}

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv",
    "venv", "env", "dist", "build", "target", ".idea"
}
```

**`walk_files(repo_path: str) -> list[dict]`**
- Uses `os.walk(repo_path)`.
- Prunes ignored dirs in-place: `dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]` — this prevents `os.walk` from descending into them.
- For each file: checks extension, reads content as UTF-8 (`errors="ignore"` to skip non-text bytes), skips empty files.
- Returns list of:
  ```python
  {
      "path": "/tmp/codebase_assistant_xyz/src/Main.java",  # absolute
      "relative_path": "src/Main.java",                      # relative to repo root
      "extension": ".java",
      "content": "public class Main { ... }"                 # full file text
  }
  ```
- Exceptions per file are caught and logged; file is skipped, walk continues.

---

### 4.5 `ingestion/ast_chunker.py`

This is the most complex ingestion module. It splits files into **semantically meaningful chunks** (function/class bodies) rather than fixed character/line windows.

**`chunk_all_files(files: list[dict]) -> list[dict]`** — entrypoint, calls `chunk_file` on each file, flattens to a single list.

**`chunk_file(file: dict) -> list[dict]`** — dispatcher:
- `.py` extension → `_chunk_python(content, relative_path)`
- anything else → `_chunk_by_regex(content, relative_path, ext)`

**`_chunk_python(content, relative_path)`**
- Calls `ast.parse(content)`. On `SyntaxError` → falls back to `_whole_file_chunk`.
- `ast.walk(tree)` visits all nodes; keeps only `FunctionDef`, `AsyncFunctionDef`, `ClassDef`.
- `node.lineno` is 1-indexed start, `node.end_lineno` is 1-indexed end.
- Extracts `"\n".join(lines[start:end])` — full function/class body including decorators if they precede the def (note: `node.lineno - 1` to get 0-indexed slice start).
- If no AST nodes found → falls back to `_whole_file_chunk`.

**`_chunk_by_regex(content, relative_path, ext)`**
- Uses `FUNCTION_PATTERNS` dict mapping extension → regex pattern.
- Patterns per language:
  - `.java`: matches `public/private/protected/static/final/abstract/synchronized` prefixed methods
  - `.js`: matches `function foo() {` and arrow functions `const foo = () => {`
  - `.ts`: same as `.js` but with optional return type annotation `): Type {`
  - `.go`: matches `func (receiver *Type) MethodName(...) { `
  - `.cpp`: broad match for C++ method signatures
  - `.c`: simple C function signature match
- Uses `re.finditer(pattern, content, re.MULTILINE)` to find all function starts.
- Each chunk spans from its own start to the next function's start (or EOF for the last one).
- If regex finds nothing → `_whole_file_chunk`.

**`_whole_file_chunk(content, relative_path)`**
- Returns a single chunk containing the entire file.
- Used as fallback when AST fails or regex finds nothing.

**Chunk output shape**:
```python
{
    "code": "def connect(self):\n    ...",
    "file": "src/peer/PeerConnection.py",   # relative path
    "start_line": 42,                        # 1-indexed
    "end_line": 78,                          # 1-indexed, inclusive
    "chunk_id": "src/peer/PeerConnection.py::42"  # used as ChromaDB document ID
}
```

**Design note**: `chunk_id` format `"file::start_line"` is globally unique per repo because no two functions start on the same line in the same file.

---

### 4.6 `ingestion/embedder.py`

Uses the **Cohere** `embed-english-light-v3.0` model (384-dimensional vectors).

**Lazy singleton client**:
```python
_client = None
def get_client() -> cohere.Client:
    global _client
    if _client is None:
        _client = cohere.Client(api_key=API_KEY)
    return _client
```
`COHERE_API_KEY` is read at module import time; missing key raises `ValueError` immediately on startup.

**`embed_chunks(chunks: list[dict]) -> list[dict]`**
- Extracts `chunk["code"]` strings.
- Batches into groups of 90 (Cohere's per-request limit).
- Calls `client.embed(texts=batch, model="embed-english-light-v3.0", input_type="search_document")`.
- `input_type="search_document"` is critical — Cohere uses this to optimize embeddings for being retrieved, not for querying.
- Attaches `chunk["embedding"] = embedding` (a `list[float]` of length 1024) to each chunk dict in-place.
- Returns the same list (mutated).

**`embed_query(query: str) -> list[float]`**
- Single call to Cohere with `input_type="search_query"`.
- Using `"search_query"` vs `"search_document"` is the asymmetric embedding technique — the model produces vectors optimized for finding matching documents.
- Returns a single `list[float]` of length 1024.

**Important**: The same Cohere model and same dimensionality is used for both indexing and querying. Mixing models or dimensionalities would make retrieval useless.

---

### 4.7 `retrieval/chroma_store.py`

Wraps ChromaDB with a lazy singleton pattern.

**Globals**:
```python
_client = None        # chromadb.PersistentClient
_collection = None    # chromadb.Collection
COLLECTION_NAME = "codebase"
```

**`get_collection()`**
- Creates `chromadb.PersistentClient(path="./chroma_db")` — relative to the backend working directory.
- Gets or creates collection named `"codebase"` with `metadata={"hnsw:space": "cosine"}`.
- Cosine similarity is used instead of L2 (Euclidean) because embedding magnitudes are not meaningful — only directions are.

**`store(chunks: list[dict])`**
- Extracts parallel arrays: `ids`, `embeddings`, `documents` (the raw code), `metadatas`.
- Metadata stored per chunk: `{"file": ..., "start_line": ..., "end_line": ...}`.
- Uses `collection.upsert(...)` — safe to call on re-ingestion, won't duplicate if `chunk_id` already exists (though `clear()` is always called before `store()` anyway).

**`query(query_embedding: list[float], top_k: int) -> list[dict]`**
- Calls `collection.query(query_embeddings=[query_embedding], n_results=top_k, include=["documents", "metadatas", "distances"])`.
- ChromaDB returns nested lists (one per query); unpacks `results["documents"][0]`, `results["metadatas"][0]`, `results["distances"][0]`.
- ChromaDB returns cosine **distance** (0 = identical, 2 = opposite). Converts to similarity: `score = round(1 - dist, 4)`.
- Returns list of:
  ```python
  {"code": "...", "file": "...", "start_line": 42, "end_line": 78, "score": 0.91}
  ```

**`clear()`**
- Calls `_client.delete_collection(COLLECTION_NAME)` then re-creates it via `get_collection()`.
- Sets `_collection = None` first so `get_collection()` re-initializes cleanly.

---

### 4.8 `retrieval/bm25_index.py`

In-memory BM25 keyword search with disk persistence.

**Globals**:
```python
_bm25: BM25Okapi = None
_chunks: list[dict] = []
INDEX_CACHE_PATH = "./bm25_index.pkl"
```

**`_tokenize(text: str) -> list[str]`**
- `re.findall(r"[a-zA-Z0-9]+", text.lower())` — splits on all non-alphanumeric characters, lowercases.
- Handles camelCase by keeping the whole word (`"PeerManager"` stays as `"peermanager"`), and splits snake_case (`"peer_manager"` → `["peer", "manager"]`).

**`build(chunks: list[dict])`**
- Tokenizes `chunk["code"]` for every chunk.
- Creates `BM25Okapi(tokenized)` from `rank-bm25` library.
- Pickles `{"bm25": _bm25, "chunks": _chunks}` to `./bm25_index.pkl` for restart survival.
- ChromaDB persists itself; BM25 is in-memory only and must be manually serialized.

**`load_from_cache()`**
- Called on `@app.on_event("startup")`.
- Unpickles the `.pkl` file if it exists.
- If load fails (corrupted file etc.) → logs warning, leaves index empty (queries will return no BM25 results but won't crash).

**`search(query: str, top_k: int) -> list[dict]`**
- Tokenizes query with same `_tokenize` function.
- `_bm25.get_scores(tokens)` returns a score per chunk.
- Zips `_chunks` with scores, sorts descending, returns top-k.
- Returns list of:
  ```python
  {"code": "...", "file": "...", "start_line": 42, "end_line": 78, "score": 4.72}
  ```
  Note: BM25 scores are not normalized (unlike the cosine similarity from ChromaDB). The RRF fusion step uses rank, not raw score, so this is fine.

**`clear()`**
- Resets `_bm25 = None`, `_chunks = []`.
- Deletes `./bm25_index.pkl` from disk.

---

### 4.9 `retrieval/hybrid_retriever.py`

The core retrieval logic — combines BM25 and semantic search using Reciprocal Rank Fusion.

**`retrieve(question: str, top_k: int = 5) -> list[dict]`**

Step 1 — Over-fetch candidates:
```python
candidate_k = max(top_k * 2, 10)   # e.g. top_k=5 → candidate_k=10
```
Fetching more candidates from each source before fusion improves overlap and final quality.

Step 2 — BM25 search:
```python
bm25_results = bm25_index.search(question, top_k=candidate_k)
```
Returns up to `candidate_k` chunks ranked by keyword relevance.

Step 3 — Semantic search:
```python
query_embedding = embedder.embed_query(question)  # Cohere, search_query type
semantic_results = chroma_store.query(query_embedding, top_k=candidate_k)
```
Each search failure is caught independently — if one fails, the other still contributes.

Step 4 — Reciprocal Rank Fusion (RRF):
```
score(doc) = Σ over methods m: 1 / (k + rank_m(doc))
```
Where `k = 60` (industry standard constant that dampens the impact of rank differences).

- Document identity key: `(file, start_line, end_line)` tuple — same chunk found by both methods gets both contributions.
- `doc_map[key]` stores the actual chunk dict for later retrieval.
- After scoring, sorts by RRF score descending, returns top `top_k` results.
- Attaches `doc["score"] = round(rrf_scores[key], 6)` to each result (the fused RRF score, not BM25 or cosine similarity).

**Why RRF instead of score normalization?**
BM25 scores (unbounded, depends on corpus) and cosine similarity (0–1) are on completely different scales and can't be directly combined. RRF uses only rank position, making it scale-invariant and requiring no tuning per model.

---

### 4.10 `llm/generator.py`

**`generate(question: str, chunks: list[dict]) -> dict`**

**API**: Uses `groq` Python client. Reads `GROQ_API_KEY` and `GROQ_MODEL` from environment. Default model: `"llama-3.1-8b-instant"` (fast, free tier, 8B parameters).

**Context construction**:
```python
context_text = ""
for i, chunk in enumerate(chunks, 1):
    context_text += f"--- Source {i}: {chunk['file']} (Lines {chunk['start_line']}-{chunk['end_line']}) ---\n"
    context_text += f"{chunk['code']}\n\n"
```
The numbered source headers help the LLM reference specific files in its answer.

**System prompt**:
> "You are an expert codebase assistant. Your goal is to answer the user's questions about their code using ONLY the provided code context. If the context does not contain enough information to answer the question, say so clearly. Support your explanation with exact code references or snippets from the context where appropriate. Keep your response concise, clear, and structured."

Key design: grounded generation — the LLM is instructed to only use the provided context, not its training data. This prevents hallucinated file paths or function names.

**LLM call parameters**:
```python
model=model,            # llama-3.1-8b-instant
temperature=0.2,        # low = factual, deterministic
max_tokens=1024         # caps response length
```

**Citations** are compiled independently of the answer:
```python
citations = [
    {"file": chunk["file"], "start_line": chunk["start_line"], "end_line": chunk["end_line"]}
    for chunk in chunks
]
```
All retrieved chunks become citations, regardless of whether the LLM explicitly referenced them in its answer text. This is intentional — the user can see exactly what context was used.

**Returns**:
```python
{"answer": "...", "citations": [...]}
```

**Error handling**: On Groq API exception, returns an error message string as `answer` with the same `citations`. Never raises — the route always gets a response.

---

## 5. Frontend — File-by-File Reference

### 5.1 `App.jsx` — Root Component

Two-state machine:
- **State A** (`repoUrl === null`): shows `<RepoInput>` component.
- **State B** (`repoUrl` is set): shows stats bar + `<ChatBox>` component.

State:
```jsx
const [repoUrl, setRepoUrl] = useState(null);
const [stats, setStats] = useState(null);   // { totalChunks, totalFiles }
```

`handleIngested(url, totalChunks, totalFiles)` — callback passed to `RepoInput`. Transitions from State A to State B.

`handleReset()` — resets both states to null. The "Index a different repo" button calls this. **Note**: this does NOT call `DELETE /clear` on the backend — the old index remains until the next ingest overwrites it.

Stats bar renders: `"{totalFiles} files · {totalChunks} chunks indexed"`.

---

### 5.2 `RepoInput.jsx`

Manages ingestion flow. State:
```jsx
const [url, setUrl] = useState("");
const [loading, setLoading] = useState(false);
const [error, setError] = useState("");
const [status, setStatus] = useState("");   // e.g. "Cloning repo..."
```

`handleIngest()`:
1. Sets `status = "Cloning repo..."` and `loading = true`.
2. `POST https://codebase-assistant-db62.onrender.com/ingest` with `{ repo_url: url }`.
3. On success: sets `status = data.message`, calls `onIngested(url, data.total_chunks, data.total_files)`.
4. On error: sets `error = err.message`.
5. Always: `loading = false`.

UI renders: URL input + "Index Repo" button (shows "Indexing..." when loading). Spinning indicator during load. Error message in red.

**Backend URL**: Hardcoded to Render.com deployment. For local dev, this needs to be changed to `http://localhost:8000`.

---

### 5.3 `ChatBox.jsx`

Manages the conversation. State:
```jsx
const [messages, setMessages] = useState([
    { role: "assistant", text: "Repo indexed. Ask me anything about the codebase.", citations: [] }
]);
const [input, setInput] = useState("");
const [loading, setLoading] = useState(false);
```

`handleAsk()`:
1. Trims and validates input, returns early if empty or already loading.
2. Appends `{ role: "user", text: question }` to messages immediately (optimistic UI).
3. Clears input, sets `loading = true`.
4. `POST .../query` with `{ question }`.
5. On success: appends `{ role: "assistant", text: data.answer, citations: data.citations }`.
6. On error: appends `{ role: "assistant", text: "Error: ...", citations: [] }`.
7. Always: `loading = false`.

Auto-scroll: `useEffect` on `messages` calls `bottomRef.current?.scrollIntoView({ behavior: "smooth" })`.

Typing indicator: a `<div className="bubble typing">` with 3 `<span>` elements animated with a bounce CSS keyframe.

Message rendering: each message is styled differently via `.message.user` or `.message.assistant`. Citations are rendered as `<CodeBlock>` cards below assistant messages.

---

### 5.4 `CodeBlock.jsx`

Minimal presentational component:
```jsx
export default function CodeBlock({ citation }) {
  return (
    <div className="citation">
      <span className="citation-file">📄 {citation.file}</span>
      <span className="citation-lines">lines {citation.start_line}–{citation.end_line}</span>
    </div>
  );
}
```
Displays file path in accent blue, line range in dim gray.

---

### 5.5 `App.css` — Design System

Dark theme modeled on GitHub's dark UI. CSS custom properties:
```css
:root {
    --bg: #0d1117;           /* page background (GitHub dark) */
    --surface: #161b22;      /* card backgrounds */
    --border: #30363d;       /* borders */
    --text: #e6edf3;         /* primary text */
    --text-dim: #8b949e;     /* secondary text, placeholders */
    --accent: #58a6ff;       /* links, highlights (GitHub blue) */
    --accent-dim: #1f6feb;   /* button backgrounds */
    --green: #3fb950;        /* app title "> " prefix */
    --mono: "JetBrains Mono", "Fira Code", "SF Mono", Consolas, monospace;
    --sans: "Inter", -apple-system, sans-serif;
}
```

Key UI patterns:
- App max-width: 720px centered column.
- `.app-header h1::before { content: "> "; color: var(--green); }` — terminal-style title.
- User messages: rounded `10px 10px 2px 10px` (missing bottom-right corner → chat bubble pointing right).
- Assistant messages: rounded `10px 10px 10px 2px` (missing bottom-left corner → chat bubble pointing left).
- Spinner: CSS `border-top-color` rotation animation at 0.7s.
- Typing dots: CSS `@keyframes bounce` with staggered `animation-delay`.
- Responsive: below 600px, input rows stack vertically; buttons go full-width.

---

## 6. Infrastructure

### 6.1 Environment Variables

Stored in `backend/.env` (gitignored).

| Variable | Required | Description |
|----------|----------|-------------|
| `COHERE_API_KEY` | ✅ Yes | Cohere embed API key. Fails at startup if missing. |
| `GROQ_API_KEY` | ✅ Yes | Groq inference API key. Fails at query time if missing. |
| `GROQ_MODEL` | ❌ Optional | Default: `"llama-3.1-8b-instant"`. Override to use different Groq model. |

### 6.2 Python Dependencies (`requirements.txt`)

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework, route definitions |
| `uvicorn[standard]` | ASGI server (runs FastAPI) |
| `gitpython` | `Repo.clone_from()` |
| `cohere` | Embed API client |
| `chromadb` | Vector store with HNSW index |
| `rank-bm25` | `BM25Okapi` keyword search |
| `groq` | Groq LLM API client |
| `pydantic` | Request/response validation |
| `python-dotenv` | `.env` file loader |

### 6.3 Dockerfile

- Base image: `python:3.11-slim`
- Installs system packages: `git` (for `gitpython`), `build-essential` (for compiling C extensions in some Python packages)
- Copies `backend/requirements.txt` first (layer caching), then `backend/` source.
- Exposes port 8000.
- CMD: `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}` — uses `PORT` env var (Render.com sets this automatically).

### 6.4 Deployment

- **Backend**: Deployed on Render.com at `https://codebase-assistant-db62.onrender.com`. The hardcoded frontend URLs point here.
- **Frontend**: Built with Vite (`npm run build`) and deployed on GitHub Pages at `https://lightrox.github.io`. CORS on the backend whitelists this origin.
- **ChromaDB persistence**: `./chroma_db` is a local directory. On Render free tier this is ephemeral (resets on restart). BM25 `.pkl` has the same issue. On restart, BM25 is loaded from the `.pkl` if it exists; if the disk was wiped, the index is gone and the user must re-ingest.

---

## 7. Data Shapes — Complete Reference

Every data structure that flows through the system:

### After `walk_files()`:
```python
{
    "path": "/tmp/codebase_assistant_abc123/src/Main.java",
    "relative_path": "src/Main.java",
    "extension": ".java",
    "content": "public class Main {\n    public static void main..."
}
```

### After `chunk_all_files()`:
```python
{
    "code": "public void connect() {\n    ...\n}",
    "file": "src/Main.java",
    "start_line": 42,
    "end_line": 78,
    "chunk_id": "src/Main.java::42"
}
```

### After `embed_chunks()` (same dict + new key):
```python
{
    "code": "...",
    "file": "...",
    "start_line": 42,
    "end_line": 78,
    "chunk_id": "src/Main.java::42",
    "embedding": [0.012, -0.341, 0.789, ...]   # 1024 floats
}
```

### From `chroma_store.query()` and `bm25_index.search()`:
```python
{
    "code": "...",
    "file": "src/Main.java",
    "start_line": 42,
    "end_line": 78,
    "score": 0.91    # cosine similarity (chroma) or BM25 score (bm25)
}
```

### From `hybrid_retriever.retrieve()` (score overwritten with RRF):
```python
{
    "code": "...",
    "file": "src/Main.java",
    "start_line": 42,
    "end_line": 78,
    "score": 0.031746   # RRF score, e.g. 1/(60+1) + 1/(60+3) = 0.0164+0.0152
}
```

### HTTP Response `POST /query`:
```json
{
    "answer": "The peer discovery mechanism works by...",
    "citations": [
        {"file": "src/peer/PeerManager.java", "start_line": 42, "end_line": 78},
        {"file": "src/tracker/TrackerClient.java", "start_line": 10, "end_line": 55}
    ]
}
```

---

## 8. Key Design Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| **AST chunking for Python, regex for others** | Python's `ast` module gives exact node boundaries. Regex is imperfect but practical for other languages. Naive fixed-size chunking would cut functions in half, destroying semantic meaning. |
| **`input_type="search_document"` vs `"search_query"`** | Cohere's asymmetric embeddings — documents and queries are embedded differently for better retrieval. Using the same type for both would degrade quality. |
| **Hybrid BM25 + semantic search** | BM25 excels at exact identifier matches (`PeerManager`, specific method names). Semantic search excels at paraphrased/conceptual queries. Each has blind spots the other covers. |
| **RRF fusion (k=60) over score normalization** | BM25 and cosine similarity are on incompatible scales. RRF uses only rank position — scale-invariant, no hyperparameter tuning per model. k=60 is the standard value from the original RRF paper. |
| **Fetching `candidate_k = max(top_k*2, 10)` from each source** | More candidates from each ranker before fusion increases the chance of overlap, which improves RRF quality. |
| **`temperature=0.2` for the LLM** | Lower temperature → more deterministic, factual answers. The LLM is being used for code explanation, not creative writing. |
| **All retrieved chunks become citations** | Even if the LLM doesn't explicitly mention a file, showing all retrieved chunks tells the user exactly what context was used. Useful for debugging retrieval quality. |
| **BM25 pickled to disk** | ChromaDB persists its HNSW index automatically. BM25 is pure in-memory and would be lost on server restart without manual serialization. |
| **Repo deleted after ingestion** | Server remains stateless on disk. Only the indexes (ChromaDB dir + BM25 pkl) persist. Prevents disk accumulation across multiple ingestions. |
| **`chunk_id = "file::start_line"`** | Globally unique within a repo. Used as ChromaDB document ID to enable upserts (deduplication on re-ingestion). |
| **Groq instead of OpenAI** | Groq offers free tier with fast inference (LPU hardware). `llama-3.1-8b-instant` is fast and sufficient for code Q&A. |

---

## 9. Known Limitations & Future Work

| Limitation | Notes |
|------------|-------|
| **Single-repo only** | Each `/ingest` call wipes all previous data. Multi-repo would require namespaced collections. |
| **No authentication** | Anyone with the URL can ingest/query. Production would need JWT auth + per-user isolation. |
| **Ephemeral storage on free hosting** | Render free tier resets disk on restart. Prod would use Qdrant (cloud) + a proper BM25 service. |
| **No streaming** | LLM response is returned in one shot. Streaming via SSE would improve perceived latency. |
| **CSS only, no Markdown rendering** | LLM answers with code blocks appear as raw text in the chat bubble. A Markdown renderer (e.g., `react-markdown`) would improve readability. |
| **README has outdated info** | README still mentions `sentence-transformers` and `all-MiniLM-L6-v2` (local embeddings), but the actual code uses Cohere's hosted API. The model listed as `llama3-8b-8192` was also replaced by `llama-3.1-8b-instant`. |
| **No retrieval evaluation** | No golden Q&A set or precision@k metrics to measure retrieval quality changes. |
| **camelCase tokenization** | `_tokenize` keeps `PeerManager` as `peermanager` (one token). Splitting camelCase into `["peer", "manager"]` would improve recall for partial identifier queries. |
