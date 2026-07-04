import { NextResponse } from "next/server";
import { fetchWithAuthRefresh } from "@/lib/proxy";

const AUTH_API_URL =
  process.env.AUTH_API_URL ||
  `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/auth`;

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;

    const response = await fetchWithAuthRefresh(
      `${AUTH_API_URL}/passkey/credentials/${id}`,
      { method: "DELETE" },
    );

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return NextResponse.json(
        { error: data.detail || data.error || "Failed to delete passkey" },
        { status: response.status },
      );
    }

    return NextResponse.json({ message: "Passkey deleted successfully" });
  } catch (error) {
    console.error("Delete passkey error:", error);
    return NextResponse.json(
      { error: "Failed to delete passkey" },
      { status: 500 },
    );
  }
}
