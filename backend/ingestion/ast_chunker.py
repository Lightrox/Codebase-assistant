import ast
import re


def chunk_file(file: dict) -> list[dict]:
    """
    Splits a file into chunks at function/class boundaries.

    For .py  → uses Python's ast module (precise)
    For rest → uses regex to detect function signatures (good enough)

    Args:
        file: dict from file_walker with keys: relative_path, extension, content

    Returns:
        List of chunks:
        [
            {
                "code": "def connect(self): ...",
                "file": "src/peer/PeerConnection.java",
                "start_line": 42,
                "end_line": 78,
                "chunk_id": "src/peer/PeerConnection.java::42"
            },
            ...
        ]
    """

    ext = file["extension"]
    content = file["content"]
    relative_path = file["relative_path"]

    if ext == ".py":
        return _chunk_python(content, relative_path)
    else:
        return _chunk_by_regex(content, relative_path, ext)


# Python chunking 

def _chunk_python(content: str, relative_path: str) -> list[dict]:
    chunks = []
    lines = content.splitlines()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _whole_file_chunk(content, relative_path)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        start = node.lineno - 1        
        end = node.end_lineno            

        code = "\n".join(lines[start:end])

        chunks.append({
            "code": code,
            "file": relative_path,
            "start_line": node.lineno,
            "end_line": end,
            "chunk_id": f"{relative_path}::{node.lineno}"
        })

    if not chunks:
        return _whole_file_chunk(content, relative_path)

    return chunks


# Regex-based chunking for Java, JS, TS, Go, C++

FUNCTION_PATTERNS = {
    ".java": r'((?:public|private|protected|static|final|abstract|synchronized)\s+[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+\w+)?\s*\{)',
    ".js":   r'((?:async\s+)?function\s+\w+\s*\([^)]*\)\s*\{|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\([^)]*\)\s*=>\s*\{)',
    ".ts":   r'((?:async\s+)?function\s+\w+\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?\([^)]*\)\s*=>\s*\{)',
    ".go":   r'(func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+\s*\([^)]*\)\s*(?:\(.*?\)\s*)?\{)',
    ".cpp":  r'(\w[\w\s*&:<>]*\s+\w+\s*\([^)]*\)\s*(?:const)?\s*\{)',
    ".c":    r'(\w[\w\s*]*\s+\w+\s*\([^)]*\)\s*\{)',
}

def _chunk_by_regex(content: str, relative_path: str, ext: str) -> list[dict]:
    pattern = FUNCTION_PATTERNS.get(ext)

    if not pattern:
        return _whole_file_chunk(content, relative_path)

    lines = content.splitlines()
    chunks = []

    # Find all function start positions
    matches = list(re.finditer(pattern, content, re.MULTILINE))

    for i, match in enumerate(matches):
        start_char = match.start()
        start_line = content[:start_char].count("\n") + 1

        # End line = start of next function, or end of file
        if i + 1 < len(matches):
            end_char = matches[i + 1].start()
            end_line = content[:end_char].count("\n")
        else:
            end_line = len(lines)

        code = "\n".join(lines[start_line - 1 : end_line])

        chunks.append({
            "code": code,
            "file": relative_path,
            "start_line": start_line,
            "end_line": end_line,
            "chunk_id": f"{relative_path}::{start_line}"
        })

    if not chunks:
        return _whole_file_chunk(content, relative_path)

    return chunks


# ── Fallback: whole file as one chunk 

def _whole_file_chunk(content: str, relative_path: str) -> list[dict]:
    return [{
        "code": content,
        "file": relative_path,
        "start_line": 1,
        "end_line": len(content.splitlines()),
        "chunk_id": f"{relative_path}::1"
    }]


# ── Entrypoint: chunk all files ─

def chunk_all_files(files: list[dict]) -> list[dict]:
    """
    Chunks all files returned by file_walker.

    Args:
        files: list of file dicts from walk_files()

    Returns:
        Flat list of all chunks across all files
    """
    all_chunks = []

    for file in files:
        chunks = chunk_file(file)
        all_chunks.extend(chunks)

    print(f"[ASTChunker] Generated {len(all_chunks)} chunks from {len(files)} files")
    return all_chunks
