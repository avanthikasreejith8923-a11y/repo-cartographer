REPO-CARTOGRAPHER SCREENSHOT ARCHIVE
====================================

The screenshots captured from the live application (http://localhost:5173) and embedded in the project README.md:

1. login.png
   - Description: Liquid Glass Authentication Portal featuring GitHub OAuth 2.0 gateway, ambient aurora glow, and security badges.
   - Route: /login

2. dashboard.png
   - Description: Tracked Repositories dashboard showing connected user account, repository cards, sync/index badges, and real-time backend service health diagnostics (Neon PostgreSQL + pgvector, Redis Cloud, ARQ Worker).
   - Route: /

3. import_modal.png
   - Description: Interactive GitHub Repository Import modal with debounced search, public/private tags, and duplicate cartography guards.
   - Route: / (Import Modal)

4. repo_detail.png
   - Description: Repository Detail view with active 8-stage Codebase Indexing progress bar, repository metadata, and action triggers.
   - Route: /repos/:id

5. commits_table.png
   - Description: Git History & Ingested Commits data table featuring monospace SHA badges, author attribution, and live indexing stage indicators.
   - Route: /repos/:id (Commits tab)
