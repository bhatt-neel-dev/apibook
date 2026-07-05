import { type NextRequest } from "next/server";
import { proxyDjangoGet } from "@/lib/proxy";

export const dynamic = "force-dynamic";

// Typeahead source for the filter bar (distinct field values matching ?q=).
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> | { slug: string } },
) {
  const resolved = "then" in context.params ? await context.params : context.params;
  return proxyDjangoGet(request, `/projects/${resolved.slug}/analytics/filter-values`);
}
