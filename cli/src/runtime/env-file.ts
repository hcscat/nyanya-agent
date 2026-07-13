import fs from "fs";
import path from "path";
import { chmodOwnerOnly, ensureDir } from "./project";

export type EnvValidation = {
  values: Record<string, string>;
  errors: string[];
  warnings: string[];
};

const KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const BOOLEAN_VALUES = new Set(["1", "0", "true", "false", "yes", "no", "on", "off"]);
const BOOLEAN_KEYS = [
  "NYANYA_SAVE_TRANSCRIPTS",
  "NYANYA_CODEX_ENABLED",
  "NYANYA_CODEX_AUTO_ENABLED",
  "NYANYA_CODEX_WRITE_ENABLED",
  "NYANYA_MEMORY_RETRIEVAL_ENABLED",
  "NYANYA_MEMORY_WORKER_LLM_REFINEMENT",
  "NYANYA_ALLOW_UNLISTED",
  "NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS",
  "NYANYA_DASHBOARD_RECORDING_ENABLED",
  "NYANYA_PHASE_CHECK_ENABLED"
];

function unquote(value: string): string {
  if (value.length >= 2 && value[0] === value[value.length - 1] && (value[0] === "\"" || value[0] === "'")) {
    return value.slice(1, -1);
  }
  return value;
}

export function parseEnvText(text: string): EnvValidation {
  const values: Record<string, string> = {};
  const errors: string[] = [];
  const warnings: string[] = [];
  const seen = new Set<string>();
  for (const [index, rawLine] of text.split(/\r?\n/).entries()) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    if (!line.includes("=")) {
      errors.push(`line ${index + 1}: expected KEY=VALUE`);
      continue;
    }
    const [rawKey, ...rest] = line.split("=");
    const key = rawKey.trim();
    if (!KEY_PATTERN.test(key)) {
      errors.push(`line ${index + 1}: invalid key ${key || "<empty>"}`);
      continue;
    }
    if (seen.has(key)) {
      warnings.push(`line ${index + 1}: duplicate key ${key}; last value wins`);
    }
    seen.add(key);
    values[key] = unquote(rest.join("=").trim());
  }
  return { values, errors, warnings };
}

export function readEnvFile(envPath: string): EnvValidation {
  if (!fs.existsSync(envPath)) {
    return { values: {}, errors: ["environment file is missing"], warnings: [] };
  }
  const validation = parseEnvText(fs.readFileSync(envPath, "utf8"));
  const provider = validation.values.NYANYA_PROVIDER;
  if (provider && !["gemini_cli", "ollama", "openai_compatible"].includes(provider)) {
    validation.errors.push(`NYANYA_PROVIDER is unsupported: ${provider}`);
  }
  const port = validation.values.NYANYA_DASHBOARD_PORT;
  if (port) {
    const parsed = Number.parseInt(port, 10);
    if (!/^\d+$/.test(port) || parsed < 1 || parsed > 65535) {
      validation.errors.push("NYANYA_DASHBOARD_PORT must be an integer between 1 and 65535");
    }
  }
  for (const key of BOOLEAN_KEYS) {
    const value = validation.values[key]?.toLowerCase();
    if (value && !BOOLEAN_VALUES.has(value)) {
      validation.errors.push(`${key} must be a boolean value`);
    }
  }
  if (
    validation.values.NYANYA_DISCORD_BOT_TOKEN &&
    !validation.values.NYANYA_DISCORD_ALLOWED_CHANNEL_IDS &&
    !validation.values.NYANYA_DISCORD_ALLOWED_USER_IDS &&
    validation.values.NYANYA_ALLOW_UNLISTED?.toLowerCase() !== "true"
  ) {
    validation.warnings.push("Discord token is configured but no allowed channel or user is configured");
  }
  if (
    validation.values.NYANYA_TELEGRAM_BOT_TOKEN &&
    !validation.values.NYANYA_TELEGRAM_ALLOWED_CHAT_IDS &&
    !validation.values.NYANYA_TELEGRAM_ALLOWED_USER_IDS
  ) {
    validation.warnings.push("Telegram token is configured but no allowed chat or user is configured");
  }
  return validation;
}

function serializeValue(value: string): string {
  if (/\r|\n/.test(value)) {
    throw new Error("Environment values cannot contain newlines");
  }
  return value;
}

export function updateEnvFile(envPath: string, updates: Record<string, string>): void {
  for (const key of Object.keys(updates)) {
    if (!KEY_PATTERN.test(key)) {
      throw new Error(`Invalid environment key: ${key}`);
    }
  }
  const existing = fs.existsSync(envPath) ? fs.readFileSync(envPath, "utf8") : "";
  const written = new Set<string>();
  const lines: string[] = [];
  for (const rawLine of existing.split(/\r?\n/)) {
    const trimmed = rawLine.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) {
      lines.push(rawLine);
      continue;
    }
    const key = trimmed.split("=", 1)[0].trim();
    if (!(key in updates)) {
      lines.push(rawLine);
      continue;
    }
    if (!written.has(key)) {
      lines.push(`${key}=${serializeValue(updates[key])}`);
      written.add(key);
    }
  }
  const pending = Object.entries(updates).filter(([key]) => !written.has(key));
  if (pending.length > 0) {
    if (lines.length && lines[lines.length - 1] !== "") {
      lines.push("");
    }
    lines.push("# Updated by nyanya config.");
    for (const [key, value] of pending) {
      lines.push(`${key}=${serializeValue(value)}`);
    }
  }
  ensureDir(path.dirname(envPath));
  fs.writeFileSync(envPath, `${lines.join("\n").replace(/\n+$/, "")}\n`, "utf8");
  chmodOwnerOnly(envPath);
}

export function secretConfigured(values: Record<string, string>, key: string): boolean {
  return Boolean(values[key] || process.env[key]);
}
