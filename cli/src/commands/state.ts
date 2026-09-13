import fs from "fs";
import path from "path";
import { run } from "../runtime/process";
import { pythonCommand, pythonEnv } from "../runtime/python";
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

function canonicalDestination(value: string): string {
  const full = path.resolve(value);
  if (fs.existsSync(full)) return fs.realpathSync(full);
  const parent = path.dirname(full);
  return path.join(canonicalDestination(parent), path.basename(full));
}

function copyItems(sourceRoot: string, targetRoot: string, items: string[], layout: RuntimeLayout): string[] {
  const relative = path.relative(fs.realpathSync(sourceRoot), canonicalDestination(targetRoot));
  if (!relative || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))) {
    throw new Error("State copy destination must be outside the source state directory");
  }
  ensureDir(targetRoot);
  chmodDirOwnerOnly(targetRoot);
  const copied: string[] = [];
  for (const item of items) {
    const source = path.join(sourceRoot, item);
    if (!fs.existsSync(source)) {
      continue;
    }
    const target = path.join(targetRoot, item);
    copyStateEntry(source, target, layout);
    copied.push(item);
  }
  const envPath = path.join(targetRoot, ".env");
  if (fs.existsSync(envPath)) {
    chmodOwnerOnly(envPath);
  }
  return copied;
}

function copyStateEntry(source: string, target: string, layout: RuntimeLayout): void {
  const stat = fs.lstatSync(source);
  if (stat.isSymbolicLink()) throw new Error("State backup refuses symlinks");
  if (stat.isDirectory()) {
    fs.mkdirSync(target, { mode: 0o700 });
    for (const name of fs.readdirSync(source)) {
      if (name.endsWith("-wal") || name.endsWith("-shm")) continue;
      copyStateEntry(path.join(source, name), path.join(target, name), layout);
    }
  } else if (stat.isFile()) {
    if (/\.(db|sqlite|sqlite3)$/i.test(source)) {
      const result = run(pythonCommand(layout), ["-m", "nyanya_agent.state_backup", source, target], {
        cwd: layout.codeRoot, env: pythonEnv(layout)
      });
      if (result.status !== 0) throw new Error("Consistent database backup failed; source state was preserved");
    } else {
      fs.copyFileSync(source, target, fs.constants.COPYFILE_EXCL);
      chmodOwnerOnly(target);
    }
  } else {
    throw new Error("State backup refuses special files");
  }
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
  const copied = copyItems(layout.stateRoot, target, DURABLE_ITEMS, layout);
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
  const copied = copyItems(layout.stateRoot, target, MIGRATION_ITEMS, layout);
  console.log(`migration_source=${layout.stateRoot}`);
  console.log(`migration_target=${target}`);
  console.log(`migration_items=${copied.join(",")}`);
  console.log("migration_excluded=.venv,run");
  console.log(`next=NYANYA_HOME="${target}" nyanya setup --non-interactive`);
  return 0;
}

function stateCommand(projectRoot: string, args: string[]): number {
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

export function state(projectRoot: string, args: string[]): number {
  try { return stateCommand(projectRoot, args); }
  catch (error) {
    console.error(error instanceof Error ? error.message : "State operation failed");
    return 1;
  }
}
