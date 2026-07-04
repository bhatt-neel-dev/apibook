import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import SyntheticDataContent from "./SyntheticDataContent";

export const metadata = {
  title: "Synthetic Data | APILens",
};

export default async function ProjectSyntheticDataPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const session = await getSession();
  if (!session) {
    redirect("/auth/login");
  }

  const { slug } = await params;
  return <SyntheticDataContent projectSlug={slug} />;
}
