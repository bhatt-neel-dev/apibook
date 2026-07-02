import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import StandaloneShell from "@/components/dashboard/StandaloneShell";
import NotificationsPageContent from "./NotificationsPageContent";

export const metadata = {
  title: "Notifications | APILens",
};

export default async function NotificationsPage() {
  const session = await getSession();
  if (!session) {
    redirect("/auth/login");
  }

  return (
    <StandaloneShell>
      <NotificationsPageContent />
    </StandaloneShell>
  );
}
