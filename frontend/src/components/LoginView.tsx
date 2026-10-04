import React from "react";
import { useAuth } from "../context/AuthContext";

export const LoginView: React.FC = () => {
  const { login } = useAuth();

  // Extract possible error query param from redirect
  const params = new URLSearchParams(window.location.search);
  const errorParam = params.get("error");

  const handleDemoLogin = async () => {
    try {
      const res = await fetch("/auth/demo-login", {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        window.location.reload();
      }
    } catch (err) {
      console.error("Demo login error:", err);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        flex: 1,
        padding: "2rem 1rem",
      }}
    >
      <div
        className="glass-card"
        style={{
          width: "100%",
          maxWidth: "480px",
          padding: "2.5rem",
          textAlign: "center",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Glow accent pill */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "4px",
            background: "var(--accent-gradient)",
          }}
        />

        <div style={{ marginBottom: "1.75rem" }}>
          <div
            style={{
              width: "56px",
              height: "56px",
              margin: "0 auto 1.25rem auto",
              borderRadius: "var(--radius-md)",
              background: "var(--accent-gradient)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "var(--shadow-glow)",
            }}
          >
            {/* Map/Graph Icon */}
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#ffffff"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" />
              <line x1="9" y1="3" x2="9" y2="18" />
              <line x1="15" y1="6" x2="15" y2="21" />
            </svg>
          </div>

          <h1
            style={{
              fontSize: "1.75rem",
              fontWeight: 800,
              letterSpacing: "-0.03em",
              marginBottom: "0.5rem",
            }}
          >
            repo-cartographer
          </h1>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "0.95rem",
              lineHeight: 1.5,
            }}
          >
            AI Developer Productivity Platform: Connect repositories, map commits & PRs, and explore codebases with cited RAG intelligence.
          </p>
        </div>

        {errorParam && (
          <div
            style={{
              background: "var(--danger-bg)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "#fca5a5",
              padding: "0.75rem 1rem",
              borderRadius: "var(--radius-md)",
              marginBottom: "1.5rem",
              fontSize: "0.85rem",
              textAlign: "left",
            }}
          >
            <strong>Authentication Error:</strong> {errorParam}
          </div>
        )}

        <div style={{ margin: "1.75rem 0", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <button
            onClick={handleDemoLogin}
            id="demo-login-button"
            className="btn btn-primary"
            style={{
              width: "100%",
              padding: "0.85rem 1.25rem",
              fontSize: "0.95rem",
              background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.6rem",
              boxShadow: "0 4px 14px rgba(99, 102, 241, 0.4)",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            Explore Interactive Demo (One-Click)
          </button>

          <button
            onClick={login}
            id="github-login-button"
            className="btn btn-github"
            style={{
              width: "100%",
              padding: "0.85rem 1.25rem",
              fontSize: "0.95rem",
            }}
          >
            {/* GitHub Octocat Icon */}
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
              />
            </svg>
            Continue with GitHub
          </button>
        </div>

        <div
          style={{
            borderTop: "1px solid var(--border-color)",
            paddingTop: "1.25rem",
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            display: "flex",
            flexDirection: "column",
            gap: "0.4rem",
          }}
        >
          <div>
            Requested Scopes: <code style={{ color: "#a5b4fc" }}>read:user, user:email, repo</code>
          </div>
          <div>Tokens encrypted at rest via Fernet &bull; Session managed with httpOnly cookies</div>
        </div>
      </div>
    </div>
  );
};
