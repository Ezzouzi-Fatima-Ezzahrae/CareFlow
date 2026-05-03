// FHIR Bundle parser — converts a Synthea/PO-style FHIR R4 bundle into
// CareFlow's internal patient + events format.

// LOINC code → CareFlow metric mapping (the codes Synthea/PO actually emit).
const LOINC_TO_METRIC = {
  "8480-6":   { code: "systolic_bp",     unit: "mmHg",          type: "vital" },
  "8462-4":   { code: "diastolic_bp",    unit: "mmHg",          type: "vital" },
  "8867-4":   { code: "heart_rate",      unit: "bpm",           type: "vital" },
  "9279-1":   { code: "resp_rate",       unit: "/min",          type: "vital" },
  "59408-5":  { code: "spo2",            unit: "%",             type: "vital" },
  "2708-6":   { code: "spo2",            unit: "%",             type: "vital" },
  "8310-5":   { code: "temperature_c",   unit: "°C",            type: "vital" },
  "29463-7":  { code: "weight_kg",       unit: "kg",            type: "vital" },
  "39156-5":  { code: "bmi",             unit: "kg/m²",         type: "vital" },
  "8302-2":   { code: "height_cm",       unit: "cm",            type: "vital" },

  "4548-4":   { code: "HbA1c",           unit: "%",             type: "lab"   },
  "17856-6":  { code: "HbA1c",           unit: "%",             type: "lab"   },
  "2339-0":   { code: "glucose",         unit: "mg/dL",         type: "lab"   },
  "1558-6":   { code: "fasting_glucose", unit: "mg/dL",         type: "lab"   },
  "2093-3":   { code: "total_cholesterol", unit: "mg/dL",       type: "lab"   },
  "2089-1":   { code: "ldl",             unit: "mg/dL",         type: "lab"   },
  "18262-6":  { code: "ldl",             unit: "mg/dL",         type: "lab"   },
  "13457-7":  { code: "ldl",             unit: "mg/dL",         type: "lab"   },
  "2085-9":   { code: "hdl",             unit: "mg/dL",         type: "lab"   },
  "2571-8":   { code: "triglycerides",   unit: "mg/dL",         type: "lab"   },
  "2160-0":   { code: "creatinine",      unit: "mg/dL",         type: "lab"   },
  "38483-4":  { code: "creatinine",      unit: "mg/dL",         type: "lab"   },
  "33914-3":  { code: "egfr",            unit: "mL/min/1.73m²", type: "lab"   },
  "62238-1":  { code: "egfr",            unit: "mL/min/1.73m²", type: "lab"   },
  "6299-2":   { code: "bun",             unit: "mg/dL",         type: "lab"   },
  "718-7":    { code: "hemoglobin",      unit: "g/dL",          type: "lab"   },
  "2823-3":   { code: "potassium",       unit: "mmol/L",        type: "lab"   },
  "2951-2":   { code: "sodium",          unit: "mmol/L",        type: "lab"   },
  "30385-9":  { code: "bnp",             unit: "pg/mL",         type: "lab"   },
  "10839-9":  { code: "troponin",        unit: "ng/mL",         type: "lab"   },
  "49562-9":  { code: "troponin",        unit: "ng/mL",         type: "lab"   },
};

// Severity thresholds — same logic as the MCP server's deterministic extractor.
const THRESHOLDS = {
  systolic_bp:     { warn: 140, critical: 160 },
  diastolic_bp:    { warn: 90,  critical: 100 },
  heart_rate:      { warn: 100, critical: 130 },
  spo2:            { warn: 92,  critical: 88,  lowerIsWorse: true },
  HbA1c:           { warn: 7.0, critical: 9.0 },
  fasting_glucose: { warn: 125, critical: 200 },
  glucose:         { warn: 140, critical: 250 },
  ldl:             { warn: 130, critical: 190 },
  creatinine:      { warn: 1.3, critical: 2.0 },
  egfr:            { warn: 60,  critical: 30,  lowerIsWorse: true },
  bnp:             { warn: 100, critical: 400 },
  troponin:        { warn: 0.04, critical: 0.4 },
};

function severityFor(code, value) {
  const t = THRESHOLDS[code];
  if (!t) return "info";
  if (t.lowerIsWorse) {
    if (value <= t.critical) return "critical";
    if (value <= t.warn) return "warn";
    return "info";
  }
  if (value >= t.critical) return "critical";
  if (value >= t.warn) return "warn";
  return "info";
}

function getDate(fhirDate) {
  if (!fhirDate) return null;
  if (typeof fhirDate === "string") {
    return fhirDate.length >= 10 ? fhirDate.slice(0, 10) : fhirDate;
  }
  return null;
}

function fullName(patient) {
  const n = (patient.name && patient.name[0]) || {};
  const given = (n.given || []).join(" ");
  const family = n.family || "";
  return `${given} ${family}`.trim() || "Unknown patient";
}


/**
 * Parse a FHIR Bundle and return a CareFlow patient object.
 * Accepts either a parsed JSON object or a JSON string.
 */
export function parseFhirBundle(bundleOrString) {
  const bundle = typeof bundleOrString === "string"
    ? JSON.parse(bundleOrString)
    : bundleOrString;

  if (!bundle || !bundle.entry) {
    throw new Error("Not a valid FHIR Bundle (no 'entry' array).");
  }

  const resources = bundle.entry.map(e => e.resource).filter(Boolean);

  const patientResource = resources.find(r => r.resourceType === "Patient");
  if (!patientResource) {
    throw new Error("Bundle has no Patient resource.");
  }

  const observations = resources.filter(r => r.resourceType === "Observation");
  const conditions   = resources.filter(r => r.resourceType === "Condition");
  const meds         = resources.filter(r => r.resourceType === "MedicationStatement"
                                           || r.resourceType === "MedicationRequest");

  // Bucket observations by date (YYYY-MM-DD) → that becomes a "visit".
  const byDate = new Map();
  function addToDate(date, evt) {
    if (!date) return;
    if (!byDate.has(date)) byDate.set(date, []);
    byDate.get(date).push(evt);
  }

  for (const obs of observations) {
    const date = getDate(obs.effectiveDateTime || obs.issued || obs.effectivePeriod?.start);
    if (!obs.code || !obs.code.coding) continue;

    // Try every coding to find a LOINC we know
    let mapped = null;
    for (const coding of obs.code.coding) {
      const m = LOINC_TO_METRIC[coding.code];
      if (m) { mapped = m; break; }
    }
    if (!mapped) {
      // Skip observations we don't recognize. Could log them later.
      continue;
    }

    if (obs.valueQuantity && typeof obs.valueQuantity.value === "number") {
      const value = obs.valueQuantity.value;
      addToDate(date, {
        type: mapped.type,
        code: mapped.code,
        value,
        unit: mapped.unit,
        severity: severityFor(mapped.code, value),
      });
    } else if (obs.component && Array.isArray(obs.component)) {
      // Blood pressure panels often come as components: systolic + diastolic.
      for (const c of obs.component) {
        if (!c.code || !c.code.coding) continue;
        let cm = null;
        for (const coding of c.code.coding) {
          const m = LOINC_TO_METRIC[coding.code];
          if (m) { cm = m; break; }
        }
        if (cm && c.valueQuantity && typeof c.valueQuantity.value === "number") {
          const v = c.valueQuantity.value;
          addToDate(date, {
            type: cm.type,
            code: cm.code,
            value: v,
            unit: cm.unit,
            severity: severityFor(cm.code, v),
          });
        }
      }
    }
  }

  for (const cond of conditions) {
    const date = getDate(cond.recordedDate
                         || cond.onsetDateTime
                         || cond.assertedDate);
    const coding = cond.code?.coding?.[0];
    addToDate(date, {
      type: "diagnosis",
      code: coding?.code || null,
      label: cond.code?.text || coding?.display || "Unspecified diagnosis",
    });
  }

  for (const med of meds) {
    const date = getDate(med.effectivePeriod?.start
                         || med.dateAsserted
                         || med.authoredOn);
    const display = med.medicationCodeableConcept?.text
                    || med.medicationCodeableConcept?.coding?.[0]?.display
                    || med.medicationReference?.display
                    || "medication";
    const dose = med.dosage?.[0]?.text
              || med.dosageInstruction?.[0]?.text
              || "";
    addToDate(date, {
      type: "medication",
      code: display.toLowerCase().split(/\s+/)[0],
      label: dose ? `${display} — ${dose}` : display,
    });
  }

  // Convert the date-buckets into a sorted list of visits.
  const visits = Array.from(byDate.entries())
    .map(([date, events]) => ({ date, label: `Visit ${date}`, events }))
    .sort((a, b) => a.date.localeCompare(b.date));

  // If we have no dates at all, fall back to a single "imported" visit.
  if (visits.length === 0 && (observations.length || conditions.length || meds.length)) {
    visits.push({ date: "Unknown date", label: "Imported records", events: [] });
  }

  return {
    id: patientResource.id || `fhir-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: fullName(patientResource),
    dob: patientResource.birthDate || null,
    gender: patientResource.gender ? patientResource.gender[0].toUpperCase() : null,
    mrn: patientResource.identifier?.[0]?.value || null,
    visits,
    _stats: {
      observations: observations.length,
      conditions: conditions.length,
      medications: meds.length,
      visits: visits.length,
    },
  };
}


/** Read a File (from <input type="file">) and parse it as a FHIR bundle. */
export function readFhirFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(parseFhirBundle(reader.result));
      } catch (e) {
        reject(e);
      }
    };
    reader.onerror = () => reject(new Error("File read error"));
    reader.readAsText(file);
  });
}
