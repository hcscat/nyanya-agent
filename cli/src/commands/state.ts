import fs from "fs";
import path from "path";
import {
  RuntimeLayout,
  chmodDirOwnerOnly,
  chmodOwnerOnly,
  defaultUserStateRoot,
  ensureDir,
  resolveRuntimeLayout
} from "../runtime/project";

const DURABLE_ITEMS = [".env", "config", "data", "sessions"];
const MIGRATION_ITEMS = [...DURABLE_ITEMS, "downloads", "logs"];

function timestamp(): string {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

function isNonEmptyDirectory(directory: string): boolean {
  return fs.existsSync(directory) && fs.statSync(directory).isDirectory() && fs.readdirSync(directory).length > 0;
}

function copyItems(sourceRoot: string, targetRoot: string, items: string[]): string[] {
  ensureDir(targetRoot);
  chmodDirOwnerOnly(targetRoot);
  const copied: string[] = [];
  for (const item of items) {
    const source = path.join(sourceRoot, item);
    if (!fs.existsSync(source)) {
      continue;
    }
    const target = path.join(targetRoot, item);
    fs.cpSync(source, target, { recursive: true, errorOnExist: true, force: false });
    copied.push(item);
  }
  const envPath = path.join(targetRoot, ".env");
  if (fs.existsSync(envPath)) {
    chmodOwnerOnly(envPath);
  }
  return copied;
}

function backup(layout: RuntimeLayout, args: string[]): number {
  const targetArg = args.find((arg) => arg.startsWith("--to="))?.slice("--to=".length);
  const target = path.resolve(
    targetArg || path.join(path.dirname(layout.stateRoot), "NyaNya Agent Backups", timestamp())
  );
  if (fs.existsSync(target)) {
    console.error(`backup_error=target already exists: ${target}`);
    return 1;
  }
  const copied = copyItems(layout.stateRoot, target, DURABLE_ITEMS);
  console.log(`backup_root=${target}`);
  console.log(`backup_items=${copied.join(",")}`);
  console.log("backup_excluded=.venv,run,logs,downloads");
  return 0;
}

function migrate(layout: RuntimeLayout, args: string[]): number {
  const targetArg = args.find((arg) => arg.startsWith("--to="))?.slice("--to=".length);
  const target = path.resolve(targetArg || defaultUserStateRoot());
  if (path.resolve(layout.stateRoot) === target) {
    console.log(`state_root=${target}`);
    console.log("migration_needed=false");
    return 0;
  }
  if (isNonEmptyDirectory(target)) {
    console.error(`migration_error=target is not empty: ${target}`);
    return 1;
  }
  const copied = copyItems(layout.stateRoot, target, MIGRATION_ITEMS);
  console.log(`migration_source=${layout.stateRoot}`);
  console.log(`migration_target=${target}`);
  console.log(`migration_items=${copied.join(",")}`);
  console.log("migration_excluded=.venv,run");
  console.log(`next=NYANYA_HOME="${target}" nyanya setup --non-interactive`);
  return 0;
}

export function state(projectRoot: string, args: string[]): number {
  const layout = resolveRuntimeLayout(projectRoot);
  const command = args[0] || "show";
  if (command === "show") {
    console.log(`code_root=${layout.codeRoot}`);
    console.log(`state_root=${layout.stateRoot}`);
    console.log(`state_mode=${layout.legacyState ? "legacy-source" : "user"}`);
    return 0;
  }
  if (command === "backup") {
    return backup(layout, args.slice(1));
  }
  if (command === "migrate") {
    return migrate(layout, args.slice(1));
  }
  console.error(`Unknown state command: ${command}`);
  console.error("Available: show, backup, migrate");
  return 2;
}
