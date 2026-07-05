import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { fetchWithRefresh } from "@/lib/proxy";

// Auth/identity calls go to the identity service (AUTH_API_URL); default
// falls back to the core API's /auth path so local dev is unchanged.
const AUTH_API_URL =
  process.env.AUTH_API_URL ||
  `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/auth`;

export async function POST(request: NextRequest) {
  try {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const response = await fetchWithRefresh(`${AUTH_API_URL}/passkey/register/options`, session, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || "Failed to generate registration options" },
        { status: response.status },
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("Passkey registration options error:", error);
    return NextResponse.json(
      { error: "Failed to generate registration options" },
      { status: 500 },
    );
  }
}
