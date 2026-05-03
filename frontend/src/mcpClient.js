// CareFlow MCP server REST client.
//
// The MCP server exposes a small REST API alongside its MCP protocol so the
// dashboard can pull patient data the agent has captured from PO.

const DEFAULT_MCP_URL = "http://localhost:8000";
const LS_URL_KEY = "careflow_mcp_url_v1";

/** Resolve the MCP base URL.
 *
 * Order of preference:
 *   1. If running on a Vercel deployment, use the same-origin "" base so all
 *      fetches go through /api/[...path].js (the serverless proxy that
 *      avoids ngrok's browser interstitial).
 *   2. ?mcp= URL param (user override).
 *   3. localStorage cached value.
 *   4. Default localhost:8000.
 */
export function getMcpUrl() {
  try {
    const host = window.location.host || "";
    const isVercel = host.endsWith(".vercel.app");

    // URL param explicitly overrides everything (good for local testing
    // against an arbitrary MCP server even from a Vercel-deployed page).
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("mcp");
    if (fromUrl) {
      try { localStorage.setItem(LS_URL_KEY, fromUrl.replace(/\/$/, "")); } catch {}
      return fromUrl.replace(/\/$/, "");
    }

    if (isVercel) return ""; // empty means same-origin → /api/* hits the proxy

    return localStorage.getItem(LS_URL_KEY) || DEFAULT_MCP_URL;
  } catch {
    return DEFAULT_MCP_URL;
  }
}

/** Read the optional ?patient= param so the agent can deep-link to a patient. */
export function getRequestedPatient() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get("patient") || null;
  } catch {
    return null;
  }
}

export function setMcpUrl(url) {
  try {
    localStorage.setItem(LS_URL_KEY, (url || "").replace(/\/$/, ""));
  } catch {
    /* ignore */
  }
}


// ngrok-free shows a browser interstitial unless we either:
//   (a) include a non-browser header so the response isn't HTML, OR
//   (b) make a "simple" CORS request that avoids preflight entirely.
//
// The header approach requires `ngrok-skip-browser-warning` AND triggers a
// CORS preflight (OPTIONS) — which ngrok sometimes also blocks. To minimise
// preflights, we use ONLY safelisted headers (Accept) and rely on ngrok
// passing through JSON requests automatically when paired with the bypass
// query string `?ngrok-skip-browser-warning=true`. We send both for safety.
const COMMON_HEADERS = {
  "Accept": "application/json",
  "ngrok-skip-browser-warning": "true",
};

function appendBypass(url) {
  const sep = url.includes("?") ? "&" : "?";
  return url + sep + "ngrok-skip-browser-warning=true";
}


export async function pingMcp() {
  try {
    const res = await fetch(appendBypass(`${getMcpUrl()}/api/health`), {
      method: "GET",
      headers: COMMON_HEADERS,
    });
    if (!res.ok) return { ok: false, status: res.status };
    return await res.json();
  } catch (e) {
    return { ok: false, error: e.message };
  }
}


export async function fetchMcpPatients() {
  try {
    const res = await fetch(appendBypass(`${getMcpUrl()}/api/patients`), {
      method: "GET",
      headers: COMMON_HEADERS,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { ok: true, patients: data.patients || [] };
  } catch (e) {
    return { ok: false, error: e.message, patients: [] };
  }
}


export async function deleteMcpPatient(id) {
  try {
    await fetch(appendBypass(`${getMcpUrl()}/api/patients/${encodeURIComponent(id)}`), {
      method: "DELETE",
      headers: COMMON_HEADERS,
    });
    return true;
  } catch {
    return false;
  }
}


export async function clearMcpCache() {
  try {
    await fetch(appendBypass(`${getMcpUrl()}/api/clear`), {
      method: "POST",
      headers: COMMON_HEADERS,
    });
    return true;
  } catch {
    return false;
  }
}


// ----------------- Convert MCP cached records → dashboard patient ----------

import { parseFhirBundle } from "./fhir.js";

/**
 * MCP-cached records may contain a FHIR bundle, derived events from regex
 * extraction, or just a name. Normalize all three into the dashboard's
 * patient shape (the same shape the FHIR import produces).
 */
export function mcpRecordToPatient(rec) {
  const baseId = `mcp-${rec.id || Date.now()}`;
  // Case 1 — we have a full FHIR Bundle. Use the same parser as manual import.
  if (rec.fhir && typeof rec.fhir === "object") {
    try {
      const p = parseFhirBundle(rec.fhir);
      return {
        ...p,
        id: baseId,
        _source: "po-mcp-bridge",
        _registered_at: rec.registered_at || null,
        _po_name: rec.name,
      };
    } catch (e) {
      console.warn("FHIR parse failed for MCP patient", rec.id, e.message);
    }
  }

  // Case 2 — derived events from a free-text summary. Wrap in a single visit.
  if (Array.isArray(rec.derived_events) && rec.derived_events.length) {
    const visits = bucketByDate(rec.derived_events);
    return {
      id: baseId,
      name: rec.name || "Unknown patient",
      dob: rec.dob || null,
      gender: rec.gender || null,
      mrn: null,
      visits,
      _stats: { observations: rec.derived_events.length, conditions: 0, medications: 0 },
      _source: "po-mcp-bridge",
      _registered_at: rec.registered_at || null,
      _po_name: rec.name,
    };
  }

  // Case 3 — name only.
  return {
    id: baseId,
    name: rec.name || "Unknown patient",
    dob: rec.dob || null,
    gender: rec.gender || null,
    mrn: null,
    visits: [],
    _stats: { observations: 0, conditions: 0, medications: 0 },
    _source: "po-mcp-bridge",
    _registered_at: rec.registered_at || null,
    _po_name: rec.name,
  };
}


function bucketByDate(events) {
  const map = new Map();
  for (const e of events) {
    const date = e.recorded_at?.slice(0, 10) || "Unknown date";
    if (!map.has(date)) map.set(date, []);
    map.get(date).push({
      type: e.event_type,
      code: e.code,
      value: e.value_num != null ? e.value_num : undefined,
      unit: e.unit,
      severity: e.severity,
      label: e.value_text,
    });
  }
  return Array.from(map.entries())
    .map(([date, events]) => ({ date, label: `Visit ${date}`, events }))
    .sort((a, b) => a.date.localeCompare(b.date));
}
