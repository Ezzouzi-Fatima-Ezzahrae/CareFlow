import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity, AlertTriangle, ChevronRight, Cloud, CloudOff, FlaskConical,
  Heart, Pill, ShieldAlert, Stethoscope, TrendingDown, TrendingUp,
  Trash2, Upload, User, Users, Zap,
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  PieChart, Pie, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import {
  SEVERITY_COLORS, SEVERITY_LABEL,
  loadPatients, addPatient, removePatient,
  flattenEvents, computeRisk, buildTrends, latestPerCode,
} from "./data.js";
import { readFhirFile } from "./fhir.js";
import {
  fetchMcpPatients, pingMcp, deleteMcpPatient, mcpRecordToPatient,
  getRequestedPatient,
} from "./mcpClient.js";


/* ------------------------------------------------------------------------ */
/* Small reusable bits                                                      */
/* ------------------------------------------------------------------------ */

function SeverityDot({ severity = "info", className = "" }) {
  const color = SEVERITY_COLORS[severity] || "#64748B";
  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${className}`}
          style={{ backgroundColor: color }} />
  );
}

function Card({ title, icon, children, className = "" }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 p-5 ${className}`}>
      {title && (
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h2 className="font-semibold text-slate-800">{title}</h2>
        </div>
      )}
      {children}
    </div>
  );
}

function RiskBadge({ risk }) {
  const colors = {
    high:     "bg-red-100 text-red-800",
    moderate: "bg-amber-100 text-amber-800",
    low:      "bg-emerald-100 text-emerald-800",
  };
  return (
    <span className={`px-3 py-1.5 rounded-full text-sm font-semibold ${colors[risk.level]}`}>
      {risk.label} risk
    </span>
  );
}


/* ------------------------------------------------------------------------ */
/* Empty state — when no patients are imported yet                          */
/* ------------------------------------------------------------------------ */

function EmptyState({ onPickFiles, mcpStatus }) {
  return (
    <div className="flex-1 flex items-center justify-center p-10">
      <div className="max-w-2xl text-center">
        <div className="w-16 h-16 rounded-2xl bg-teal-50 mx-auto flex items-center justify-center">
          <Zap className="w-7 h-7 text-teal-700" />
        </div>
        <h2 className="text-2xl font-bold text-slate-900 mt-5">Waiting for a patient from Prompt Opinion</h2>
        <p className="text-slate-600 mt-2">
          Open the <strong>CareFlow Clinical Assistant</strong> in PO's Launchpad,
          select a patient (e.g. Tamera164 Wisozk929), and start a chat.
          The agent will register the patient with this dashboard automatically —
          they'll appear in the sidebar within a few seconds.
        </p>

        <div className={`mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm ${
          mcpStatus?.connected
            ? "bg-emerald-50 text-emerald-800"
            : "bg-amber-50 text-amber-800"
        }`}>
          {mcpStatus?.connected
            ? <><Cloud className="w-4 h-4" /> Connected to MCP — listening for PO patients</>
            : <><CloudOff className="w-4 h-4" /> Cannot reach the MCP server (is it running on localhost:8000?)</>}
        </div>

        <div className="mt-8 pt-8 border-t border-slate-200">
          <p className="text-sm text-slate-500">
            Or, if you have a FHIR JSON file, you can import one manually:
          </p>
          <button
            onClick={onPickFiles}
            className="mt-3 inline-flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 px-4 py-2 rounded-lg text-sm font-semibold">
            <Upload className="w-4 h-4" /> Import FHIR file
          </button>
        </div>

        <p className="text-xs text-slate-400 mt-6">
          Synthetic data only. Not a medical device.
        </p>
      </div>
    </div>
  );
}


/* ------------------------------------------------------------------------ */
/* Sidebar                                                                  */
/* ------------------------------------------------------------------------ */

function Sidebar({ patients, activeId, onSelect, onPickFiles, onRemove, mcpStatus }) {
  return (
    <aside className="w-72 bg-white border-r border-slate-200 flex flex-col">
      <div className="px-5 py-5 border-b border-slate-200 flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-teal-700 flex items-center justify-center text-white font-bold text-lg">
          C
        </div>
        <div>
          <div className="font-bold text-slate-800 text-lg">CareFlow</div>
          <div className="text-xs text-slate-500">Clinical dashboard</div>
        </div>
      </div>

      <div className={`px-4 py-2 border-b text-xs flex items-center gap-2 ${
        mcpStatus?.connected
          ? "bg-emerald-50 border-emerald-100 text-emerald-800"
          : "bg-amber-50 border-amber-100 text-amber-800"
      }`}>
        {mcpStatus?.connected ? (
          <>
            <Cloud className="w-3.5 h-3.5" />
            <span>Live link to PO via MCP — {mcpStatus.count ?? 0} from PO</span>
          </>
        ) : (
          <>
            <CloudOff className="w-3.5 h-3.5" />
            <span>Offline — start the MCP server to sync</span>
          </>
        )}
      </div>

      <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs uppercase text-slate-500 font-semibold tracking-wide">
          <Users className="w-3.5 h-3.5" />
          Patients ({patients.length})
        </div>
        <button onClick={onPickFiles}
                className="text-xs bg-teal-600 hover:bg-teal-700 text-white px-2.5 py-1.5 rounded-md font-semibold flex items-center gap-1">
          <Upload className="w-3 h-3" /> Import
        </button>
      </div>

      <ul className="flex-1 overflow-y-auto p-2 space-y-1">
        {patients.length === 0 ? (
          <li className="text-xs text-slate-400 text-center py-6 px-2">
            No patients yet.<br />Import a FHIR bundle to begin.
          </li>
        ) : patients.map(p => {
          const events = flattenEvents(p);
          const risk = computeRisk(events);
          const isActive = p.id === activeId;
          return (
            <li key={p.id} className="group relative">
              <button
                onClick={() => onSelect(p.id)}
                className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-left transition-colors ${
                  isActive ? "bg-teal-50 text-teal-900" : "hover:bg-slate-50"
                }`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
                    isActive ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-600"
                  }`}>
                    <User className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className={`text-sm font-medium truncate ${isActive ? "text-teal-900" : "text-slate-800"}`}>
                      {p.name}
                      {p._source === "po-mcp-bridge" && (
                        <Zap className="inline w-3 h-3 ml-1 text-teal-600" title="Live from PO" />
                      )}
                    </div>
                    <div className="text-xs text-slate-500 truncate">
                      {p.gender || "?"} · {p.dob || "—"}
                    </div>
                  </div>
                </div>
                <SeverityDot severity={
                  risk.level === "high" ? "critical" :
                  risk.level === "moderate" ? "warn" : "info"
                } />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onRemove(p.id); }}
                className="absolute right-1 top-1 hidden group-hover:flex items-center justify-center w-7 h-7 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                title="Remove patient">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </li>
          );
        })}
      </ul>

      <div className="px-5 py-4 border-t border-slate-200 text-xs text-slate-500">
        Synthetic data only.<br />Not a medical device.
      </div>
    </aside>
  );
}


/* ------------------------------------------------------------------------ */
/* Patient header                                                           */
/* ------------------------------------------------------------------------ */

function PatientHeader({ patient, risk }) {
  return (
    <div className="bg-white border-b border-slate-200 px-8 py-5 flex items-center justify-between">
      <div>
        <div className="text-xs uppercase tracking-wide text-teal-700 font-semibold">Active patient</div>
        <h1 className="text-2xl font-bold text-slate-900 mt-0.5">{patient.name}</h1>
        <div className="text-sm text-slate-500 mt-1">
          {patient.gender || "?"} · {patient.dob || "—"}
          {patient.mrn ? <> · MRN {patient.mrn}</> : null}
          {" · "}{patient.visits?.length || 0} visits
        </div>
      </div>
      <div className="flex items-center gap-3">
        {risk.level !== "low" && (
          <span className="flex items-center gap-1.5 text-sm text-slate-600">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            {risk.critical} critical · {risk.warning} warnings
          </span>
        )}
        <RiskBadge risk={risk} />
      </div>
    </div>
  );
}


/* ------------------------------------------------------------------------ */
/* Risk overview                                                            */
/* ------------------------------------------------------------------------ */

function RiskOverview({ risk }) {
  const data = [
    { name: "Critical", value: risk.critical,                                          key: "critical" },
    { name: "Warning",  value: risk.warning,                                           key: "warn"     },
    { name: "Normal",   value: Math.max(0, risk.total - risk.critical - risk.warning), key: "info"     },
  ].filter(d => d.value > 0);

  return (
    <Card title="Overall risk" icon={<ShieldAlert className="w-4 h-4 text-teal-700" />}>
      <div className="flex items-center gap-4">
        <div className="relative w-40 h-40">
          <ResponsiveContainer>
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name"
                   innerRadius={48} outerRadius={68} startAngle={90} endAngle={-270}
                   stroke="white" strokeWidth={2}>
                {data.map(d => <Cell key={d.key} fill={SEVERITY_COLORS[d.key]} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <div className="text-2xl font-bold" style={{
              color: SEVERITY_COLORS[
                risk.level === "high" ? "critical" :
                risk.level === "moderate" ? "warn" : "info"
              ]
            }}>
              {risk.label}
            </div>
            <div className="text-xs text-slate-500">{risk.total} events</div>
          </div>
        </div>
        <div className="flex-1 space-y-2">
          {data.length ? data.map(d => (
            <div key={d.key} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded" style={{ backgroundColor: SEVERITY_COLORS[d.key] }} />
                <span className="text-slate-700">{d.name}</span>
              </div>
              <span className="text-slate-900 font-semibold">{d.value}</span>
            </div>
          )) : (
            <p className="text-sm text-slate-500">No measured events yet.</p>
          )}
        </div>
      </div>
    </Card>
  );
}


/* ------------------------------------------------------------------------ */
/* Latest metrics — color-coded bar chart                                   */
/* ------------------------------------------------------------------------ */

function MetricsDashboard({ events }) {
  const latest = latestPerCode(events);
  if (!latest.length) {
    return (
      <Card title="Latest measurements" icon={<Activity className="w-4 h-4 text-teal-700" />}>
        <p className="text-sm text-slate-500 py-4">No numeric measurements available for this patient.</p>
      </Card>
    );
  }

  const order = { critical: 0, warn: 1, info: 2 };
  latest.sort((a, b) => (order[a.severity] - order[b.severity]) || a.code.localeCompare(b.code));

  return (
    <Card title="Latest measurements" icon={<Activity className="w-4 h-4 text-teal-700" />}>
      <div style={{ width: "100%", height: Math.max(180, latest.length * 36) }}>
        <ResponsiveContainer>
          <BarChart data={latest} layout="vertical" margin={{ top: 5, right: 60, left: 8, bottom: 5 }}>
            <CartesianGrid horizontal={false} stroke="#E2E8F0" />
            <XAxis type="number" stroke="#64748B" fontSize={11} />
            <YAxis type="category" dataKey="code" stroke="#0F172A" fontSize={12} width={130} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 12 }}
              formatter={(v, _n, p) => [`${v} ${p?.payload?.unit ?? ""}`, p?.payload?.code]}
              labelFormatter={() => ""}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {latest.map((e, i) => (
                <Cell key={i} fill={SEVERITY_COLORS[e.severity] || "#94A3B8"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 mt-3 text-xs text-slate-600">
        {Object.entries(SEVERITY_LABEL).map(([k, label]) => (
          <div key={k} className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: SEVERITY_COLORS[k] }} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}


/* ------------------------------------------------------------------------ */
/* Trend lines per metric                                                   */
/* ------------------------------------------------------------------------ */

function TrendCharts({ events }) {
  const trends = buildTrends(events);
  const codes = Object.keys(trends);
  if (!codes.length) {
    return (
      <Card title="Trends over time" icon={<TrendingUp className="w-4 h-4 text-teal-700" />}>
        <div className="text-sm text-slate-500 py-6 text-center">
          Need at least 2 visits with the same metric to plot a trend.
        </div>
      </Card>
    );
  }

  return (
    <Card title="Trends over time" icon={<TrendingUp className="w-4 h-4 text-teal-700" />}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {codes.map(code => {
          const series = trends[code];
          const first = series[0].value;
          const last  = series[series.length - 1].value;
          const delta = last - first;
          const trendColor = SEVERITY_COLORS[series[series.length - 1].severity];
          const TrendIcon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Activity;

          return (
            <div key={code} className="border border-slate-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-semibold text-slate-800">{code}</div>
                <div className="flex items-center gap-1.5 text-xs" style={{ color: trendColor }}>
                  <TrendIcon className="w-3.5 h-3.5" />
                  <span className="font-semibold">
                    {first} → {last} {series[0].unit || ""}
                  </span>
                </div>
              </div>
              <div style={{ width: "100%", height: 130 }}>
                <ResponsiveContainer>
                  <LineChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={d => (d || "").slice(2, 7)} stroke="#94A3B8" fontSize={10} />
                    <YAxis stroke="#94A3B8" fontSize={10} domain={["auto", "auto"]} />
                    <Tooltip
                      contentStyle={{ borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 12 }}
                      formatter={(v, _n, p) => [`${v} ${p?.payload?.unit ?? ""}`, code]}
                    />
                    <Line type="monotone" dataKey="value" stroke="#0F766E" strokeWidth={2.5}
                          dot={(props) => {
                            const { cx, cy, payload } = props;
                            return (
                              <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={5}
                                      fill={SEVERITY_COLORS[payload.severity] || "#0F766E"}
                                      stroke="white" strokeWidth={2} />
                            );
                          }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}


/* ------------------------------------------------------------------------ */
/* Doctor summary (deterministic — same logic as the MCP server)            */
/* ------------------------------------------------------------------------ */

function buildSummary(events, risk) {
  const diagnoses = events.filter(e => e.type === "diagnosis");
  const meds      = events.filter(e => e.type === "medication");
  const notes     = events.filter(e => e.type === "note" && (e.severity === "warn" || e.severity === "critical"));

  const trends = buildTrends(events);
  const trendLines = Object.entries(trends).map(([code, arr]) => {
    const first = arr[0].value, last = arr[arr.length - 1].value;
    const delta = last - first;
    const arrow = delta > 0 ? "↑" : delta < 0 ? "↓" : "·";
    return `**${code}**: ${first} → ${last} ${arr[0].unit || ""} (${arrow} ${Math.abs(delta).toFixed(2)})`;
  });

  const followUps = [];
  const crit = events.filter(e => e.severity === "critical");
  const warn = events.filter(e => e.severity === "warn");
  if (crit.length) {
    followUps.push(`Address critical-flagged findings (${[...new Set(crit.map(e => e.code).filter(Boolean))].join(", ")}).`);
  } else if (warn.length) {
    followUps.push(`Monitor warning-flagged values (${[...new Set(warn.map(e => e.code).filter(Boolean))].join(", ")}).`);
  }
  if (risk.level === "high") followUps.push("Consider specialist referral given high-risk delta.");
  if (meds.length) followUps.push(`Confirm adherence to recent regimen (${meds.slice(-3).map(m => m.label || m.code).join(", ")}).`);
  if (!followUps.length) followUps.push("Routine follow-up unless symptoms change.");

  const seenDx = new Set();
  const activeIssues = [];
  for (const d of diagnoses) {
    const key = (d.label || d.code || "").toLowerCase();
    if (!key || seenDx.has(key)) continue;
    seenDx.add(key);
    activeIssues.push(d.label || d.code);
  }
  for (const n of notes) activeIssues.push(n.label);

  return {
    activeIssues,
    trends: trendLines,
    medications: meds.slice(-3).map(m => m.label || m.code),
    followUps,
  };
}

function DoctorSummary({ summary }) {
  return (
    <Card title="Doctor summary" icon={<Stethoscope className="w-4 h-4 text-teal-700" />}>
      <div className="markdown text-sm text-slate-700">
        <h3>Active issues</h3>
        <ul>
          {summary.activeIssues.length
            ? summary.activeIssues.map((x, i) => <li key={i}>{x}</li>)
            : <li><em>No active diagnoses on record.</em></li>}
        </ul>

        <h3>Trends</h3>
        <ul>
          {summary.trends.length
            ? summary.trends.map((x, i) => (
                <li key={i} dangerouslySetInnerHTML={{
                  __html: x.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                }} />
              ))
            : <li><em>Insufficient data for numeric trends.</em></li>}
        </ul>

        <h3>Recent medications</h3>
        <ul>
          {summary.medications.length
            ? summary.medications.map((x, i) => <li key={i}>{x}</li>)
            : <li><em>No medications recorded.</em></li>}
        </ul>

        <h3>Suggested follow-ups</h3>
        <ul>
          {summary.followUps.map((x, i) => <li key={i}>{x}</li>)}
        </ul>

        <p className="text-xs text-slate-400 mt-3">
          <em>Generated locally by CareFlow — facts pulled directly from the FHIR bundle. No LLM extraction.</em>
        </p>
      </div>
    </Card>
  );
}


/* ------------------------------------------------------------------------ */
/* Timeline                                                                 */
/* ------------------------------------------------------------------------ */

function Timeline({ patient }) {
  return (
    <Card title="Visit timeline" icon={<ChevronRight className="w-4 h-4 text-teal-700" />}>
      <ol className="relative border-l-2 border-teal-200 pl-5 space-y-5 max-h-[520px] overflow-y-auto pr-2">
        {patient.visits.map((visit, vi) => (
          <li key={vi} className="relative">
            <span className="absolute -left-[1.65rem] top-1.5 w-3.5 h-3.5 rounded-full bg-teal-600 ring-2 ring-white" />
            <div className="text-xs text-slate-500">{visit.date}</div>
            <div className="text-sm font-semibold text-slate-800">{visit.label}</div>
            <ul className="mt-2 space-y-1.5">
              {visit.events.map((e, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <SeverityDot severity={e.severity || "info"} className="mt-1.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <span className="text-slate-500 mr-1">
                      {e.type === "vital" && <Heart className="inline w-3 h-3 mr-0.5 -mt-0.5 text-rose-500" />}
                      {e.type === "lab" && <FlaskConical className="inline w-3 h-3 mr-0.5 -mt-0.5 text-violet-500" />}
                      {e.type === "medication" && <Pill className="inline w-3 h-3 mr-0.5 -mt-0.5 text-emerald-600" />}
                      {e.type}
                    </span>
                    <span className="font-medium text-slate-800">{e.code || ""}</span>
                    {typeof e.value === "number" && (
                      <span className="ml-1 px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-xs">
                        {e.value} {e.unit}
                      </span>
                    )}
                    {e.label && <span className="ml-1 text-slate-600">{e.label}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </Card>
  );
}


/* ------------------------------------------------------------------------ */
/* App shell                                                                */
/* ------------------------------------------------------------------------ */

const POLL_INTERVAL_MS = 5000;

export default function App() {
  // Manually-imported (FHIR file upload) — persisted in localStorage
  const [importedPatients, setImportedPatients] = useState(() => loadPatients());
  // Live from PO via the MCP bridge — polled every 5s
  const [mcpPatients, setMcpPatients] = useState([]);
  const [mcpStatus, setMcpStatus] = useState({ connected: false, lastError: null });

  const [activeId, setActiveId] = useState(null);
  const [importStatus, setImportStatus] = useState(null);
  const fileInputRef = useRef(null);

  // Combined list: live MCP patients first (most recently registered),
  // then manually-imported ones.
  const patients = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const p of mcpPatients) {
      out.push(p);
      seen.add(p.name?.toLowerCase());
    }
    for (const p of importedPatients) {
      // De-dupe by name to avoid showing the same patient twice
      if (!seen.has(p.name?.toLowerCase())) {
        out.push(p);
      }
    }
    return out;
  }, [mcpPatients, importedPatients]);

  // ---- Poll the MCP server for patients PO has registered ----
  useEffect(() => {
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      const res = await fetchMcpPatients();
      if (cancelled) return;
      if (res.ok) {
        setMcpStatus({ connected: true, lastError: null, count: res.patients.length });
        setMcpPatients(res.patients.map(mcpRecordToPatient));
      } else {
        setMcpStatus({ connected: false, lastError: res.error });
      }
    };

    tick(); // immediately
    timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => { cancelled = true; if (timer) clearInterval(timer); };
  }, []);

  // Auto-select patient: respect ?patient=NAME_OR_ID URL param, else first.
  useEffect(() => {
    if (!patients.length) {
      setActiveId(null);
      return;
    }
    const requested = getRequestedPatient();
    if (requested) {
      const norm = requested.toLowerCase();
      const match = patients.find(p =>
        (p.id || "").toLowerCase().includes(norm) ||
        (p.name || "").toLowerCase().includes(norm) ||
        (p._po_name || "").toLowerCase().includes(norm)
      );
      if (match) {
        setActiveId(match.id);
        return;
      }
    }
    if (!patients.find(p => p.id === activeId)) {
      setActiveId(patients[0].id);
    }
  }, [patients, activeId]);

  const patient = patients.find(p => p.id === activeId);
  const events = useMemo(() => patient ? flattenEvents(patient) : [], [patient]);
  const risk = useMemo(() => computeRisk(events), [events]);
  const summary = useMemo(() => buildSummary(events, risk), [events, risk]);

  const handlePickFiles = () => fileInputRef.current?.click();

  const handleFiles = async (fileList) => {
    if (!fileList || fileList.length === 0) return;
    const results = [];
    let updated = importedPatients;
    for (const file of Array.from(fileList)) {
      try {
        const p = await readFhirFile(file);
        updated = addPatient(updated, p);
        results.push(`✓ ${p.name} (${p._stats.observations} obs, ${p._stats.conditions} cond, ${p._stats.medications} meds)`);
      } catch (e) {
        results.push(`✗ ${file.name}: ${e.message || "parse failed"}`);
      }
    }
    setImportedPatients(updated);
    setImportStatus(results.join(" · "));
    setTimeout(() => setImportStatus(null), 6000);
  };

  const handleRemove = (id) => {
    if (!window.confirm("Remove this patient from the dashboard?")) return;
    const target = patients.find(p => p.id === id);
    // If it's an MCP-bridged patient, also delete on the server
    if (target?._source === "po-mcp-bridge" && target.id?.startsWith("mcp-")) {
      const serverId = target.id.replace(/^mcp-/, "");
      deleteMcpPatient(serverId);
    }
    setImportedPatients(prev => removePatient(prev, id));
  };

  return (
    <div className="h-screen flex bg-slate-50">
      <input ref={fileInputRef} type="file" accept=".json,application/json" multiple
             className="hidden" onChange={(e) => handleFiles(e.target.files)} />

      <Sidebar
        patients={patients}
        activeId={activeId}
        onSelect={setActiveId}
        onPickFiles={handlePickFiles}
        onRemove={handleRemove}
        mcpStatus={mcpStatus}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        {importStatus && (
          <div className="px-8 py-2.5 bg-teal-50 border-b border-teal-200 text-sm text-teal-900">
            {importStatus}
          </div>
        )}

        {!patient ? (
          <EmptyState onPickFiles={handlePickFiles} mcpStatus={mcpStatus} />
        ) : (
          <>
            <PatientHeader patient={patient} risk={risk} />
            <div className="flex-1 overflow-y-auto p-8 space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <RiskOverview risk={risk} />
                <div className="lg:col-span-2">
                  <MetricsDashboard events={events} />
                </div>
              </div>
              <TrendCharts events={events} />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <DoctorSummary summary={summary} />
                <Timeline patient={patient} />
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
