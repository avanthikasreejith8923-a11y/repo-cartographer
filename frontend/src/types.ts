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
  created_at: string;
  updated_at: string;
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

