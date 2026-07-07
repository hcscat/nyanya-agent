import fs from "fs";
import path from "path";
import { doctor } from "./doctor";
import { runPythonModule } from "../runtime/python";
import { chmodDirOwnerOnly, chmodOwnerOnly, ensureDir } from "../runtime/project";
import { createVenv, findPython, installPythonDependencies, satisfiesPython, venvExists } from "../runtime/python";

type SetupOptions = {
  all: boolean;
  skipDeps: boolean;
};

function parseSetupOptions(args: string[]): SetupOptions {
  return {
    all: args.includes("--all") || args.includes("--install-services"),
    skipDeps: args.includes("--skip-deps")
  };
}

function printPrerequisiteHelp(): void {
  console.error("Python 3.11 or newer is required.");
  console.error("Install it first, then run: nyanya setup");
  if (process.platform === "darwin") {
    console.error("macOS example: brew install python@3.12");
  } else if (process.platform === "win32") {
    console.error("Windows example: winget install Python.Python.3.12");
  } else {
    console.error("Linux example: use your distribution package manager to install python3.11+ and python3-venv.");
  }
}

function ensureRuntimeFiles(projectRoot: string): void {
  for (const name of ["data", "logs", "run", "downloads", "config"]) {
    const dir = path.join(projectRoot, name);
    ensureDir(dir);
    chmodDirOwnerOnly(dir);
  }

  const envPath = path.join(projectRoot, ".env");
  const samplePath = path.join(projectRoot, ".env.example");
  if (!fs.existsSync(envPath) && fs.existsSync(samplePath)) {
    fs.copyFileSync(samplePath, envPath);
    chmodOwnerOnly(envPath);
    console.log("env_file=created");
  } else if (fs.existsSync(envPath)) {
    chmodOwnerOnly(envPath);
    console.log("env_file=present");
  } else {
    console.log("env_file=missing_sample");
  }
}

export function setup(projectRoot: string, args: string[]): number {
  const options = parseSetupOptions(args);
  const python = findPython();
  if (!satisfiesPython(python)) {
    printPrerequisiteHelp();
    return 1;
  }

  ensureRuntimeFiles(projectRoot);

  if (!options.skipDeps) {
    if (!venvExists(projectRoot)) {
      console.log(`venv=create python=${python?.command}`);
      const venvRc = createVenv(projectRoot, python!.command);
      if (venvRc !== 0) {
        return venvRc;
      }
    } else {
      console.log("venv=present");
    }

    console.log("python_dependencies=install");
    const depsRc = installPythonDependencies(projectRoot);
    if (depsRc !== 0) {
      return depsRc;
    }
  } else {
    console.log("python_dependencies=skipped");
  }

  if (options.all) {
    if (process.platform !== "darwin") {
      console.error("service_install=skipped reason=launchagent_requires_macos");
    } else {
      const serviceRc = runPythonModule(projectRoot, "nyanya_agent.manager", ["start-all"]);
      if (serviceRc !== 0) {
        return serviceRc;
      }
    }
  }

  return doctor(projectRoot);
}
