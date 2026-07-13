#!/usr/bin/env node
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.main = main;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const config_1 = require("../commands/config");
const doctor_1 = require("../commands/doctor");
const service_1 = require("../commands/service");
const setup_1 = require("../commands/setup");
const state_1 = require("../commands/state");
const project_1 = require("../runtime/project");
const python_1 = require("../runtime/python");
function help() {
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
function printVersion(projectRoot) {
    const manifestPath = path_1.default.join(projectRoot, "package.json");
    const manifest = JSON.parse(fs_1.default.readFileSync(manifestPath, "utf8"));
    console.log(manifest.version || "unknown");
    return 0;
}
function runAgent(projectRoot, args) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    if (!fs_1.default.existsSync(layout.envPath) || !fs_1.default.existsSync(layout.venvRoot)) {
        console.error("setup_required=true");
        console.error("next=nyanya setup");
        console.error(`state_root=${layout.stateRoot}`);
        return 1;
    }
    console.log("NyaNya Agent");
    (0, config_1.printConfigStatus)(projectRoot);
    return (0, python_1.runPythonModule)(projectRoot, "nyanya_agent.core", args);
}
function main(argv) {
    const projectRoot = (0, project_1.findProjectRoot)(__dirname);
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
        return (0, setup_1.setup)(projectRoot, rest);
    }
    if (command === "config") {
        return (0, config_1.configure)(projectRoot, rest);
    }
    if (command === "auth") {
        return (0, config_1.configure)(projectRoot, rest, "provider");
    }
    if (command === "doctor") {
        return (0, doctor_1.doctor)(projectRoot, rest);
    }
    if (command === "repair") {
        return (0, setup_1.setup)(projectRoot, ["--all", "--non-interactive", ...rest]);
    }
    if (command === "service") {
        return (0, service_1.service)(projectRoot, rest);
    }
    if (command === "state") {
        return (0, state_1.state)(projectRoot, rest);
    }
    if (command === "paths") {
        return (0, config_1.printConfigStatus)(projectRoot);
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
