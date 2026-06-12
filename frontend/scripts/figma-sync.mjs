#!/usr/bin/env node

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const FIGMA_API_BASE = "https://api.figma.com/v1";

async function loadEnvFiles() {
  const envFiles = [".env.local", ".env"];
  for (const fileName of envFiles) {
    const fullPath = path.resolve(fileName);
    let content = "";
    try {
      content = await readFile(fullPath, "utf8");
    } catch {
      continue;
    }

    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) {
        continue;
      }
      const separator = line.indexOf("=");
      if (separator <= 0) {
        continue;
      }
      const key = line.slice(0, separator).trim();
      let value = line.slice(separator + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (process.env[key] === undefined) {
        process.env[key] = value;
      }
    }
  }
}

function getEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) {
      continue;
    }
    const key = arg.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = "true";
      continue;
    }
    args[key] = next;
    i += 1;
  }
  return args;
}

function parseNodeIds(raw) {
  if (!raw) {
    return [];
  }
  return raw
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean);
}

async function figmaRequest(endpoint, searchParams = undefined) {
  const token = getEnv("FIGMA_ACCESS_TOKEN");
  const url = new URL(`${FIGMA_API_BASE}${endpoint}`);
  if (searchParams) {
    Object.entries(searchParams).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await fetch(url, {
    headers: {
      "X-Figma-Token": token,
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Figma API error ${response.status}: ${body}`);
  }

  return response.json();
}

async function writeJsonFile(filePath, data) {
  const fullPath = path.resolve(filePath);
  await mkdir(path.dirname(fullPath), { recursive: true });
  await writeFile(fullPath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  return fullPath;
}

async function downloadFile(url, filePath) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download asset (${response.status}) from ${url}`);
  }
  const arrayBuffer = await response.arrayBuffer();
  const fullPath = path.resolve(filePath);
  await mkdir(path.dirname(fullPath), { recursive: true });
  await writeFile(fullPath, Buffer.from(arrayBuffer));
  return fullPath;
}

function requireFileKey(args) {
  return args.file || process.env.FIGMA_FILE_KEY || "";
}

async function runCheck() {
  const me = await figmaRequest("/me");
  console.log(`Connected to Figma as: ${me.email}`);
}

async function runFile(args) {
  const fileKey = requireFileKey(args);
  if (!fileKey) {
    throw new Error("Provide --file <FILE_KEY> or set FIGMA_FILE_KEY.");
  }

  const nodeIds = parseNodeIds(args.nodes);
  const payload = await figmaRequest(`/files/${fileKey}`, {
    ids: nodeIds.length > 0 ? nodeIds.join(",") : undefined,
    depth: args.depth,
  });

  const outPath = args.out || `figma-output/file-${fileKey}.json`;
  const savedPath = await writeJsonFile(outPath, payload);
  console.log(`Saved file JSON: ${savedPath}`);
}

async function runImages(args) {
  const fileKey = requireFileKey(args);
  if (!fileKey) {
    throw new Error("Provide --file <FILE_KEY> or set FIGMA_FILE_KEY.");
  }

  const nodeIds = parseNodeIds(args.nodes);
  if (nodeIds.length === 0) {
    throw new Error("Provide --nodes <id1,id2,...> for image export.");
  }

  const format = args.format || "png";
  const scale = args.scale || "2";
  const outputDir = args.out || "figma-output/assets";

  const payload = await figmaRequest(`/images/${fileKey}`, {
    ids: nodeIds.join(","),
    format,
    scale,
  });

  const images = payload.images || {};
  const downloads = Object.entries(images).map(async ([nodeId, url]) => {
    if (!url) {
      return null;
    }
    const safeNodeId = nodeId.replace(/[^a-zA-Z0-9_-]/g, "_");
    const target = path.join(outputDir, `${safeNodeId}.${format}`);
    const savedPath = await downloadFile(url, target);
    return { nodeId, savedPath };
  });

  const saved = (await Promise.all(downloads)).filter(Boolean);
  const manifestPath = await writeJsonFile(path.join(outputDir, "manifest.json"), {
    fileKey,
    format,
    scale: Number(scale),
    saved,
  });

  console.log(`Downloaded ${saved.length} assets to ${path.resolve(outputDir)}`);
  console.log(`Saved manifest: ${manifestPath}`);
}

async function main() {
  const command = process.argv[2];
  const args = parseArgs(process.argv.slice(3));
  await loadEnvFiles();

  if (!command || command === "help" || command === "--help") {
    console.log(
      [
        "Usage:",
        "  npm run figma:check",
        "  npm run figma:file -- --file <FILE_KEY> [--nodes <id1,id2>] [--depth <n>] [--out <path>]",
        "  npm run figma:images -- --file <FILE_KEY> --nodes <id1,id2> [--format png|jpg|svg|pdf] [--scale 2] [--out <dir>]",
        "",
        "Env vars:",
        "  FIGMA_ACCESS_TOKEN (required)",
        "  FIGMA_FILE_KEY (optional default file key)",
      ].join("\n")
    );
    return;
  }

  if (command === "check") {
    await runCheck();
    return;
  }
  if (command === "file") {
    await runFile(args);
    return;
  }
  if (command === "images") {
    await runImages(args);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
