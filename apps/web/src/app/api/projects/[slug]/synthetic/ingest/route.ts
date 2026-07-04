import { NextResponse } from "next/server";
import { withAuth, apiResult } from "@/lib/proxy";
import { apiClient } from "@/lib/api-client";

const MAX_SYNTHETIC_COUNT = 50_000;
const MAX_SYNTHETIC_DAYS = 365;

export const POST = (
  request: Request,
  { params }: { params: Promise<{ slug: string }> },
) =>
  withAuth(async () => {
    const { slug } = await params;
    const body = await request.json();
    const count = Number(body.count || 0);
    if (!Number.isFinite(count) || count < 1 || count > MAX_SYNTHETIC_COUNT) {
      return NextResponse.json(
        { error: `Count must be between 1 and ${MAX_SYNTHETIC_COUNT}` },
        { status: 400 },
      );
    }
    const days = Number(body.days || 0);
    if (!Number.isFinite(days) || days < 1 || days > MAX_SYNTHETIC_DAYS) {
      return NextResponse.json(
        { error: `Days must be between 1 and ${MAX_SYNTHETIC_DAYS}` },
        { status: 400 },
      );
    }
    const scenarioKeys = Array.isArray(body.scenario_keys)
      ? body.scenario_keys.map((key: unknown) => String(key).trim()).filter(Boolean)
      : [];
    if (scenarioKeys.length === 0) {
      return NextResponse.json(
        { error: "At least one synthetic scenario must be selected" },
        { status: 400 },
      );
    }
    const rawSeed = body.seed;
    const parsedSeed = rawSeed === "" || rawSeed === undefined || rawSeed === null
      ? null
      : Number(rawSeed);
    return apiResult(await apiClient.ingestSyntheticTelemetry(slug, {
      scenario_keys: scenarioKeys,
      count,
      days,
      seed: Number.isFinite(parsedSeed) ? parsedSeed : null,
      accelerator: body.accelerator || "auto",
      include_logs: body.include_logs !== false,
      include_spans: body.include_spans !== false,
      ensure_apps: body.ensure_apps !== false,
      app_slugs: Array.isArray(body.app_slugs) ? body.app_slugs : [],
    }));
  });
