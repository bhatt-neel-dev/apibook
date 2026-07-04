import { NextResponse } from "next/server";
import { fetchWithAuthRefresh } from "@/lib/proxy";

const AUTH_API_URL =
  process.env.AUTH_API_URL ||
  `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/auth`;

export async function GET() {
  try {
    const response = await fetchWithAuthRefresh(`${AUTH_API_URL}/passkey/credentials`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || "Failed to fetch passkeys" },
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
