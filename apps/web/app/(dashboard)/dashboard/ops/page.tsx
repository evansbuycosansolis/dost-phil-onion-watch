import { redirect } from "next/navigation";

export default function OpsRootPage() {
  redirect("/dashboard/ops/geospatial/rollout");
}
