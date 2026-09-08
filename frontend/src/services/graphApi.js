// ─── Phase 14 §12 — Investigation Graph ──────────────────────────────────
// Deterministic graph built only from persisted relational records.
import { http } from "./api.js";

export async function investigationGraph(plate) {
  const { data } = await http.get("/ai/graph", { params: { plate } });
  return data;
}
