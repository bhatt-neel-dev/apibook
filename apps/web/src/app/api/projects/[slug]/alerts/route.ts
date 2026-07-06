import { type NextRequest } from "next/server";
import { withAuth, apiResult } from "@/lib/proxy";
import { apiClient } from "@/lib/api-client";

export const GET = (
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) =>
  withAuth(async () => {
    const { slug } = await params;
    const status = new URL(request.url).searchParams.get("status") || "active";
    return apiResult(await apiClient.getProjectAlerts(slug, status), "alerts");
  });
