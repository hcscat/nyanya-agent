import fs from "fs";
import path from "path";
import { run, runInherit } from "./process";

export type PythonCandidate = {
  command: string;
  versionText: string;
  major: number;
  minor: number;
  patch: number;
};

export function venvPython(projectRoot: string): string {
  return process.platform === "win32"
    ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
    : path.join(projectRoot, ".venv", "bin", "python");
}

export function venvExists(projectRoot: string): boolean {
  return fs.existsSync(venvPython(projectRoot));
}

export function pythonCommand(projectRoot: string): string {
  const localPython = venvPython(projectRoot);
  if (fs.existsSync(localPython)) {
    return localPython;
  }
  return process.env.PYTHON || "python3";
}

export function pythonEnv(projectRoot: string): NodeJS.ProcessEnv {
  const srcPath = path.join(projectRoot, "src");
  return {
    ...process.env,
    NYANYA_PROJECT_ROOT: projectRoot,
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

export function createVenv(projectRoot: string, python: string): number {
  return runInherit(python, ["-m", "venv", path.join(projectRoot, ".venv")], { cwd: projectRoot });
}

export function installPythonDependencies(projectRoot: string): number {
  const python = venvPython(projectRoot);
  const pipUpgrade = runInherit(python, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: projectRoot });
  if (pipUpgrade !== 0) {
    return pipUpgrade;
  }
  return runInherit(python, ["-m", "pip", "install", "-e", ".[bots,dashboard]"], { cwd: projectRoot });
}

export function runPythonModule(projectRoot: string, moduleName: string, args: string[]): number {
  return runInherit(pythonCommand(projectRoot), ["-m", moduleName, ...args], {
    cwd: projectRoot,
    env: pythonEnv(projectRoot)
  });
}
