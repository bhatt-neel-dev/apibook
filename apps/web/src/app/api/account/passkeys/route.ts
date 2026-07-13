import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { fetchWithRefresh } from "@/lib/proxy";

// Auth/identity calls go to the identity service (AUTH_API_URL); default
// falls back to the core API's /auth path so local dev is unchanged.
const AUTH_API_URL =
  process.env.AUTH_API_URL ||
  `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/auth`;

export async function GET(request: NextRequest) {
  try {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const response = await fetchWithRefresh(`${AUTH_API_URL}/passkey/credentials`, session, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Failed to fetch passkeys" },
        { status: response.status },
      );
    }

    return NextResponse.json({ passkeys: data });
  } catch (error) {
    console.error("Fetch passkeys error:", error);
    return NextResponse.json(
      { error: "Failed to fetch passkeys" },
      { status: 500 },
    );
  }
}
