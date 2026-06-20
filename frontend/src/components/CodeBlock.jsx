export default function CodeBlock({ citation }) {
  return (
    <div className="citation">
      <span className="citation-file">📄 {citation.file}</span>
      <span className="citation-lines">
        lines {citation.start_line}–{citation.end_line}
      </span>
    </div>
  );
}
