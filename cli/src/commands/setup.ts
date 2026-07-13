import fs from "fs";
import path from "path";
import { configure, printConfigStatus } from "./config";
import { doctor } from "./doctor";
import { runPythonModule } from "../runtime/python";
import { RuntimeLayout, chmodOwnerOnly, ensureRuntimeDirectories, resolveRuntimeLayout } from "../runtime/project";
import { createVenv, findPython, installPythonDependencies, satisfiesPython, venvExists } from "../runtime/python";
import { confirm, interactiveAvailable } from "../runtime/prompt";

type SetupOptions = {
  all: boolean;
  skipDeps: boolean;
  configure: boolean;
  nonInteractive: boolean;
};

function parseSetupOptions(args: string[]): SetupOptions {
  return {
    all: args.includes("--all") || args.includes("--install-services"),
    skipDeps: args.includes("--skip-deps"),
    configure: args.includes("--configure"),
    nonInteractive: args.includes("--non-interactive")
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

function ensureRuntimeFiles(layout: RuntimeLayout): void {
  ensureRuntimeDirectories(layout);
  const samplePath = path.join(layout.codeRoot, ".env.example");
  if (!fs.existsSync(layout.envPath) && fs.existsSync(samplePath)) {
    fs.copyFileSync(samplePath, layout.envPath);
    chmodOwnerOnly(layout.envPath);
    console.log("env_file=created");
  } else if (fs.existsSync(layout.envPath)) {
    chmodOwnerOnly(layout.envPath);
    console.log("env_file=present");
  } else {
    console.log("env_file=missing_sample");
  }
}

export function setup(projectRoot: string, args: string[]): number {
  const options = parseSetupOptions(args);
  const layout = resolveRuntimeLayout(projectRoot);
  const python = findPython();
  if (!satisfiesPython(python)) {
    printPrerequisiteHelp();
    return 1;
  }

  ensureRuntimeFiles(layout);
  console.log(`code_root=${layout.codeRoot}`);
  console.log(`state_root=${layout.stateRoot}`);
  console.log(`state_mode=${layout.legacyState ? "legacy-source" : "user"}`);

  const shouldConfigure = options.configure || (!options.nonInteractive && interactiveAvailable() && confirm("Configure LLM and SNS connections now", true));
  if (shouldConfigure) {
    const configRc = configure(projectRoot);
    if (configRc !== 0) {
      return configRc;
    }
  }
  const configStatusRc = printConfigStatus(projectRoot);
  if (configStatusRc !== 0) {
    return configStatusRc;
  }

  if (!options.skipDeps) {
    if (!venvExists(layout.stateRoot)) {
      console.log(`venv=create python=${python?.command}`);
      const venvRc = createVenv(layout, python!.command);
      if (venvRc !== 0) {
        return venvRc;
      }
    } else {
      console.log("venv=present");
    }

    console.log("python_dependencies=install");
    const depsRc = installPythonDependencies(layout);
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

  return doctor(projectRoot, []);
}
