import { useState } from "react";

export default function RepoInput({ onIngested }) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const handleIngest = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    setStatus("Cloning repo...");

    try {
      const res = await fetch("http://localhost:8000/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: url.trim() }),
      });

      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || "Ingestion failed");

      setStatus(data.message);
      onIngested(url.trim(), data.total_chunks, data.total_files);
    } catch (err) {
      setError(err.message);
      setStatus("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="repo-input">
      <div className="input-row">
        <input
          type="text"
          placeholder="https://github.com/username/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleIngest()}
          disabled={loading}
          className="url-input"
        />
        <button
          onClick={handleIngest}
          disabled={loading || !url.trim()}
          className="ingest-btn"
        >
          {loading ? "Indexing..." : "Index Repo"}
        </button>
      </div>

      {loading && (
        <div className="status-bar">
          <span className="spinner" />
          <span>{status}</span>
        </div>
      )}

      {error && <div className="error-msg">⚠ {error}</div>}
    </div>
  );
}
