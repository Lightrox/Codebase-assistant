import { useState } from "react";
import RepoInput from "./components/RepoInput";
import ChatBox from "./components/ChatBox";
import "./App.css";

export default function App() {
  const [repoUrl, setRepoUrl] = useState(null);
  const [stats, setStats] = useState(null);

  const handleIngested = (url, totalChunks, totalFiles) => {
    setRepoUrl(url);
    setStats({ totalChunks, totalFiles });
  };

  const handleReset = () => {
    setRepoUrl(null);
    setStats(null);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Codebase Assistant</h1>
        <p>Chat with any GitHub repository in plain English</p>
      </header>

      {!repoUrl ? (
        <RepoInput onIngested={handleIngested} />
      ) : (
        <>
          <div className="stats-row">
            <span>{stats.totalFiles} files · {stats.totalChunks} chunks indexed</span>
            <button onClick={handleReset} className="reset-btn">Index a different repo</button>
          </div>
          <ChatBox repoUrl={repoUrl} />
        </>
      )}
    </div>
  );
}
