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
