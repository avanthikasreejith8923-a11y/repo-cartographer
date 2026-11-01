SCREENSHOT CAPTURE CHECKLIST FOR REPO-CARTOGRAPHER
=====================================================

Capture the following 6 screenshots from the web application (http://localhost:5173) and save them to this directory:

1. dashboard.png
   - Description: The main repositories dashboard showing connected GitHub account, repository list, sync/index badges, and Quick Action buttons.
   - Route: /

2. repo_search.png
   - Description: Repository view with the "Search" tab selected, showing hybrid search query results with highlighted code snippets and GitHub permalinks.
   - Route: /repos/:id (Search tab)

3. ask_answer.png
   - Description: The "Ask" codebase Q&A tab showing a question asked to Google Gemini, with a grounded response and validated clickable source citations [S1], [S2].
   - Route: /repos/:id (Ask tab)

4. architecture_doc.png
   - Description: The "Documentation" tab showing the generated Architecture overview document with tech stack breakdown, directory summary, and citation badges.
   - Route: /repos/:id (Docs tab)

5. pr_risk_badge.png
   - Description: Pull Request view showing automated PR risk assessment (Low / Medium / High / Critical) with risk factor tags, deterministic heuristic checks, and LLM summary.
   - Route: /repos/:id (PRs tab)

6. tests_tab.png
   - Description: The "Tests" tab displaying automated unit test generation for a repository source file (pytest/vitest) with syntax validation status.
   - Route: /repos/:id (Tests tab)
