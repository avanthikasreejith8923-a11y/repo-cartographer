import React, { useEffect, useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { AskQuestionResponse, QAHistoryItem, Repository, SourceCitation } from "../types";

interface AskTabProps {
  repo: Repository;
  onNavigateToIndex?: () => void;
}

export const AskTab: React.FC<AskTabProps> = ({ repo, onNavigateToIndex }) => {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitWait, setRateLimitWait] = useState<number | null>(null);
  
  // Current Q&A response
  const [currentResult, setCurrentResult] = useState<AskQuestionResponse | null>(null);
  const [activeCitationMarker, setActiveCitationMarker] = useState<string | null>(null);

  // History state
  const [history, setHistory] = useState<QAHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const sourcesSectionRef = useRef<HTMLDivElement>(null);

  const isIndexed = repo.index_status === "ready";

  const fetchHistory = async () => {
    try {
      setHistoryLoading(true);
      const res = await fetch(`/repos/${repo.id}/ask/history?limit=20`);
      if (res.ok) {
        const data: QAHistoryItem[] = await res.json();
        setHistory(data);
      }
    } catch (err) {
      console.error("Failed to load QA history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (isIndexed) {
      fetchHistory();
    }
  }, [repo.id, isIndexed]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading || !isIndexed) return;

    setLoading(true);
    setError(null);
    setRateLimitWait(null);
    setActiveCitationMarker(null);

    try {
      const res = await fetch(`/repos/${repo.id}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
      });

      if (res.status === 429) {
        const retryHeader = res.headers.get("Retry-After");
        const waitSec = retryHeader ? parseInt(retryHeader, 10) : 60;
        setRateLimitWait(isNaN(waitSec) ? 60 : waitSec);
        setError("Rate limit reached. Maximum 10 questions per minute. Please wait before asking again.");
        return;
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Server returned error (${res.status})`);
      }

      const data: AskQuestionResponse = await res.json();
      setCurrentResult(data);
      fetchHistory();
    } catch (err: any) {
      setError(err.message || "Failed to ask question");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectHistory = (item: QAHistoryItem) => {
    setQuestion(item.question);
    setCurrentResult({
      answer: item.answer,
      status: item.status,
      citations_missing: false,
      sources: item.citations,
      history_id: item.id,
      latency_ms: item.latency_ms,
    });
    setError(null);
    setActiveCitationMarker(null);
  };

  const handleDeleteHistory = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setDeletingId(id);
      const res = await fetch(`/repos/${repo.id}/ask/history/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setHistory((prev) => prev.filter((h) => h.id !== id));
        if (currentResult?.history_id === id) {
          setCurrentResult(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete history item:", err);
    } finally {
      setDeletingId(null);
    }
  };

  const scrollToSource = (marker: string) => {
    setActiveCitationMarker(marker);
    const elem = document.getElementById(`source-card-${marker}`);
    if (elem) {
      elem.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  if (!isIndexed) {
    return (
      <div className="glass-card" style={{ padding: "2.5rem", textAlign: "center", maxWidth: "600px", margin: "2rem auto" }}>
        <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>🔍</div>
        <h3 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>Repository Not Indexed</h3>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem", fontSize: "0.95rem" }}>
          To ask grounded questions about this codebase with deep citations, the repository must first be indexed with embeddings.
        </p>
        {onNavigateToIndex && (
          <button className="btn btn-primary" onClick={onNavigateToIndex}>
            Go to Search & Indexing Tab
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: "1.5rem", alignItems: "start" }}>
      {/* Main Q&A Area */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {/* Question Form */}
        <form onSubmit={handleAsk} className="glass-card" style={{ padding: "1.5rem" }}>
          <label style={{ display: "block", fontWeight: 600, fontSize: "0.95rem", marginBottom: "0.5rem" }}>
            Ask anything about {repo.full_name}
          </label>
          <div style={{ position: "relative" }}>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. How does authentication work? Where are database sessions created?"
              disabled={loading}
              maxLength={1000}
              rows={3}
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "var(--radius-md)",
                background: "rgba(11, 15, 23, 0.6)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                fontFamily: "inherit",
                fontSize: "0.95rem",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.75rem" }}>
            <span style={{ fontSize: "0.8rem", color: question.length > 900 ? "var(--warning)" : "var(--text-muted)" }}>
              {question.length} / 1000 characters
            </span>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !question.trim()}
              style={{ minWidth: "120px" }}
            >
              {loading ? "Analyzing..." : "Ask Question"}
            </button>
          </div>

          {rateLimitWait && (
            <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", background: "var(--warning-bg)", border: "1px solid var(--warning)", borderRadius: "var(--radius-md)", color: "var(--warning)", fontSize: "0.9rem" }}>
              ⏳ Rate limit reached. You can ask again in approximately {rateLimitWait} seconds.
            </div>
          )}

          {error && !rateLimitWait && (
            <div style={{ marginTop: "1rem", padding: "0.75rem 1rem", background: "var(--danger-bg)", border: "1px solid var(--danger)", borderRadius: "var(--radius-md)", color: "var(--danger)", fontSize: "0.9rem" }}>
              ⚠️ {error}
            </div>
          )}
        </form>

        {/* Loading Skeleton */}
        {loading && (
          <div className="glass-card" style={{ padding: "2rem", textAlign: "center" }}>
            <div className="spinner" style={{ margin: "0 auto 1rem" }} />
            <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem" }}>
              Searching code chunks, building grounded context, and consulting Gemini...
            </p>
          </div>
        )}

        {/* Answer Card */}
        {currentResult && !loading && (
          <div className="glass-card" style={{ padding: "1.75rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.75rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span style={{ fontWeight: 600, fontSize: "1.1rem" }}>Answer</span>
                {currentResult.status === "insufficient_evidence" && (
                  <span style={{ padding: "0.2rem 0.6rem", borderRadius: "var(--radius-full)", background: "var(--warning-bg)", color: "var(--warning)", fontSize: "0.75rem", fontWeight: 600 }}>
                    Insufficient Evidence
                  </span>
                )}
                {currentResult.status === "ok" && (
                  <span style={{ padding: "0.2rem 0.6rem", borderRadius: "var(--radius-full)", background: "var(--success-bg)", color: "var(--success)", fontSize: "0.75rem", fontWeight: 600 }}>
                    Grounded with Citations
                  </span>
                )}
              </div>
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Latency: {currentResult.latency_ms}ms
              </span>
            </div>

            {/* Markdown Answer */}
            <div style={{ lineHeight: "1.7", color: "var(--text-primary)", fontSize: "0.95rem", marginBottom: "1.5rem" }}>
              <ReactMarkdown>{currentResult.answer}</ReactMarkdown>
            </div>

            {/* Clickable Citation Chips */}
            {currentResult.sources.length > 0 && (
              <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border-color)", paddingTop: "1rem" }}>
                <span style={{ fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", fontWeight: 600, display: "block", marginBottom: "0.5rem" }}>
                  Cited Sources ({currentResult.sources.length})
                </span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {currentResult.sources.map((s) => (
                    <button
                      key={s.marker}
                      type="button"
                      onClick={() => scrollToSource(s.marker)}
                      style={{
                        background: activeCitationMarker === s.marker ? "var(--accent-primary)" : "rgba(99, 102, 241, 0.15)",
                        color: activeCitationMarker === s.marker ? "#ffffff" : "var(--accent-primary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "var(--radius-full)",
                        padding: "0.25rem 0.75rem",
                        fontSize: "0.8rem",
                        fontWeight: 600,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        transition: "all var(--transition-fast)",
                      }}
                    >
                      <span>{s.marker}</span>
                      <span style={{ opacity: 0.8, fontSize: "0.75rem" }}>{s.path.split("/").pop()}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Source Cards List */}
        {currentResult && currentResult.sources.length > 0 && !loading && (
          <div ref={sourcesSectionRef} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <h4 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-secondary)" }}>
              Source References
            </h4>
            {currentResult.sources.map((source: SourceCitation) => {
              const isHighlight = activeCitationMarker === source.marker;
              return (
                <div
                  key={source.marker}
                  id={`source-card-${source.marker}`}
                  className="glass-card"
                  style={{
                    padding: "1.25rem",
                    borderColor: isHighlight ? "var(--accent-primary)" : "var(--border-color)",
                    boxShadow: isHighlight ? "var(--shadow-glow)" : "var(--shadow-sm)",
                    transition: "all var(--transition-normal)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                      <span style={{ background: "var(--accent-primary)", color: "#fff", padding: "0.15rem 0.5rem", borderRadius: "var(--radius-sm)", fontSize: "0.75rem", fontWeight: 700 }}>
                        {source.marker}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", fontWeight: 600 }}>
                        {source.path}:{source.start_line}-{source.end_line}
                      </span>
                      {source.symbol && (
                        <span style={{ fontSize: "0.75rem", background: "rgba(255,255,255,0.06)", padding: "0.1rem 0.4rem", borderRadius: "var(--radius-sm)", color: "var(--text-secondary)" }}>
                          {source.symbol}
                        </span>
                      )}
                    </div>
                    <a
                      href={source.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontSize: "0.8rem", color: "var(--accent-primary)", textDecoration: "none", fontWeight: 500 }}
                    >
                      View on GitHub ↗
                    </a>
                  </div>
                  <pre
                    style={{
                      background: "rgba(0, 0, 0, 0.4)",
                      padding: "0.75rem 1rem",
                      borderRadius: "var(--radius-md)",
                      overflowX: "auto",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8rem",
                      lineHeight: "1.5",
                      border: "1px solid var(--border-color)",
                      color: "#e5e7eb",
                    }}
                  >
                    <code>{source.snippet}</code>
                  </pre>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* History Sidebar */}
      <div className="glass-card" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem" }}>
          <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>Question History</span>
          <button
            onClick={fetchHistory}
            disabled={historyLoading}
            style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: "0.8rem" }}
          >
            {historyLoading ? "..." : "↻"}
          </button>
        </div>

        {history.length === 0 && !historyLoading && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1.5rem 0" }}>
            No questions asked yet for this repo.
          </p>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxHeight: "600px", overflowY: "auto" }}>
          {history.map((item) => (
            <div
              key={item.id}
              onClick={() => handleSelectHistory(item)}
              style={{
                padding: "0.75rem",
                borderRadius: "var(--radius-md)",
                background: currentResult?.history_id === item.id ? "rgba(99, 102, 241, 0.15)" : "rgba(255, 255, 255, 0.03)",
                border: "1px solid",
                borderColor: currentResult?.history_id === item.id ? "var(--accent-primary)" : "var(--border-color)",
                cursor: "pointer",
                transition: "all var(--transition-fast)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-primary)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                  {item.question}
                </span>
                <button
                  type="button"
                  onClick={(e) => handleDeleteHistory(item.id, e)}
                  disabled={deletingId === item.id}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--danger)",
                    cursor: "pointer",
                    fontSize: "0.85rem",
                    padding: "0 0.2rem",
                    opacity: 0.7,
                  }}
                  title="Delete question from history"
                >
                  ✕
                </button>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.4rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                <span>{new Date(item.created_at).toLocaleDateString()}</span>
                <span>{item.status === "ok" ? "Answered" : item.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
