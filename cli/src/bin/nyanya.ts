#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { configure, printConfigStatus } from "../commands/config";
import { doctor } from "../commands/doctor";
import { service } from "../commands/service";
import { setup } from "../commands/setup";
import { state } from "../commands/state";
import { findProjectRoot, resolveRuntimeLayout } from "../runtime/project";
import { runPythonModule } from "../runtime/python";

function help(): void {
  console.log(`NyaNya Agent

Usage:
  nyanya setup [--all] [--skip-deps] [--configure] [--non-interactive]
  nyanya config [edit|show|validate]
  nyanya auth
  nyanya doctor [--backend]
  nyanya repair
  nyanya service [status|start|stop|restart|health|repair|uninstall]
  nyanya state [show|backup|migrate]
  nyanya paths
  nyanya update
  nyanya [agent options]

Examples:
  nyanya setup
  nyanya setup --all
  nyanya config
  nyanya doctor
  nyanya service status
  nyanya service stop
  nyanya --check
`);
}

function printVersion(projectRoot: string): number {
  const manifestPath = path.join(projectRoot, "package.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8")) as { version?: string };
  console.log(manifest.version || "unknown");
  return 0;
}

function runAgent(projectRoot: string, args: string[]): number {
  const layout = resolveRuntimeLayout(projectRoot);
  if (!fs.existsSync(layout.envPath) || !fs.existsSync(layout.venvRoot)) {
    console.error("setup_required=true");
    console.error("next=nyanya setup");
    console.error(`state_root=${layout.stateRoot}`);
    return 1;
  }
  console.log("NyaNya Agent");
  printConfigStatus(projectRoot);
  return runPythonModule(projectRoot, "nyanya_agent.core", args);
}

export function main(argv: string[]): number {
  const projectRoot = findProjectRoot(__dirname);
  const [command, ...rest] = argv;

  if (command === "--help" || command === "-h" || command === "help") {
    help();
    return 0;
  }
  if (command === "--version" || command === "-V" || command === "version") {
    return printVersion(projectRoot);
  }
  if (!command) {
    return runAgent(projectRoot, []);
  }
  if (command === "setup") {
    return setup(projectRoot, rest);
  }
  if (command === "config") {
    return configure(projectRoot, rest);
  }
  if (command === "auth") {
    return configure(projectRoot, rest, "provider");
  }
  if (command === "doctor") {
    return doctor(projectRoot, rest);
  }
  if (command === "repair") {
    return setup(projectRoot, ["--all", "--non-interactive", ...rest]);
  }
  if (command === "service") {
    return service(projectRoot, rest);
  }
  if (command === "state") {
    return state(projectRoot, rest);
  }
  if (command === "paths") {
    return printConfigStatus(projectRoot);
  }
  if (command === "update") {
    console.log("update_command=npm update -g @hcscat-dev/nyanya-agent");
    console.log("update_next=nyanya setup --non-interactive && nyanya service restart");
    console.log("data_policy=NYANYA_HOME is preserved outside the npm package directory");
    return 0;
  }

  return runAgent(projectRoot, [command, ...rest]);
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
}
