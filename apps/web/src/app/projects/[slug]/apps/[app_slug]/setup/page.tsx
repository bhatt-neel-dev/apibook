"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AppSetupGuide from "@/components/apps/AppSetupGuide";
import type { FrameworkId } from "@/types/app";

interface SetupMeta {
  appName: string;
  framework: FrameworkId;
  apiKeyPrefix: string;
  projectSlug: string;
  projectName?: string;
  createdAt: number;
}

export default function ProjectAppSetupPage() {
  const router = useRouter();
  const params = useParams();
  const projectSlug = params.slug as string;
  const appSlug = params.app_slug as string;

  const [meta, setMeta] = useState<SetupMeta | null>(null);
  const [projectName, setProjectName] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;

    const metaKey = `apilens_setup_meta_${projectSlug}_${appSlug}`;
    const legacyMetaKey = `apilens_setup_meta_${appSlug}`;
    const rawMeta = window.localStorage.getItem(metaKey) || window.localStorage.getItem(legacyMetaKey);

    if (rawMeta) {
      try {
        setMeta(JSON.parse(rawMeta));
        setLoading(false);
        return;
      } catch {
        // ignore
      }
    }

    async function loadSetupMeta() {
      try {
        const [appRes, keysRes] = await Promise.all([
          fetch(`/api/projects/${projectSlug}/apps/${appSlug}`),
          fetch(`/api/projects/${projectSlug}/api-keys`),
        ]);

        if (!appRes.ok) {
          if (!cancelled) router.replace(`/projects/${projectSlug}/apps`);
          return;
        }

        const app = await appRes.json();
        const keysData = keysRes.ok ? await keysRes.json().catch(() => ({})) : {};
        const keys = Array.isArray(keysData)
          ? keysData
          : Array.isArray(keysData.keys)
            ? keysData.keys
            : [];

        if (!cancelled) {
          setMeta({
            appName: app.name || appSlug,
            framework: app.framework || "fastapi",
            apiKeyPrefix: keys.length > 0 ? keys[0].prefix : "apilens_****",
            projectSlug,
            createdAt: Date.now(),
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadSetupMeta();

    return () => {
      cancelled = true;
    };
  }, [appSlug, projectSlug, router]);

  useEffect(() => {
    let cancelled = false;

    async function loadProjectName() {
      if (!projectSlug) return;
      try {
        const res = await fetch(`/api/projects/${projectSlug}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) {
          setProjectName(data.name || projectSlug);
        }
      } catch {
        if (!cancelled) {
          setProjectName("");
        }
      }
    }

    loadProjectName();
    return () => {
      cancelled = true;
    };
  }, [projectSlug]);

  if (loading) {
    return (
      <div style={{ padding: "32px", textAlign: "center" }}>
        <p>Loading setup guide...</p>
      </div>
    );
  }

  if (!meta) return null;

  return (
    <div className="create-app-container">
      <AppSetupGuide
        appName={meta.appName}
        framework={meta.framework}
        apiKey={`${meta.apiKeyPrefix}********`}
        hasRawKey={false}
        appSlug={appSlug}
        projectSlug={projectSlug}
        projectName={projectName || meta.projectName}
      />
    </div>
  );
}
