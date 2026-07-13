import { getSession, setSession, clearSession } from "./session";
import type { FrameworkId } from "@/types/app";

const DJANGO_API_URL = process.env.DJANGO_API_URL || "http://localhost:8000/api/v1";

// Identity (IAM) service base for token issuance/validation. In production
// AUTH_API_URL points at the dedicated identity service (internal
// http://identity:8000/v1); when unset it falls back to the core API's /auth
// path so local dev is unchanged. (Authenticated settings calls — 2FA, etc. —
// keep flowing through fetchDjango / the back-compat alias.)
const AUTH_API_URL =
  process.env.AUTH_API_URL || `${DJANGO_API_URL}/auth`;

export interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

export interface DjangoUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  email_verified: boolean;
  has_password: boolean;
  timezone: string;
  created_at: string;
  last_login_at: string | null;
}

export interface DjangoUserContext {
  id: string;
  email: string;
  display_name: string;
  is_authenticated: boolean;
  permissions: string[];
  role: string;
}

export interface SessionInfo {
  id: string;
  device_info: string;
  ip_address: string | null;
  location: string;
  last_used_at: string;
  created_at: string;
  is_current: boolean;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResult {
  key: string;
  id: string;
  name: string;
  prefix: string;
  created_at: string;
}

export interface ProjectInfo {
  id: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export type ProjectRole = "owner" | "admin" | "member" | "viewer";

export interface ProjectMember {
  id: string | null;
  user_id: string;
  email: string;
  name: string;
  role: ProjectRole;
  is_owner: boolean;
  is_you: boolean;
}

export interface ProjectInvitation {
  id: string;
  email: string;
  role: ProjectRole;
  expires_at: string;
  created_at: string;
}

export interface ProjectMembersResult {
  members: ProjectMember[];
  invitations: ProjectInvitation[];
  your_role: ProjectRole;
}

export interface InviteInfo {
  valid: boolean;
  email: string;
  role: ProjectRole | "";
  project_name: string;
  project_slug: string;
  inviter: string;
}

export interface PendingInvitation {
  id: string;
  project_name: string;
  project_slug: string;
  role: ProjectRole;
  inviter: string;
  created_at: string;
  expires_at: string;
}

export interface AcceptResult {
  message: string;
  project_slug: string;
  project_name: string;
}

export interface ProjectListItem {
  id: string;
  name: string;
  slug: string;
  description: string;
  app_count: number;
  created_at: string;
}

export interface AppInfo {
  id: string;
  name: string;
  slug: string;
  description: string;
  framework: FrameworkId;
  created_at: string;
  updated_at: string;
}

export interface AppListItem {
  id: string;
  name: string;
  slug: string;
  description: string;
  framework: FrameworkId;
  api_key_count: number;
  created_at: string;
}

async function fetchDjango<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<ApiResponse<T>> {
  const session = await getSession();
  if (!session) {
    return { error: "Not authenticated", status: 401 };
  }

  // Auth/identity endpoints (2FA, etc.) live on the identity service, not the
  // core API. Route "/auth/*" to AUTH_API_URL (dropping the "/auth" segment,
  // since AUTH_API_URL is already the auth base); everything else -> core.
  const url = endpoint.startsWith("/auth/")
    ? `${AUTH_API_URL}${endpoint.slice("/auth".length)}`
    : `${DJANGO_API_URL}${endpoint}`;

  try {
    let response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        ...options.headers,
      },
    });

    // Auto-refresh on 401
    if (response.status === 401) {
      const refreshResult = await refreshTokens(session.refreshToken);
      if (!refreshResult) {
        await clearSession();
        return { error: "Session expired", status: 401 };
      }

      response = await fetch(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${refreshResult.accessToken}`,
          ...options.headers,
        },
      });
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        error: errorData.detail || errorData.error || `Request failed with status ${response.status}`,
        status: response.status,
      };
    }

    const data = await response.json();
    return { data, status: response.status };
  } catch (error) {
    console.error(`API error (${endpoint}):`, error);
    return {
      error: error instanceof Error ? error.message : "Unknown error",
      status: 500,
    };
  }
}

// Refresh-token rotation is single-use with family-reuse detection on the
// backend: presenting an already-rotated token wipes the whole session family.
// The dashboard fires many parallel requests that all carry the SAME refresh
// token, so on a 401 wave they must ALL resolve to the one rotated token —
// never re-present the old one. We coalesce two ways, keyed by the presented
// token:
//   • in-flight map  — concurrent callers share the one /refresh promise;
//   • recent cache   — callers that 401 just *after* it settled still get the
//                      already-rotated result instead of refreshing again.
export type RefreshResult = { accessToken: string; refreshToken: string } | null;
const REFRESH_CACHE_TTL_MS = 15_000;
const refreshInflight = new Map<string, Promise<RefreshResult>>();
const refreshRecent = new Map<string, { result: RefreshResult; at: number }>();

export async function refreshTokens(refreshToken: string): Promise<RefreshResult> {
  const cached = refreshRecent.get(refreshToken);
  if (cached && Date.now() - cached.at < REFRESH_CACHE_TTL_MS) {
    return cached.result;
  }

  const existing = refreshInflight.get(refreshToken);
  if (existing) return existing;

  const inflight = (async (): Promise<RefreshResult> => {
    try {
      const response = await fetch(`${AUTH_API_URL}/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) return null;

      const data = await response.json();

      const session = await getSession();
      if (session) {
        await setSession({
          ...session,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
        });
      }

      return {
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      };
    } catch {
      return null;
    }
  })();

  refreshInflight.set(refreshToken, inflight);
  try {
    const result = await inflight;
    // Remember the outcome briefly so the rest of the herd reuses it.
    refreshRecent.set(refreshToken, { result, at: Date.now() });
    if (refreshRecent.size > 50) {
      const cutoff = Date.now() - REFRESH_CACHE_TTL_MS;
      for (const [key, val] of refreshRecent) {
        if (val.at < cutoff) refreshRecent.delete(key);
      }
    }
    return result;
  } finally {
    refreshInflight.delete(refreshToken);
  }
}

export const apiClient = {
  async getCurrentUser(): Promise<ApiResponse<DjangoUser>> {
    return fetchDjango<DjangoUser>("/users/me");
  },

  async getUserContext(): Promise<ApiResponse<DjangoUserContext>> {
    return fetchDjango<DjangoUserContext>("/users/context");
  },

  async updateProfile(data: {
    first_name?: string;
    last_name?: string;
    timezone?: string;
  }): Promise<ApiResponse<DjangoUser>> {
    return fetchDjango<DjangoUser>("/users/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async deleteAccount(): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>("/users/me", {
      method: "DELETE",
    });
  },

  async logoutAll(): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>("/users/logout-all", {
      method: "POST",
    });
  },

  async logoutOthers(): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>("/users/logout-others", {
      method: "POST",
    });
  },

  // ── Two-Factor Authentication ─────────────────────────────────────
  // These go through fetchDjango so they automatically refresh the access
  // token if it's expired (15-min lifetime). Otherwise a stale settings tab
  // would throw 401 the first time the user touches a 2FA action.

  async twoFactorStatus(): Promise<ApiResponse<{ enabled: boolean; backup_codes_remaining: number }>> {
    return fetchDjango("/auth/2fa/status");
  },

  async twoFactorEnable(): Promise<ApiResponse<{ secret: string; qr_code_uri: string }>> {
    return fetchDjango("/auth/2fa/enable", { method: "POST" });
  },

  async twoFactorVerify(payload: { code: string; password?: string }): Promise<ApiResponse<{ codes: string[] }>> {
    return fetchDjango("/auth/2fa/verify", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async twoFactorDisable(payload: { password?: string; code?: string; backup_code?: string }): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango("/auth/2fa/disable", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async twoFactorRegenerateBackupCodes(): Promise<ApiResponse<{ codes: string[] }>> {
    return fetchDjango("/auth/2fa/backup-codes/regenerate", { method: "POST" });
  },

  async setPassword(payload: {
    new_password: string;
    confirm_password: string;
    current_password?: string;
  }): Promise<ApiResponse<{ message: string; access_token: string; refresh_token: string }>> {
    return fetchDjango("/users/me/password", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getSessions(): Promise<ApiResponse<SessionInfo[]>> {
    return fetchDjango<SessionInfo[]>("/users/sessions");
  },

  async revokeSession(
    sessionId: string,
  ): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/users/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  // ── Projects ──────────────────────────────────────────────────────

  async getProjects(): Promise<ApiResponse<ProjectListItem[]>> {
    return fetchDjango<ProjectListItem[]>("/projects/");
  },

  async getProject(slug: string): Promise<ApiResponse<ProjectInfo>> {
    return fetchDjango<ProjectInfo>(`/projects/${slug}`);
  },

  async createProject(data: { name: string; description?: string }): Promise<ApiResponse<ProjectInfo>> {
    return fetchDjango<ProjectInfo>("/projects/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateProject(slug: string, data: { name?: string; description?: string }): Promise<ApiResponse<ProjectInfo>> {
    return fetchDjango<ProjectInfo>(`/projects/${slug}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async deleteProject(slug: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${slug}`, {
      method: "DELETE",
    });
  },

  // ── Project-scoped API Keys ────────────────────────────────────────

  async getProjectApiKeys(projectSlug: string): Promise<ApiResponse<ApiKeyInfo[]>> {
    return fetchDjango<ApiKeyInfo[]>(`/projects/${projectSlug}/api-keys`);
  },

  async createProjectApiKey(projectSlug: string, name: string): Promise<ApiResponse<ApiKeyCreateResult>> {
    return fetchDjango<ApiKeyCreateResult>(`/projects/${projectSlug}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  },

  async revokeProjectApiKey(projectSlug: string, keyId: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/api-keys/${keyId}`, {
      method: "DELETE",
    });
  },

  // ── Project Members & Invitations ──────────────────────────────────

  async getProjectMembers(projectSlug: string): Promise<ApiResponse<ProjectMembersResult>> {
    return fetchDjango<ProjectMembersResult>(`/projects/${projectSlug}/members`);
  },

  async inviteProjectMember(projectSlug: string, email: string, role: string): Promise<ApiResponse<ProjectInvitation>> {
    return fetchDjango<ProjectInvitation>(`/projects/${projectSlug}/members/invite`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    });
  },

  async updateMemberRole(projectSlug: string, memberId: string, role: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/members/${memberId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  },

  async removeProjectMember(projectSlug: string, memberId: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/members/${memberId}`, {
      method: "DELETE",
    });
  },

  async revokeProjectInvitation(projectSlug: string, inviteId: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/invitations/${inviteId}`, {
      method: "DELETE",
    });
  },

  async getInviteInfo(token: string): Promise<ApiResponse<InviteInfo>> {
    return fetchDjango<InviteInfo>(`/auth/invite-info`, {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  async acceptInvitation(token: string): Promise<ApiResponse<AcceptResult>> {
    return fetchDjango<AcceptResult>(`/projects/invitations/accept`, {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  async declineInvitationByToken(token: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/invitations/decline`, {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  async getPendingInvitations(): Promise<ApiResponse<PendingInvitation[]>> {
    return fetchDjango<PendingInvitation[]>(`/projects/invitations/pending`);
  },

  async acceptInvitationById(inviteId: string): Promise<ApiResponse<AcceptResult>> {
    return fetchDjango<AcceptResult>(`/projects/invitations/${inviteId}/accept`, {
      method: "POST",
    });
  },

  async declineInvitation(inviteId: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/invitations/${inviteId}/decline`, {
      method: "POST",
    });
  },

  // ── Apps (Project-scoped) ─────────────────────────────────────────

  async getProjectApps(projectSlug: string): Promise<ApiResponse<AppListItem[]>> {
    return fetchDjango<AppListItem[]>(`/projects/${projectSlug}/apps`);
  },

  async createProjectApp(projectSlug: string, data: { name: string; slug?: string; description?: string; framework?: "fastapi" | "flask" | "django" | "starlette" }): Promise<ApiResponse<AppInfo>> {
    return fetchDjango<AppInfo>(`/projects/${projectSlug}/apps`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getProjectApp(projectSlug: string, appSlug: string): Promise<ApiResponse<AppInfo>> {
    return fetchDjango<AppInfo>(`/projects/${projectSlug}/apps/${appSlug}`);
  },

  async updateProjectApp(projectSlug: string, appSlug: string, data: { name?: string; description?: string; framework?: string }): Promise<ApiResponse<AppInfo>> {
    return fetchDjango<AppInfo>(`/projects/${projectSlug}/apps/${appSlug}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async deleteProjectApp(projectSlug: string, appSlug: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/apps/${appSlug}`, {
      method: "DELETE",
    });
  },

  async getProjectAppApiKeys(projectSlug: string, appSlug: string): Promise<ApiResponse<{ keys: ApiKeyInfo[] }>> {
    return fetchDjango<{ keys: ApiKeyInfo[] }>(`/projects/${projectSlug}/apps/${appSlug}/api-keys`);
  },

  async createProjectAppApiKey(projectSlug: string, appSlug: string, data: { name: string }): Promise<ApiResponse<ApiKeyCreateResult>> {
    return fetchDjango<ApiKeyCreateResult>(`/projects/${projectSlug}/apps/${appSlug}/api-keys`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async revokeProjectAppApiKey(projectSlug: string, appSlug: string, keyId: string): Promise<ApiResponse<{ message: string }>> {
    return fetchDjango<{ message: string }>(`/projects/${projectSlug}/apps/${appSlug}/api-keys/${keyId}`, {
      method: "DELETE",
    });
  },

  async validateSession(refreshToken: string): Promise<ApiResponse<{ valid: boolean }>> {
    try {
      const response = await fetch(`${AUTH_API_URL}/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      const data = await response.json();
      return { data, status: response.status };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : "Validation failed",
        status: 500,
      };
    }
  },

  async healthCheck(): Promise<
    ApiResponse<{ status: string; service: string }>
  > {
    try {
      const response = await fetch(`${DJANGO_API_URL}/health`);
      const data = await response.json();
      return { data, status: response.status };
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : "Unknown error",
        status: 500,
      };
    }
  },
};
