# Repo Cartographer — 2-Minute Demo Video Script

**Target Duration**: 2 minutes (120 seconds)  
**Setup Before Recording**:
1. Run `.\scripts\dev-all.ps1` to launch Backend API, Worker, and Frontend.
2. Open `http://localhost:5173` in a clean browser window (1080p, 100% zoom).
3. Ensure at least one repository is synced and indexed (e.g. `studyhive`).

---

### [0:00 - 0:20] Introduction & Repository Dashboard
- **Screen**: Main Dashboard (`/`) showing the imported repository card, branch status, and "v1.0" header badge.
- **Action**: Hover over the repository card. Point out the synced commit SHA, chunk count, and green "Ready" status indicators.
- **Audio / Script**:
  > "Welcome to Repo Cartographer, an AI-powered codebase exploration and intelligence platform built on Google Gemini, Neon serverless Postgres with pgvector, and Redis Cloud.
  > Here on the dashboard, you can see our imported GitHub repositories. Metadata, tree structures, and commit histories are synced asynchronously in background worker queues."

---

### [0:20 - 0:45] Hybrid Code Search (BM25 + Semantic Vector Search)
- **Screen**: Click into the repository and select the **Search** tab.
- **Action**: In the search box, type `database models` or `authentication` and press Enter. Click on the first result to expand the snippet and highlight the GitHub permalink.
- **Audio / Script**:
  > "First, let's explore code search. Repo Cartographer uses Reciprocal Rank Fusion to combine full-text keyword search with dense 768-dimensional Gemini embeddings stored in pgvector.
  > Notice the sub-second hybrid results: each matching chunk includes line ranges, symbols, and direct permalinks back to the exact lines in GitHub."

---

### [0:45 - 1:15] Grounded Codebase Q&A (Ask) with Citations
- **Screen**: Navigate to the **Ask** tab.
- **Action**: Type: *"What is the primary architecture and purpose of this codebase?"* and click **Ask Question**.
- **Audio / Script**:
  > "Next is Ask—our grounded codebase Q&A. Instead of hallucinating, Repo Cartographer retrieves the most relevant semantic chunks across the codebase and feeds them into Gemini with strict grounding instructions.
  > The response is generated in real-time, accompanied by strict, validated source citations. Hovering or clicking any citation marker takes you directly to the source chunk that proved the claim."

---

### [1:15 - 1:40] AI Architecture Documentation Generation
- **Screen**: Switch to the **Documentation** tab.
- **Action**: Click on the **Architecture** sub-tab. If generated, view the structured markdown; if empty, click **Generate Architecture**.
- **Audio / Script**:
  > "Under Documentation, Repo Cartographer can synthesize an entire architectural blueprint of the codebase.
  > It inspects manifests, entry points, service layers, and schema definitions to produce structured overview documentation, complete with technology stacks, component hierarchies, and citation references."

---

### [1:40 - 2:00] Unit Test Generation & Robust System Design
- **Screen**: Switch to the **Tests** tab.
- **Action**: Select a source file (e.g., Python or JavaScript) and click **Generate Tests**. Show the generated test suite and syntax verification badge.
- **Audio / Script**:
  > "Finally, the Tests tab generates automated unit tests tailored to the project's testing framework—such as Pytest or Vitest—with automatic AST syntax verification.
  > Behind the scenes, the system features rate-limit pacing, exponential backoff with jitter for Gemini 429s, and atomic multi-stage background workers. Repo Cartographer delivers reliable codebase intelligence at scale."
