#!/usr/bin/env node
import { doctor } from "../commands/doctor";
import { service } from "../commands/service";
import { setup } from "../commands/setup";
import { findProjectRoot } from "../runtime/project";
import { runPythonModule } from "../runtime/python";

function help(): void {
  console.log(`NyaNya Agent

Usage:
  nyanya setup [--all] [--skip-deps]
  nyanya doctor
  nyanya repair
  nyanya service [status|start|restart|health|repair]
  nyanya [agent options]

Examples:
  nyanya setup
  nyanya setup --all
  nyanya doctor
  nyanya service status
  nyanya --check
`);
}

export function main(argv: string[]): number {
  const projectRoot = findProjectRoot(__dirname);
  const [command, ...rest] = argv;

  if (!command || command === "--help" || command === "-h" || command === "help") {
    help();
    return 0;
  }
  if (command === "setup") {
    return setup(projectRoot, rest);
  }
  if (command === "doctor") {
    return doctor(projectRoot);
  }
  if (command === "repair") {
    return setup(projectRoot, rest);
  }
  if (command === "service") {
    return service(projectRoot, rest);
  }

  return runPythonModule(projectRoot, "nyanya_agent.core", [command, ...rest]);
}

if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
}
