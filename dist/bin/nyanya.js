#!/usr/bin/env node
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.main = main;
const doctor_1 = require("../commands/doctor");
const service_1 = require("../commands/service");
const setup_1 = require("../commands/setup");
const project_1 = require("../runtime/project");
const python_1 = require("../runtime/python");
function help() {
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
function main(argv) {
    const projectRoot = (0, project_1.findProjectRoot)(__dirname);
    const [command, ...rest] = argv;
    if (!command || command === "--help" || command === "-h" || command === "help") {
        help();
        return 0;
    }
    if (command === "setup") {
        return (0, setup_1.setup)(projectRoot, rest);
    }
    if (command === "doctor") {
        return (0, doctor_1.doctor)(projectRoot);
    }
    if (command === "repair") {
        return (0, setup_1.setup)(projectRoot, rest);
    }
    if (command === "service") {
        return (0, service_1.service)(projectRoot, rest);
    }
    return (0, python_1.runPythonModule)(projectRoot, "nyanya_agent.core", [command, ...rest]);
}
if (require.main === module) {
    process.exit(main(process.argv.slice(2)));
}
