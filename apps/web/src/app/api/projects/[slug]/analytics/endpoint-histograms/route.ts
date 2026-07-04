import { type NextRequest } from "next/server";
import { proxyDjangoWithAuth } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> | { slug: string } },
) {
  const resolved = "then" in context.params ? await context.params : context.params;
  const { slug } = resolved;
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const upstream = `${process.env.DJANGO_API_URL || "http://localhost:8000/api/v1"}/projects/${slug}/analytics/endpoint-histograms${qs ? `?${qs}` : ""}`;

  return proxyDjangoWithAuth(upstream);
}
