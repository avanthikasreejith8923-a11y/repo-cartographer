import React, { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";

export const LoginView: React.FC = () => {
  const { login, sessionExpired, clearSessionExpired } = useAuth();
  const [isRedirecting, setIsRedirecting] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Handle and display login failures gracefully from URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("error")) {
      setLoginError("GitHub sign-in failed. Please try again.");
      params.delete("error");
      const newSearch = params.toString();
      const newPath = window.location.pathname + (newSearch ? `?${newSearch}` : "") + window.location.hash;
      window.history.replaceState({}, document.title, newPath);
    }
  }, []);

  const handleGitHubLogin = () => {
    if (isRedirecting) return;
    setIsRedirecting(true);
    if (clearSessionExpired) {
      clearSessionExpired();
    }
    login();
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        flex: 1,
        padding: "3rem 1.5rem",
      }}
    >
      <div
        className="glass-card"
        style={{
          width: "100%",
          maxWidth: "480px",
          padding: "2.75rem 2.25rem",
          textAlign: "center",
          position: "relative",
          borderRadius: "var(--radius-card)",
        }}
      >
        {/* Logo Tile */}
        <div style={{ marginBottom: "1.75rem" }}>
          <div
            className="brand-icon"
            style={{
              width: "56px",
              height: "56px",
              margin: "0 auto 1.25rem auto",
              fontSize: "1.35rem",
              borderRadius: "16px",
            }}
          >
            RC
          </div>

          <h1
            style={{
              fontSize: "1.85rem",
              fontWeight: 700,
              letterSpacing: "-0.035em",
              marginBottom: "0.5rem",
              color: "#ffffff",
            }}
          >
            repo-cartographer
          </h1>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "1.05rem",
              fontWeight: 400,
              lineHeight: 1.5,
            }}
          >
            Map any GitHub repo. Ask it anything.
          </p>
        </div>

        {/* Expired Session Banner */}
        {sessionExpired && (
          <div
            className="glass-card"
            style={{
              background: "rgba(245, 158, 11, 0.15)",
              border: "1px solid rgba(245, 158, 11, 0.45)",
              color: "#fbbf24",
              padding: "0.85rem 1.15rem",
              borderRadius: "var(--radius-input)",
              marginBottom: "1.5rem",
              fontSize: "0.9rem",
              fontWeight: 500,
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Your session expired. Please sign in again.</span>
          </div>
        )}

        {/* Failed Login Error Banner */}
        {loginError && (
          <div
            className="glass-card"
            style={{
              background: "rgba(244, 63, 94, 0.15)",
              border: "1px solid rgba(244, 63, 94, 0.45)",
              color: "#fca5a5",
              padding: "0.85rem 1.15rem",
              borderRadius: "var(--radius-input)",
              marginBottom: "1.5rem",
              fontSize: "0.9rem",
              fontWeight: 500,
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <span>{loginError}</span>
          </div>
        )}

        {/* Action: Continue with GitHub Button */}
        <div style={{ margin: "2rem 0 1.75rem 0" }}>
          <button
            onClick={handleGitHubLogin}
            disabled={isRedirecting}
            id="github-login-button"
            className="btn btn-github"
            style={{
              width: "100%",
              padding: "0.95rem 1.5rem",
              fontSize: "1rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
            }}
          >
            {isRedirecting ? (
              <>
                <div className="spinner-sm" />
                <span>Redirecting to GitHub...</span>
              </>
            ) : (
              <>
                <svg
                  width="22"
                  height="22"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden="true"
                  style={{ flexShrink: 0 }}
                >
                  <path
                    fillRule="evenodd"
                    clipRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                  />
                </svg>
                <span>Continue with GitHub</span>
              </>
            )}
          </button>
        </div>

        {/* Feature Highlights */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.65rem",
            textAlign: "left",
            padding: "1.25rem",
            background: "rgba(255, 255, 255, 0.04)",
            border: "1px solid rgba(255, 255, 255, 0.12)",
            borderRadius: "var(--radius-input)",
            marginBottom: "1.75rem",
          }}
        >

          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--aurora-cyan)", display: "flex" }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
            <span>Ask questions with cited answers and verifiable sources</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--aurora-cyan)", display: "flex" }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
            <span>Review pull requests with AI risk checks and duplicates detection</span>
          </div>
        </div>

        {/* Security Footer Notice */}
        <div
          style={{
            borderTop: "1px solid var(--glass-border)",
            paddingTop: "1.25rem",
            fontSize: "0.78rem",
            color: "var(--text-muted)",
            display: "flex",
            flexDirection: "column",
            gap: "0.45rem",
          }}
        >
          <div>
            Requested Scopes: <code style={{ color: "#c4b5fd" }}>read:user, user:email, repo</code>
          </div>
          <div>Tokens encrypted at rest via Fernet &bull; Session managed with httpOnly cookies</div>
        </div>
      </div>
    </div>
  );
};
