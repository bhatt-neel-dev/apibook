import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import AlertsContent from "./AlertsContent";

export const metadata = {
  title: "Alerts | APILens",
};

export default async function ProjectAlertsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const session = await getSession();
  if (!session) {
    redirect("/auth/login");
  }

  const { slug } = await params;
  return <AlertsContent projectSlug={slug} />;
}
