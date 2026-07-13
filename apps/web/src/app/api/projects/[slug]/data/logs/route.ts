import { type NextRequest } from "next/server";
import { proxyDjangoGet } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// Proxy for the project-wide raw log query (paginated, filterable).
// Backs the request-detail Logs tab (trace_id correlation).
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> | { slug: string } },
) {
  const resolved = "then" in context.params ? await context.params : context.params;
  return proxyDjangoGet(request, `/projects/${resolved.slug}/data/logs`);
}
