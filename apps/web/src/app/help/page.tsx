import Link from "next/link";
import { redirect } from "next/navigation";
import { BookOpen, LifeBuoy, Mail, Settings } from "lucide-react";
import { getSession } from "@/lib/session";
import StandaloneShell from "@/components/dashboard/StandaloneShell";

export const metadata = {
  title: "Help & Support | APILens",
};

export default async function HelpPage() {
  const session = await getSession();
  if (!session) {
    redirect("/auth/login");
  }

  return (
    <StandaloneShell>
      <div className="apps-page">
        <div className="apps-page-header">
          <h1 className="apps-page-title">Help & Support</h1>
        </div>

        <div className="apps-grid">
          <Link href="/projects" className="app-card app-card-clickable" style={{ textDecoration: "none" }}>
            <div className="app-card-header">
              <h3 className="app-card-name">Projects</h3>
            </div>
            <p className="app-card-description">Return to your projects and apps.</p>
            <div className="app-card-meta-row">
              <span className="app-card-meta">
                <BookOpen size={12} />
                Dashboard
              </span>
            </div>
          </Link>

          <Link href="/account/general" className="app-card app-card-clickable" style={{ textDecoration: "none" }}>
            <div className="app-card-header">
              <h3 className="app-card-name">Account settings</h3>
            </div>
            <p className="app-card-description">Manage login methods, sessions, profile, and security.</p>
            <div className="app-card-meta-row">
              <span className="app-card-meta">
                <Settings size={12} />
                Settings
              </span>
            </div>
          </Link>

          <a href="mailto:support@apilens.ai" className="app-card app-card-clickable" style={{ textDecoration: "none" }}>
            <div className="app-card-header">
              <h3 className="app-card-name">Contact support</h3>
            </div>
            <p className="app-card-description">Email support when you need help with access, setup, or telemetry.</p>
            <div className="app-card-meta-row">
              <span className="app-card-meta">
                <Mail size={12} />
                support@apilens.ai
              </span>
            </div>
          </a>
        </div>

        <div className="apps-empty" style={{ marginTop: 24 }}>
          <div className="apps-empty-icon">
            <LifeBuoy size={32} />
          </div>
          <h2 className="apps-empty-title">Need setup help?</h2>
          <p className="apps-empty-text">
            Open an app setup guide from Apps, or create a new app to get framework-specific instructions.
          </p>
        </div>
      </div>
    </StandaloneShell>
  );
}
