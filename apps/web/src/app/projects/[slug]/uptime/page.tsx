import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import UptimeContent from "./UptimeContent";

export const metadata = {
  title: "Uptime | APILens",
};

export default async function ProjectUptimePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const session = await getSession();
  if (!session) {
    redirect("/auth/login");
  }

  const { slug } = await params;
  return <UptimeContent projectSlug={slug} />;
}
