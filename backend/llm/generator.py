import os
import re
from groq import Groq

UI_SNIPPET_MAX_LINES = 40
UI_SNIPPET_MAX_CHARS = 2000


def _github_blob_url(chunk: dict) -> str:
    owner = chunk.get("owner") or ""
    repo = chunk.get("repo") or ""
    sha = chunk.get("commit_sha") or ""
    file_path = (chunk.get("file") or "").lstrip("/")
    start = chunk.get("start_line")
    end = chunk.get("end_line")
    if not owner or not repo or not sha or not file_path or start is None or end is None:
        return ""
    return f"https://github.com/{owner}/{repo}/blob/{sha}/{file_path}#L{start}-L{end}"


def _display_code(code: str) -> str:
    if not code:
        return ""
    lines = code.splitlines()
    truncated = False
    if len(lines) > UI_SNIPPET_MAX_LINES:
        lines = lines[:UI_SNIPPET_MAX_LINES]
        truncated = True
    text = "\n".join(lines)
    if len(text) > UI_SNIPPET_MAX_CHARS:
        text = text[:UI_SNIPPET_MAX_CHARS]
        truncated = True
    if truncated:
        text += "\n..."
    return text


def _citation_from_chunk(chunk: dict) -> dict:
    return {
        "file": chunk["file"],
        "start_line": chunk["start_line"],
        "end_line": chunk["end_line"],
        "url": _github_blob_url(chunk),
        "code": _display_code(chunk.get("code", "")),
    }


def generate(question: str, chunks: list[dict]) -> dict:
    """
    Generates an answer using the Groq API based on the retrieved code chunks,
    returning a dictionary with 'answer' and 'citations'.

    Args:
        question: User's question about the codebase
        chunks: List of retrieved code chunks with source paths

    Returns:
        Dict containing:
        {
            "answer": str,
            "citations": list[dict]
        }
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[Generator] WARNING: GROQ_API_KEY is not set.")
        return {
            "answer": "Error: GROQ_API_KEY is not set. Please add it to your environment or .env file in the backend folder.",
            "citations": []
        }

    # Use active Groq model
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    # Max character caps to prevent HTTP 413 (Request Entity Too Large) errors from Groq API
    MAX_CHUNK_CHARS = 2500
    MAX_TOTAL_CHARS = 12000

    # Format the context retrieved from RAG with safe character bounds
    used_chunks = []
    if not chunks:
        context_text = "No relevant code context was found in the repository."
    else:
        context_parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            code = chunk.get("code", "")
            if len(code) > MAX_CHUNK_CHARS:
                code = code[:MAX_CHUNK_CHARS] + "\n... [truncated chunk text]"

            chunk_entry = f"--- Source {i}: {chunk['file']} (Lines {chunk['start_line']}-{chunk['end_line']}) ---\n{code}\n\n"
            if total_chars + len(chunk_entry) > MAX_TOTAL_CHARS:
                if not context_parts:
                    context_parts.append(chunk_entry[:MAX_TOTAL_CHARS])
                    used_chunks.append(chunk)
                break
            context_parts.append(chunk_entry)
            total_chars += len(chunk_entry)
            used_chunks.append(chunk)

        context_text = "".join(context_parts)

    system_prompt = (
        "You are an expert codebase assistant. Your goal is to answer the user's questions about their code "
        "using ONLY the provided code context for codebase questions. For greetings or unrelated conversational questions, "
        "respond briefly without using the code context. If the context does not contain enough information to answer a "
        "codebase question, say so clearly. After an answer that relies on repository context, append a marker for each "
        "supporting source in the exact format [[source:N]], using its source number from the context. Do not include "
        "markers for sources you did not use, and do not include any markers for conversational or unrelated answers. "
        "Keep your response concise, clear, and structured."
    )

    user_content = f"Context:\n{context_text}\n\nQuestion: {question}"

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        answer = response.choices[0].message.content or ""
        source_numbers = {
            int(number)
            for number in re.findall(r"\[\[source:(\d+)\]\]", answer)
        }
        answer = re.sub(r"\s*\[\[source:\d+\]\]", "", answer).rstrip()
        citations = [
            _citation_from_chunk(chunk)
            for number, chunk in enumerate(used_chunks, 1)
            if number in source_numbers
        ]
        return {
            "answer": answer,
            "citations": citations
        }
    except Exception as e:
        print(f"[Generator] Error calling Groq API: {e}")
        return {
            "answer": f"Error: Failed to generate an answer from Groq. Details: {str(e)}",
            "citations": []
        }