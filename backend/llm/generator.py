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

    # Use standard Llama-3-8b model on Groq
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # Format the context retrieved from RAG
    if not chunks:
        context_text = "No relevant code context was found in the repository."
    else:
        context_text = ""
        for i, chunk in enumerate(chunks, 1):
            context_text += f"--- Source {i}: {chunk['file']} (Lines {chunk['start_line']}-{chunk['end_line']}) ---\n"
            context_text += f"{chunk['code']}\n\n"

    system_prompt = (
        "You are an expert codebase assistant. Your goal is to answer the user's questions about their code "
        "using ONLY the provided code context. If the context does not contain enough information to answer the question, "
        "say so clearly. Support your explanation with exact code references or snippets from the context where appropriate. "
        "Keep your response concise, clear, and structured."
    )

    user_content = f"Context:\n{context_text}\n\nQuestion: {question}"

    # Prepare citations
    citations = [
        {
            "file": chunk["file"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"]
        }
        for chunk in chunks
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