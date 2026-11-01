export interface User {
  id: string;
  github_id: number;
  login: string;
  name: string | null;
  avatar_url: string | null;
  email: string | null;
  created_at: string;
  updated_at: string;
}

export interface HealthStatus {
  status: string;
  database: string;
  redis: string;
  worker?: "alive" | "not running" | string;
  timestamp: string;
  phase: string;
}

export interface Repository {
  id: string;
  user_id: string;
  github_id: number;
  full_name: string;
  description: string | null;
  default_branch: string;
  language: string | null;
  is_private: boolean;
  status: "pending" | "syncing" | "ready" | "failed";
  last_synced_at: string | null;
  sync_error: string | null;
  index_status?: "none" | "indexing" | "ready" | "failed";
  indexed_commit_sha?: string | null;
  indexed_at?: string | null;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
}

export interface IndexJob {
  id: string;
  repo_id: string;
  status: "pending" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  error: string | null;
  stats?: Record<string, any>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export type SearchMode = "hybrid" | "semantic" | "keyword";

export interface SearchResultItem {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  language: string | null;
  symbol: string | null;
  kind: string;
  score: number;
  snippet: string;
  permalink: string;
}

export interface AvailableRepo {
  github_id: number;
  name: string;
  full_name: string;
  description: string | null;
  is_private: boolean;
  html_url: string | null;
  default_branch: string;
  language: string | null;
  is_imported: boolean;
}

export interface SyncJob {
  id: string;
  repo_id: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Commit {
  id: string;
  repo_id: string;
  sha: string;
  author_login: string | null;
  author_name: string | null;
  message: string;
  committed_at: string;
  additions: number | null;
  deletions: number | null;
  files_changed: number | null;
  created_at: string;
}

export interface PullRequest {
  id: string;
  repo_id: string;
  number: number;
  title: string;
  body: string | null;
  state: string;
  author_login: string | null;
  created_at: string;
  merged_at: string | null;
  closed_at: string | null;
  additions: number | null;
  deletions: number | null;
  changed_files: number | null;
  base_ref: string | null;
  head_ref: string | null;
}

export interface IssueLabel {
  id?: number;
  name: string;
  color?: string;
  description?: string;
}

export interface Issue {
  id: string;
  repo_id: string;
  number: number;
  title: string;
  body: string | null;
  state: string;
  labels: IssueLabel[];
  author_login: string | null;
  created_at: string;
  closed_at: string | null;
}

export interface SourceCitation {
  marker: string;
  path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  language: string | null;
  snippet: string;
  permalink: string;
}

export interface AskQuestionResponse {
  answer: string;
  status: "ok" | "insufficient_evidence" | "error";
  citations_missing: boolean;
  sources: SourceCitation[];
  history_id: string | null;
  latency_ms: number;
}

export interface QAHistoryItem {
  id: string;
  repo_id: string;
  user_id: string;
  question: string;
  answer: string;
  citations: SourceCitation[];
  status: "ok" | "insufficient_evidence" | "error";
  model: string;
  indexed_commit_sha: string | null;
  latency_ms: number;
  created_at: string;
}

export interface DocResponse {
  id: string | null;
  repo_id: string;
  doc_type: "architecture" | "readme";
  status: "not_started" | "pending" | "generating" | "ready" | "failed";
  content_markdown: string | null;
  citations: SourceCitation[];
  error: string | null;
  model: string | null;
  indexed_commit_sha: string | null;
  is_stale: boolean;
  generated_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PRAnalysis {
  id: string;
  repo_id: string;
  pr_number: number;
  risk_level: "low" | "medium" | "high";
  risk_score: number;
  risk_reasons: string[];
  summary_markdown: string | null;
  files_analyzed: number;
  truncated: boolean;
  status: "ok" | "error";
  error: string | null;
  model: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface IssueAnalysis {
  issue_number: number;
  issue_type: "bug" | "feature" | "question" | "documentation" | "chore" | "unclassified";
  confidence: number;
  reason: string | null;
  embedding_model: string | null;
  analyzed_at: string | null;
}

export interface DuplicateIssuePair {
  issue_a: number;
  title_a: string;
  issue_b: number;
  title_b: string;
  similarity: number;
  link_a: string;
  link_b: string;
}

export interface AnalysisJob {
  id: string;
  repo_id: string;
  kind: string;
  status: "pending" | "running" | "ready" | "failed";
  stage: string;
  progress: number;
  error: string | null;
  stats?: Record<string, any>;
  started_at: string | null;
  finished_at: string | null;
}

export interface GeneratedTest {
  id: string;
  repo_id: string;
  user_id: string;
  path: string;
  framework: string;
  content: string;
  syntax_valid: boolean | null;
  notes: string | null;
  model: string;
  indexed_commit_sha: string | null;
  created_at: string | null;
}

export interface RepoFileListResponse {
  files: string[];
  total: number;
}



