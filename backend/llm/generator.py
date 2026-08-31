import os
from groq import Groq

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
    model = os.getenv("GROQ_MODEL", "groq/compound-mini")

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
        "using ONLY the provided code context. If the context does not contain enough information to answer the question, "
        "say so clearly. Support your explanation with exact code references or snippets from the context where appropriate. "
        "Keep your response concise, clear, and structured."
    )

    user_content = f"Context:\n{context_text}\n\nQuestion: {question}"

    # Prepare citations for used chunks
    citations = [
        {
            "file": chunk["file"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"]
        }
        for chunk in used_chunks
    ]

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
        return {
            "answer": response.choices[0].message.content,
            "citations": citations
        }
    except Exception as e:
        print(f"[Generator] Error calling Groq API: {e}")
        return {
            "answer": f"Error: Failed to generate an answer from Groq. Details: {str(e)}",
            "citations": citations
        }