export default function CodeBlock({ citation }) {
  const fileLabel = (
    <span className="citation-file">📄 {citation.file}</span>
  );

  return (
    <div className="citation">
      <div className="citation-header">
        {citation.url ? (
          <a
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            className="citation-link"
          >
            {fileLabel}
          </a>
        ) : (
          fileLabel
        )}
        <span className="citation-lines">
          lines {citation.start_line}–{citation.end_line}
        </span>
      </div>
      {citation.code ? (
        <pre className="citation-code">
          <code>{citation.code}</code>
        </pre>
      ) : null}
    </div>
  );
}
