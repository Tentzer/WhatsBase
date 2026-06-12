import { NextRequest, NextResponse } from "next/server";

const METRICS_PATH = "/api/public/v2/metrics";
const OBSERVATIONS_PATH = "/api/public/v2/observations";

function getLangfuseConfig() {
  const publicKey = process.env.LANGFUSE_PUBLIC_KEY;
  const secretKey = process.env.LANGFUSE_SECRET_KEY;
  const host = process.env.LANGFUSE_HOST;

  if (!publicKey || !secretKey || !host) {
    throw new Error("Langfuse environment variables are missing");
  }

  return {
    publicKey,
    secretKey,
    host: host.endsWith("/") ? host.slice(0, -1) : host,
  };
}

function createBasicAuthHeader(publicKey: string, secretKey: string): string {
  return `Basic ${Buffer.from(`${publicKey}:${secretKey}`).toString("base64")}`;
}

function appendForwardedParams(source: URL, target: URL) {
  source.searchParams.forEach((value, key) => {
    if (key !== "endpoint") {
      target.searchParams.append(key, value);
    }
  });
}

export async function POST(request: NextRequest) {
  const endpoint = request.nextUrl.searchParams.get("endpoint");
  if (endpoint !== "metrics") {
    return NextResponse.json({ error: "Only endpoint=metrics supports POST" }, { status: 400 });
  }

  let body: unknown = null;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  let config: ReturnType<typeof getLangfuseConfig>;
  try {
    config = getLangfuseConfig();
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Langfuse config error" },
      { status: 500 },
    );
  }

  const auth = createBasicAuthHeader(config.publicKey, config.secretKey);
  const targetUrl = new URL(`${config.host}${METRICS_PATH}`);
  appendForwardedParams(request.nextUrl, targetUrl);

  const response = await fetch(targetUrl.toString(), {
    method: "POST",
    headers: {
      Authorization: auth,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  // Cloud deployments that only support GET still work through this proxy.
  if (response.status === 405) {
    targetUrl.searchParams.set("query", JSON.stringify(body));
    const fallback = await fetch(targetUrl.toString(), {
      method: "GET",
      headers: { Authorization: auth },
      cache: "no-store",
    });
    const fallbackJson = await fallback.json();
    return NextResponse.json(fallbackJson, { status: fallback.status });
  }

  const json = await response.json();
  return NextResponse.json(json, { status: response.status });
}

export async function GET(request: NextRequest) {
  const endpoint = request.nextUrl.searchParams.get("endpoint");
  if (endpoint !== "observations") {
    return NextResponse.json({ error: "Use endpoint=observations for GET" }, { status: 400 });
  }

  let config: ReturnType<typeof getLangfuseConfig>;
  try {
    config = getLangfuseConfig();
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Langfuse config error" },
      { status: 500 },
    );
  }

  const auth = createBasicAuthHeader(config.publicKey, config.secretKey);
  const targetUrl = new URL(`${config.host}${OBSERVATIONS_PATH}`);
  appendForwardedParams(request.nextUrl, targetUrl);

  const response = await fetch(targetUrl.toString(), {
    method: "GET",
    headers: { Authorization: auth },
    cache: "no-store",
  });

  const json = await response.json();
  return NextResponse.json(json, { status: response.status });
}
