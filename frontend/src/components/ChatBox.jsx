import { useState, useRef, useEffect } from "react";
import CodeBlock from "./CodeBlock";

export default function ChatBox({ repoUrl }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Repo indexed. Ask me anything about the codebase.",
      citations: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleAsk = async () => {
    const question = input.trim();
    if (!question || loading) return;

    // Add user message immediately
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("https://codebase-assistant-db62.onrender.com/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || "Query failed");

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.answer,
          citations: data.citations || [],
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${err.message}`, citations: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chatbox">
      <div className="repo-tag">
        <span>⚡</span>
        <span>{repoUrl}</span>
      </div>

      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="bubble">{msg.text}</div>
            {msg.citations?.length > 0 && (
              <div className="citations">
                {msg.citations.map((c, j) => (
                  <CodeBlock key={j} citation={c} />
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="bubble typing">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="input-row">
        <input
          type="text"
          placeholder="Ask anything about the codebase"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          disabled={loading}
          className="chat-input"
        />
        <button
          onClick={handleAsk}
          disabled={loading || !input.trim()}
          className="send-btn"
        >
          Ask
        </button>
      </div>
    </div>
  );
}
