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

  const expectedKey = process.env.DASH_KEY_HASH || "ad15418e84fe6e94ec8dd2c22e7f952fc90457256ffbc0f59dcffdef0509366d";
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

  // 3. Fetch from Private GitHub Repository via GitHub API or Raw Fallback
  const ghPat = process.env.GH_PAT;
  const apiUrl = `https://api.github.com/repos/toanilsharma/midcap-swing-scanner/contents/${file}`;
  const rawUrl = `https://raw.githubusercontent.com/toanilsharma/midcap-swing-scanner/main/${file}`;

  try {
    let upstreamRes;

    if (ghPat) {
      // Official GitHub API endpoint for private repos with PAT
      upstreamRes = await fetch(apiUrl, {
        method: "GET",
        headers: {
          "User-Agent": "Midcap-Swing-Scanner-Netlify-Proxy",
          "Accept": "application/vnd.github.raw",
          "Authorization": `Bearer ${ghPat}`,
          "X-GitHub-Api-Version": "2022-11-28",
        },
      });
    } else {
      // Fallback to raw domain (works if repo is public)
      upstreamRes = await fetch(rawUrl, {
        method: "GET",
        headers: {
          "User-Agent": "Midcap-Swing-Scanner-Netlify-Proxy",
        },
      });
    }

    if (upstreamRes.status === 404) {
      return {
        statusCode: 404,
        headers: responseHeaders,
        body: JSON.stringify({ 
          error: "not found",
          hint: ghPat ? "File not found in repo" : "GH_PAT environment variable is missing on Netlify for private repo"
        }),
      };
    }

    if (!upstreamRes.ok) {
      return {
        statusCode: upstreamRes.status || 502,
        headers: responseHeaders,
        body: JSON.stringify({ error: "upstream fetch failure", upstreamStatus: upstreamRes.status }),
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
