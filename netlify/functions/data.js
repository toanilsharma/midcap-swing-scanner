// Netlify Serverless Function: GitHub Raw Proxy for Private Repo
// Provides secure, server-side authenticated proxy to repo files
// without exposing GitHub PAT or repository data to anonymous clients.

exports.handler = async function (event, context) {
  const responseHeaders = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "x-dash-key, Content-Type",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
  };

  // Handle CORS preflight
  if (event.httpMethod === "OPTIONS") {
    return {
      statusCode: 204,
      headers: responseHeaders,
      body: "",
    };
  }

  // 1. Authenticate Request via x-dash-key header
  const reqHeaders = event.headers || {};
  let clientKey = "";
  for (const k of Object.keys(reqHeaders)) {
    if (k.toLowerCase() === "x-dash-key") {
      clientKey = reqHeaders[k];
      break;
    }
  }

  const expectedKey = process.env.DASH_KEY_HASH;
  if (!expectedKey || clientKey !== expectedKey) {
    return {
      statusCode: 401,
      headers: responseHeaders,
      body: JSON.stringify({ error: "unauthorized" }),
    };
  }

  // 2. Validate Query Parameter "file" & Enforce Strict Allowlist
  const params = event.queryStringParameters || {};
  const file = params.file;

  if (!file || typeof file !== "string" || file.includes("..")) {
    return {
      statusCode: 400,
      headers: responseHeaders,
      body: JSON.stringify({ error: "invalid file parameter" }),
    };
  }

  const exactAllowlist = ["scan_results.json", "trades.json", "open_positions.json"];
  const archivePattern = /^archive\/[A-Za-z0-9_.-]+$/;

  const isAllowed = exactAllowlist.includes(file) || archivePattern.test(file);
  if (!isAllowed) {
    return {
      statusCode: 400,
      headers: responseHeaders,
      body: JSON.stringify({ error: "file not allowed" }),
    };
  }

  // 3. Fetch from Private GitHub Repository with GH_PAT
  const ghPat = process.env.GH_PAT;
  const upstreamUrl = `https://raw.githubusercontent.com/toanilsharma/midcap-swing-scanner/main/${file}`;

  try {
    const fetchHeaders = {
      "User-Agent": "Midcap-Swing-Scanner-Netlify-Proxy",
    };
    if (ghPat) {
      fetchHeaders["Authorization"] = `Bearer ${ghPat}`;
    }

    const upstreamRes = await fetch(upstreamUrl, {
      method: "GET",
      headers: fetchHeaders,
    });

    if (upstreamRes.status === 404) {
      return {
        statusCode: 404,
        headers: responseHeaders,
        body: JSON.stringify({ error: "not found" }),
      };
    }

    if (!upstreamRes.ok) {
      return {
        statusCode: 502,
        headers: responseHeaders,
        body: JSON.stringify({ error: "upstream fetch failure" }),
      };
    }

    const bodyText = await upstreamRes.text();
    return {
      statusCode: 200,
      headers: responseHeaders,
      body: bodyText,
    };
  } catch (err) {
    // Fail-closed with generic message: NEVER leak internal details or PAT
    return {
      statusCode: 502,
      headers: responseHeaders,
      body: JSON.stringify({ error: "gateway connection error" }),
    };
  }
};
