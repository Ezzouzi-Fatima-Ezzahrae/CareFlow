// Vercel serverless proxy: forwards /api/* to the CareFlow MCP server (via ngrok).
// Solves two issues at once:
//   1. ngrok-free's browser interstitial — server-to-server fetch isn't seen as a browser.
//   2. CORS — the dashboard fetches its own origin, no preflight needed.
//
// Configure the upstream MCP URL via the Vercel env var MCP_UPSTREAM
// (defaults to the project's known ngrok endpoint).

const DEFAULT_UPSTREAM = "https://catfish-uncoated-heavily.ngrok-free.dev";

export default async function handler(req, res) {
  const upstream = (process.env.MCP_UPSTREAM || DEFAULT_UPSTREAM).replace(/\/$/, "");

  const segments = req.query.path;
  const pathStr = Array.isArray(segments) ? segments.join("/") : (segments || "");
  const url = `${upstream}/api/${pathStr}`;

  try {
    const fetchInit = {
      method: req.method,
      headers: {
        "Accept": "application/json",
        // The ngrok-skip-browser-warning header DOES work server-side.
        "ngrok-skip-browser-warning": "true",
        // A non-browser UA also bypasses the interstitial.
        "User-Agent": "CareFlow-Vercel-Proxy/1.0",
      },
    };

    if (req.method !== "GET" && req.method !== "HEAD" && req.body) {
      fetchInit.body = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
      fetchInit.headers["Content-Type"] = "application/json";
    }

    const upstreamRes = await fetch(url, fetchInit);
    const text = await upstreamRes.text();

    res.status(upstreamRes.status);
    res.setHeader("Content-Type", upstreamRes.headers.get("content-type") || "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Cache-Control", "no-store");
    res.send(text);
  } catch (e) {
    res.status(502).json({
      error: "proxy_failed",
      message: e.message,
      upstream: url,
    });
  }
}
