import fs from "fs";
import path from "path";
import { run, runInherit } from "./process";
import { RuntimeLayout, resolveRuntimeLayout } from "./project";

export type PythonCandidate = {
  command: string;
  versionText: string;
  major: number;
  minor: number;
  patch: number;
};

export function venvPython(stateRoot: string): string {
  return process.platform === "win32"
    ? path.join(stateRoot, ".venv", "Scripts", "python.exe")
    : path.join(stateRoot, ".venv", "bin", "python");
}

export function venvExists(stateRoot: string): boolean {
  return fs.existsSync(venvPython(stateRoot));
}

export function pythonCommand(layout: RuntimeLayout): string {
  const localPython = venvPython(layout.stateRoot);
  if (fs.existsSync(localPython)) {
    return localPython;
  }
  return process.env.PYTHON || "python3";
}

export function pythonEnv(layout: RuntimeLayout): NodeJS.ProcessEnv {
  const srcPath = path.join(layout.codeRoot, "src");
  return {
    ...process.env,
    NYANYA_PROJECT_ROOT: layout.codeRoot,
    NYANYA_HOME: layout.stateRoot,
    NYANYA_ENV_FILE: layout.envPath,
    PYTHONPATH: process.env.PYTHONPATH ? `${srcPath}${path.delimiter}${process.env.PYTHONPATH}` : srcPath
  };
}

export function findPython(): PythonCandidate | null {
  const candidates = [process.env.PYTHON, "python3.12", "python3.11", "python3"].filter(Boolean) as string[];
  for (const command of candidates) {
    const result = run(command, ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"]);
    if (result.status !== 0 || !result.stdout.trim()) {
      continue;
    }
    const versionText = result.stdout.trim();
    const [major, minor, patch] = versionText.split(".").map((part) => Number.parseInt(part, 10));
    if (Number.isFinite(major) && Number.isFinite(minor) && Number.isFinite(patch)) {
      return { command, versionText, major, minor, patch };
    }
  }
  return null;
}

export function satisfiesPython(candidate: PythonCandidate | null): boolean {
  if (!candidate) {
    return false;
  }
  return candidate.major > 3 || (candidate.major === 3 && candidate.minor >= 11);
}

export function createVenv(layout: RuntimeLayout, python: string): number {
  return runInherit(python, ["-m", "venv", layout.venvRoot], { cwd: layout.codeRoot });
}

export function installPythonDependencies(layout: RuntimeLayout): number {
  const python = venvPython(layout.stateRoot);
  const pipUpgrade = runInherit(python, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: layout.codeRoot });
  if (pipUpgrade !== 0) {
    return pipUpgrade;
  }
  return runInherit(python, ["-m", "pip", "install", "--upgrade", `${layout.codeRoot}[bots,dashboard]`], { cwd: layout.codeRoot });
}

export function runPythonModule(projectRoot: string, moduleName: string, args: string[]): number {
  const layout = resolveRuntimeLayout(projectRoot);
  return runInherit(pythonCommand(layout), ["-m", moduleName, ...args], {
    cwd: layout.codeRoot,
    env: pythonEnv(layout)
  });
}
