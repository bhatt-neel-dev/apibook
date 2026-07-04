import { withAuth, apiResult } from "@/lib/proxy";
import { apiClient } from "@/lib/api-client";

export const GET = (
  _request: Request,
  { params }: { params: Promise<{ slug: string }> },
) =>
  withAuth(async () => {
    const { slug } = await params;
    return apiResult(await apiClient.getSyntheticScenarios(slug), "scenarios");
  });
