// Phase 16A — Command Center. ONE bounded aggregation call.
import { http } from "./api.js";

export async function commandCenterSummary() {
  const { data } = await http.get("/command-center/summary");
  return data;
}
