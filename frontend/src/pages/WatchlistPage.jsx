import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Download, Plus, RefreshCw, ShieldAlert, Upload } from "lucide-react";
import { C } from "../theme.js";
import { canManageOps } from "../services/api.js";
import { useToast } from "../context/ToastContext.jsx";
import {
  activateWatchlistEntry, createWatchlistEntry, deactivateWatchlistEntry,
  downloadWatchlistCSV, importWatchlistCSV, listWatchlist, updateWatchlistEntry,
  watchlistCategories,
} from "../services/opsApi.js";
import SeverityBadge from "../components/SeverityBadge.jsx";
import EmptyState from "../components/ui/EmptyState.jsx";
import ErrorBanner from "../components/ui/ErrorBanner.jsx";
import { SkeletonRows } from "../components/ui/Skeleton.jsx";
import { Pager } from "./IncidentsPage.jsx";
import { fmtDateTime } from "../utils/datetime.js";

const PAGE = 25;
const STATUS = ["", "effective", "pending", "expired", "inactive"];

export default function WatchlistPage() {
  const { push } = useToast();
  const manage = canManageOps();
  const fileRef = useRef(null);

  const [data, setData] = useState(null);
  const [cats, setCats] = useState(["STOLEN", "WANTED", "SUSPICIOUS", "MISSING", "INVESTIGATION", "OTHER"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("recent");
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState({ plate_number: "", offense_category: "STOLEN", priority_level: "MEDIUM", reason: "", description: "", effective_from: "", expires_at: "" });
  const [importResult, setImportResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params = { limit: PAGE, offset, sort };
      if (q.trim()) params.q = q.trim();
      if (category) params.category = category;
      if (status) params.status = status;
      setData(await listWatchlist(params));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [offset, sort, q, category, status]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setOffset(0); }, [category, status, sort]);
  useEffect(() => { watchlistCategories().then(setCats).catch(() => {}); }, []);

  const act = async (fn, msg) => {
    setBusy(true);
    try { await fn(); push({ title: msg, severity: "medium" }); load(); }
    catch (e) { push({ title: "Action failed", msg: e?.response?.data?.error?.message || "", severity: "high" }); }
    finally { setBusy(false); }
  };

  const submitNew = () => act(async () => {
    const payload = { ...form };
    if (!payload.effective_from) delete payload.effective_from;
    if (!payload.expires_at) delete payload.expires_at;
    await createWatchlistEntry(payload);
    setShowNew(false);
    setForm({ plate_number: "", offense_category: "STOLEN", priority_level: "MEDIUM", reason: "", description: "", effective_from: "", expires_at: "" });
  }, "Watchlist entry added");

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const r = await importWatchlistCSV(file, false);
      setImportResult(r);
      push({ title: `Import: ${r.created} created, ${r.updated} updated, ${r.skipped} skipped, ${r.invalid} invalid`, severity: r.invalid ? "high" : "medium" });
      load();
    } catch (err) {
      push({ title: "Import failed", msg: err?.response?.data?.error?.message || "", severity: "high" });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const items = data?.items || [];
  const total = data?.total || 0;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
        <ShieldAlert size={16} color={C.accent} />
        <span style={{ fontWeight: 700, fontSize: 15 }}>Watchlist Management</span>
        <span style={{ color: C.muted, fontSize: 12 }}>· {total}</span>
        <button onClick={load} style={iconBtn} title="Refresh"><RefreshCw size={12} /></button>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {manage && <button onClick={() => setShowNew((v) => !v)} style={{ ...iconBtn, color: C.accent }}><Plus size={12} /> Add</button>}
          {manage && <button onClick={() => fileRef.current?.click()} style={iconBtn} disabled={busy}><Upload size={12} /> Import CSV</button>}
          {manage && <button onClick={downloadWatchlistCSV} style={iconBtn}><Download size={12} /> Export CSV</button>}
          <input ref={fileRef} type="file" accept=".csv" hidden onChange={onImport} />
        </div>
      </div>
      <div style={{ color: C.muted, fontSize: 11, marginBottom: 12 }}>
        The matching engine uses only currently-effective entries (active · within effective window · not expired).
      </div>

      {error && <ErrorBanner message="Could not load the watchlist." onRetry={load} />}

      {importResult && (
        <div style={{ ...panel, padding: 12, marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <strong style={{ fontSize: 12 }}>
              Import summary — {importResult.created} created · {importResult.updated} updated · {importResult.skipped} skipped · {importResult.invalid} invalid
            </strong>
            <button style={linkBtn} onClick={() => setImportResult(null)}>dismiss</button>
          </div>
          {importResult.rows.filter((r) => r.outcome === "invalid" || r.outcome === "skipped").slice(0, 20).map((r, i) => (
            <div key={i} style={{ fontSize: 10, color: r.outcome === "invalid" ? C.red : C.amber }}>
              line {r.line}: {r.plate || "?"} — {r.outcome}{r.reason ? ` (${r.reason})` : ""}
            </div>
          ))}
        </div>
      )}

      {showNew && manage && (
        <div style={{ ...panel, padding: 12, marginBottom: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 8 }}>
          <F label="Plate *"><input value={form.plate_number} onChange={(e) => setForm({ ...form, plate_number: e.target.value })} style={{ ...input, fontFamily: "monospace" }} /></F>
          <F label="Category"><select value={form.offense_category} onChange={(e) => setForm({ ...form, offense_category: e.target.value })} style={input}>{cats.map((c) => <option key={c}>{c}</option>)}</select></F>
          <F label="Priority"><select value={form.priority_level} onChange={(e) => setForm({ ...form, priority_level: e.target.value })} style={input}>{["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => <option key={p}>{p}</option>)}</select></F>
          <F label="Effective from"><input type="datetime-local" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} style={input} /></F>
          <F label="Expires at"><input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} style={input} /></F>
          <F label="Reason"><input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} style={input} /></F>
          <F label="Description"><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={input} /></F>
          <div style={{ alignSelf: "end" }}>
            <button style={primaryBtn} disabled={busy || !form.plate_number.trim()} onClick={submitNew}>Create</button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, alignItems: "center" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
               placeholder="Search plate…" style={{ ...input, flex: "1 1 180px" }} />
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={input}>
          <option value="">All categories</option>{cats.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} style={input}>
          {STATUS.map((s) => <option key={s} value={s}>{s ? s : "All statuses"}</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} style={input}>
          {["recent", "plate", "priority", "expiry"].map((s) => <option key={s} value={s}>sort: {s}</option>)}
        </select>
      </div>

      <div style={panel}>
        {loading ? (
          <div style={{ padding: 14 }}><SkeletonRows rows={6} height={40} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={ShieldAlert} title="No watchlist entries" />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: C.muted, textAlign: "left", fontSize: 10, textTransform: "uppercase" }}>
                  <th style={th}>Plate</th><th style={th}>Category</th><th style={th}>Priority</th>
                  <th style={th}>Effective</th><th style={th}>Expires</th><th style={th}>State</th>
                  <th style={th}>Updated by</th>{manage && <th style={th}>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((w) => (
                  <tr key={w.id} style={{ borderTop: `1px solid ${C.border}`, opacity: w.is_currently_effective ? 1 : 0.6 }}>
                    <td style={{ ...td, fontFamily: "monospace", color: C.amber }}>{w.plate_number_normalized}</td>
                    <td style={{ ...td, color: C.muted }}>
                      {w.offense_category}
                      {w.description ? <div style={{ fontSize: 9 }}>{w.description}</div> : null}
                    </td>
                    <td style={td}><SeverityBadge s={String(w.priority_level).toLowerCase()} /></td>
                    <td style={{ ...td, color: C.muted, fontSize: 10 }}>{w.effective_from ? fmtDateTime(w.effective_from) : "immediate"}</td>
                    <td style={{ ...td, color: w.is_expired ? C.red : C.muted, fontSize: 10 }}>{w.expires_at ? fmtDateTime(w.expires_at) : "never"}</td>
                    <td style={td}>
                      {!w.active && <Tag c={C.muted}>inactive</Tag>}
                      {w.active && w.is_expired && <Tag c={C.red}><AlertTriangle size={9} /> expired</Tag>}
                      {w.active && w.is_pending && <Tag c={C.violet}>pending</Tag>}
                      {w.is_currently_effective && <Tag c={C.green}>effective</Tag>}
                    </td>
                    <td style={{ ...td, color: C.dim, fontSize: 10 }}>{w.updated_by_username || w.added_by_username || "—"}</td>
                    {manage && (
                      <td style={td}>
                        <div style={{ display: "flex", gap: 6 }}>
                          <button style={linkBtn} disabled={busy}
                                  onClick={() => {
                                    const p = window.prompt("New priority (CRITICAL/HIGH/MEDIUM/LOW):", w.priority_level);
                                    if (p) act(() => updateWatchlistEntry(w.id, { priority_level: p.toUpperCase() }), "Updated");
                                  }}>edit</button>
                          {w.active
                            ? <button style={{ ...linkBtn, color: C.red }} disabled={busy}
                                      onClick={() => window.confirm("Deactivate this entry?") && act(() => deactivateWatchlistEntry(w.id), "Deactivated")}>disable</button>
                            : <button style={{ ...linkBtn, color: C.green }} disabled={busy}
                                      onClick={() => act(() => activateWatchlistEntry(w.id), "Activated")}>activate</button>}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Pager offset={offset} total={total} onPage={setOffset} loading={loading} page={PAGE} />
    </div>
  );
}

const Tag = ({ c, children }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: c, border: `1px solid ${c}44`, borderRadius: 3, padding: "0 5px", fontSize: 9, fontWeight: 700, textTransform: "uppercase", marginRight: 3 }}>{children}</span>
);
const F = ({ label, children }) => (
  <label style={{ fontSize: 10, color: C.muted, display: "flex", flexDirection: "column", gap: 3 }}>{label}{children}</label>
);
const panel = { background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: "hidden" };
const th = { padding: "9px 12px" };
const td = { padding: "9px 12px", verticalAlign: "top" };
const input = { background: C.panel, border: `1px solid ${C.border}`, color: C.text, borderRadius: 4, padding: "5px 8px", fontSize: 11 };
const iconBtn = { ...input, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 };
const linkBtn = { background: "transparent", border: "none", color: C.accent, fontSize: 10, cursor: "pointer", padding: 0 };
const primaryBtn = { background: C.accent, color: "#0b0f14", border: "none", borderRadius: 4, padding: "7px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer" };
