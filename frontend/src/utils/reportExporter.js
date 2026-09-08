// ─── Client-Side PDF / CSV Investigation Report Exporter (Vishakha) ──────────
// DEVELOPER_README §14.9 / §9.7 — jsPDF compiles a structured vehicle movement
// report; downloads as `<PLATE>_Report.pdf`. Pure client-side, no backend.
import { jsPDF } from "jspdf";
import { formatPlate, normalizePlate } from "./plate.js";

const fmt = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString("en-IN", { hour12: false });
};

export function exportVehicleReportPDF(result) {
  if (!result) return;
  const plate = normalizePlate(result.plate);
  const doc = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const margin = 48;
  let y = margin;

  const line = (text, { size = 10, bold = false, color = [40, 40, 40], gap = 16 } = {}) => {
    if (y > pageH - margin) {
      doc.addPage();
      y = margin;
    }
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    doc.setTextColor(...color);
    doc.text(String(text), margin, y);
    y += gap;
  };

  // Header
  doc.setFillColor(18, 22, 28);
  doc.rect(0, 0, pageW, 70, "F");
  doc.setTextColor(230, 234, 238);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("SENTINEL — Vehicle Investigation Report", margin, 34);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(150, 160, 175);
  doc.text("Gujarat Police · Integrated CCTV & Video Analytics Command Center", margin, 50);
  y = 96;

  line(`Target plate: ${formatPlate(plate)}`, { size: 13, bold: true, gap: 20 });
  line(`Report generated: ${new Date().toLocaleString("en-IN", { hour12: false })}`, { size: 9, color: [110, 110, 110] });
  y += 6;

  // Summary
  line("Vehicle Profile Summary", { size: 11, bold: true, gap: 18 });
  line(`First seen        : ${fmt(result.firstSeen)}`);
  line(`Last seen         : ${fmt(result.lastSeen)}`);
  line(`Total sightings   : ${result.totalSightings}`);
  line(`Distinct cameras  : ${result.cameraCount}`);
  line(
    `Vehicle type      : ${
      (result.vehicleTypes || []).length ? result.vehicleTypes.join(" / ") : "Unclassified"
    }`
  );
  line(
    `Journey           : ${
      result.isSingleSighting
        ? "Single camera sighting — no journey to plot"
        : result.hasJourney
        ? "Camera-sighting trail (chronological, not GPS)"
        : "Insufficient geolocated sightings to plot a trail"
    }`
  );
  line(`Watchlist status  : ${result.watchlistHit ? "ACTIVE WATCHLIST HIT" : "No active watchlist hit"}`, {
    bold: result.watchlistHit,
    color: result.watchlistHit ? [200, 60, 50] : [40, 40, 40],
  });
  y += 10;

  // Movement timeline
  line("Chronological Camera-Sighting Timeline (ASC) — not GPS tracking", { size: 11, bold: true, gap: 18 });
  doc.setDrawColor(200);
  doc.line(margin, y - 8, pageW - margin, y - 8);

  (result.sightings || []).forEach((s, i) => {
    line(`${i + 1}.  ${s.cameraName}  (${s.cameraId})`, { size: 10, bold: true, gap: 14 });
    line(`     Time  : ${fmt(s.timestamp)}`, { size: 9, color: [90, 90, 90], gap: 13 });
    line(
      `     Coords: ${
        s.hasLocation && s.lat != null ? `${s.lat.toFixed(5)}, ${s.lng.toFixed(5)}` : "location unavailable"
      }` +
        (s.vehicleType ? `   Vehicle: ${s.vehicleType}` : "") +
        (Number.isFinite(s.ocrConfidence) ? `   Plate conf: ${(s.ocrConfidence * 100).toFixed(1)}%` : ""),
      { size: 9, color: [90, 90, 90], gap: 13 }
    );
    line(`     Event : ${s.eventId}`, { size: 8, color: [140, 140, 140], gap: 18 });
  });

  // Footer note on every page
  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p += 1) {
    doc.setPage(p);
    doc.setFontSize(8);
    doc.setTextColor(150);
    doc.text(
      `SENTINEL confidential · Page ${p} of ${pages} · ${formatPlate(plate)}`,
      margin,
      pageH - 24
    );
  }

  doc.save(`${plate}_Report.pdf`);
}

export function exportVehicleReportCSV(result) {
  if (!result) return;
  const plate = normalizePlate(result.plate);
  const rows = [
    ["seq", "camera_id", "camera_name", "timestamp", "vehicle_type", "latitude", "longitude", "plate_confidence", "event_id"],
    ...(result.sightings || []).map((s, i) => [
      i + 1,
      s.cameraId,
      `"${String(s.cameraName).replace(/"/g, '""')}"`,
      s.timestamp || "",
      s.vehicleType || "",
      s.hasLocation ? s.lat ?? "" : "",
      s.hasLocation ? s.lng ?? "" : "",
      Number.isFinite(s.ocrConfidence) ? s.ocrConfidence : "",
      s.eventId,
    ]),
  ];
  const csv = rows.map((r) => r.join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${plate}_Report.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ─── Generic CSV → PDF (Phase 13 §8) ────────────────────────────────────────
// Renders a downloaded report CSV as a simple paginated PDF table. Pure
// client-side (jsPDF, already a dependency). CSV remains the primary format.
function parseCsv(text) {
  const rows = [];
  let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cur += '"'; i += 1; }
      else if (c === '"') q = false;
      else cur += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cur); rows.push(row); row = []; cur = "";
    } else cur += c;
  }
  if (cur !== "" || row.length) { row.push(cur); rows.push(row); }
  return rows.filter((r) => r.some((c) => c !== ""));
}

export function exportCsvTextToPDF(title, csvText) {
  const rows = parseCsv(csvText);
  if (!rows.length) return;
  const doc = new jsPDF({ unit: "pt", format: "a4", orientation: "landscape" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const margin = 36;
  let y = margin;

  doc.setFillColor(18, 22, 28);
  doc.rect(0, 0, pageW, 54, "F");
  doc.setTextColor(230, 234, 238);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.text(`SENTINEL — ${title}`, margin, 26);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(150, 160, 175);
  doc.text(
    `Gujarat Police · generated ${new Date().toLocaleString("en-IN", { hour12: false })} · ${rows.length - 1} row(s)`,
    margin, 42,
  );
  y = 74;

  const header = rows[0];
  const cols = header.length;
  const colW = (pageW - margin * 2) / cols;

  const drawRow = (cells, bold) => {
    if (y > pageH - margin) { doc.addPage(); y = margin; }
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(bold ? 8 : 7.5);
    doc.setTextColor(bold ? 40 : 70, bold ? 40 : 70, bold ? 40 : 70);
    cells.forEach((c, i) => {
      const s = String(c ?? "");
      const clipped = s.length > 26 ? `${s.slice(0, 24)}…` : s;
      doc.text(clipped, margin + i * colW, y);
    });
    y += bold ? 15 : 12;
    if (bold) { doc.setDrawColor(200); doc.line(margin, y - 8, pageW - margin, y - 8); }
  };

  drawRow(header, true);
  rows.slice(1).forEach((r) => drawRow(r, false));

  const pages = doc.getNumberOfPages();
  for (let p = 1; p <= pages; p += 1) {
    doc.setPage(p);
    doc.setFontSize(7);
    doc.setTextColor(150);
    doc.text(`SENTINEL confidential · Page ${p} of ${pages}`, margin, pageH - 18);
  }
  doc.save(`${title.replace(/\s+/g, "_")}.pdf`);
}
