// Patient store — backed by localStorage so imported FHIR bundles persist.

const LS_KEY = "careflow_patients_v1";

export const SEVERITY_COLORS = {
  info:     "#10B981",
  warn:     "#F59E0B",
  critical: "#DC2626",
};

export const SEVERITY_LABEL = {
  info:     "Normal",
  warn:     "Warning",
  critical: "Critical",
};


export function loadPatients() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function savePatients(patients) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(patients));
  } catch {
    /* quota or privacy mode — ignore */
  }
}

export function addPatient(patients, patient) {
  // Replace if same id, otherwise prepend.
  const i = patients.findIndex(p => p.id === patient.id);
  const next = [...patients];
  if (i >= 0) next[i] = patient; else next.unshift(patient);
  savePatients(next);
  return next;
}

export function removePatient(patients, id) {
  const next = patients.filter(p => p.id !== id);
  savePatients(next);
  return next;
}


/* ---------------------- Aggregation helpers ---------------------- */

export function flattenEvents(patient) {
  const out = [];
  if (!patient || !patient.visits) return out;
  for (const visit of patient.visits) {
    for (const e of visit.events) {
      out.push({ ...e, date: visit.date, visitLabel: visit.label });
    }
  }
  return out;
}

export function computeRisk(events) {
  const crit = events.filter(e => e.severity === "critical").length;
  const warn = events.filter(e => e.severity === "warn").length;
  const total = events.length;
  if (crit) return { level: "high",     label: "HIGH",     critical: crit, warning: warn, total };
  if (warn) return { level: "moderate", label: "MODERATE", critical: 0,    warning: warn, total };
  return { level: "low", label: "LOW", critical: 0, warning: 0, total };
}

export function buildTrends(events) {
  const series = {};
  for (const e of events) {
    if (typeof e.value === "number" && e.code) {
      if (!series[e.code]) series[e.code] = [];
      series[e.code].push({ date: e.date, value: e.value, severity: e.severity, unit: e.unit });
    }
  }
  const out = {};
  for (const [code, arr] of Object.entries(series)) {
    arr.sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    if (arr.length >= 2) out[code] = arr;
  }
  return out;
}

export function latestPerCode(events) {
  const map = {};
  for (const e of events) {
    if (typeof e.value !== "number" || !e.code) continue;
    if (!map[e.code] || (e.date && e.date > (map[e.code].date || ""))) {
      map[e.code] = { ...e };
    }
  }
  return Object.values(map);
}
