import React from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { LoginView } from "./components/LoginView";
import { DashboardView } from "./components/DashboardView";

const AppContent: React.FC = () => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "70vh",
          gap: "1rem",
        }}
      >
        <div className="spinner" />
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
          Authenticating with repo-cartographer...
        </p>
      </div>
    );
  }

  return user ? <DashboardView /> : <LoginView />;
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <div className="app-container">
        {/* Navigation Header */}
        <header className="navbar">
          <div className="brand">
            <div className="brand-icon">RC</div>
            <span className="brand-title">repo-cartographer</span>
            <span className="brand-badge">Phase 2 / 6</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span
              style={{
                fontSize: "0.8rem",
                color: "var(--text-muted)",
                display: "none",
              }}
            >
              PostgreSQL + pgvector &bull; Redis &bull; FastAPI
            </span>
            <a
              href="https://github.com"
              target="_blank"
              rel="noreferrer"
              style={{
                color: "var(--text-secondary)",
                textDecoration: "none",
                fontSize: "0.85rem",
              }}
            >
              Docs
            </a>
          </div>
        </header>

        {/* Main View */}
        <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <AppContent />
        </main>

        {/* Footer */}
        <footer
          style={{
            borderTop: "1px solid var(--border-color)",
            padding: "1.25rem 2rem",
            textAlign: "center",
            fontSize: "0.8rem",
            color: "var(--text-muted)",
          }}
        >
          repo-cartographer &copy; 2026 &bull; AI Developer Productivity Platform &bull; Phase 2: Repository Ingestion &amp; Async Sync
        </footer>
      </div>
    </AuthProvider>
  );
};

export default App;
