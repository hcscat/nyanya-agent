import fs from "fs";
import os from "os";
import path from "path";

export function findProjectRoot(startDir: string = __dirname): string {
  const override = process.env.NYANYA_PROJECT_ROOT?.trim();
  if (override) {
    return path.resolve(expandHome(override));
  }

  let current = path.resolve(startDir);
  while (true) {
    if (
      fs.existsSync(path.join(current, "pyproject.toml")) &&
      fs.existsSync(path.join(current, "src", "nyanya_agent"))
    ) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return path.resolve(process.cwd());
    }
    current = parent;
  }
}

export function expandHome(value: string): string {
  if (value === "~") {
    return os.homedir();
  }
  if (value.startsWith("~/")) {
    return path.join(os.homedir(), value.slice(2));
  }
  return value;
}

export function projectPath(root: string, ...parts: string[]): string {
  return path.join(root, ...parts);
}

export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

export function chmodOwnerOnly(filePath: string): void {
  if (process.platform !== "win32") {
    fs.chmodSync(filePath, 0o600);
  }
}

export function chmodDirOwnerOnly(dirPath: string): void {
  if (process.platform !== "win32") {
    fs.chmodSync(dirPath, 0o700);
  }
}
