import { NextRequest, NextResponse } from "next/server";
import { fetchWithAuthRefresh } from "@/lib/proxy";

const AUTH_API_URL =
  process.env.AUTH_API_URL ||
  `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/auth`;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await fetchWithAuthRefresh(`${AUTH_API_URL}/passkey/register/verify`, {
      method: "POST",
      body: JSON.stringify({
        credential: body.credential,
        challenge: body.challenge,
        device_name: body.device_name || "Unnamed Device",
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || "Failed to verify passkey" },
        { status: response.status },
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("Passkey registration verify error:", error);
    return NextResponse.json(
      { error: "Failed to verify passkey" },
      { status: 500 },
    );
  }
}
