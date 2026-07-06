import { withAuth, apiResult } from "@/lib/proxy";
import { apiClient } from "@/lib/api-client";

export const POST = (
  _request: Request,
  { params }: { params: Promise<{ slug: string; alertId: string }> },
) =>
  withAuth(async () => {
    const { slug, alertId } = await params;
    return apiResult(await apiClient.dismissAlert(slug, alertId));
  });
