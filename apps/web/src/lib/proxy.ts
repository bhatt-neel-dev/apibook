import { NextResponse } from "next/server";
import { clearSession, getSession, setSession } from "@/lib/session";
import type { ApiResponse } from "@/lib/api-client";

const DJANGO_API_URL = process.env.DJANGO_API_URL || "http://localhost:8000/api/v1";
const AUTH_API_URL = process.env.AUTH_API_URL || `${DJANGO_API_URL}/auth`;

/**
 * Wraps a route handler with session authentication and error handling.
 * Eliminates the repetitive try/catch + session check boilerplate.
 */
export async function withAuth(
  handler: () => Promise<NextResponse>,
): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }
  try {
    return await handler();
  } catch (error) {
    console.error("Route error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

type RefreshResult = { accessToken: string; refreshToken: string } | null;

const REFRESH_CACHE_TTL_MS = 15_000;
const refreshInflight = new Map<string, Promise<RefreshResult>>();
const refreshRecent = new Map<string, { result: RefreshResult; at: number }>();

async function refreshTokens(refreshToken: string): Promise<RefreshResult> {
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
        cache: "no-store",
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

function withBearer(headers: HeadersInit | undefined, accessToken: string): Headers {
  const nextHeaders = new Headers(headers);
  if (!nextHeaders.has("Content-Type")) {
    nextHeaders.set("Content-Type", "application/json");
  }
  nextHeaders.set("Authorization", `Bearer ${accessToken}`);
  return nextHeaders;
}

export async function fetchWithAuthRefresh(
  upstream: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = await getSession();
  if (!session) {
    return Response.json({ error: "Not authenticated" }, { status: 401 });
  }

  const response = await fetch(upstream, {
    ...init,
    headers: withBearer(init.headers, session.accessToken),
    cache: init.cache || "no-store",
  });

  if (response.status !== 401) return response;

  const refreshed = await refreshTokens(session.refreshToken);
  if (!refreshed) {
    await clearSession();
    return Response.json({ error: "Session expired" }, { status: 401 });
  }

  return fetch(upstream, {
    ...init,
    headers: withBearer(init.headers, refreshed.accessToken),
    cache: init.cache || "no-store",
  });
}

async function toNextResponse(response: Response): Promise<NextResponse> {
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json",
    },
  });
}

export async function proxyDjangoWithAuth(
  upstream: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  try {
    return toNextResponse(await fetchWithAuthRefresh(upstream, init));
  } catch {
    return NextResponse.json({ error: "Upstream request failed" }, { status: 502 });
  }
}

/**
 * Converts an apiClient result into a NextResponse.
 * Optionally wraps data under a key (e.g. { sessions: [...] }).
 */
export function apiResult<T>(
  result: ApiResponse<T>,
  wrapKey?: string,
): NextResponse {
  if (result.error || !result.data) {
    return NextResponse.json(
      { error: result.error || "Request failed" },
      { status: result.status },
    );
  }
  return NextResponse.json(wrapKey ? { [wrapKey]: result.data } : result.data);
}
