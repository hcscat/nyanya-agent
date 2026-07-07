"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.setup = setup;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const doctor_1 = require("./doctor");
const python_1 = require("../runtime/python");
const project_1 = require("../runtime/project");
const python_2 = require("../runtime/python");
function parseSetupOptions(args) {
    return {
        all: args.includes("--all") || args.includes("--install-services"),
        skipDeps: args.includes("--skip-deps")
    };
}
function printPrerequisiteHelp() {
    console.error("Python 3.11 or newer is required.");
    console.error("Install it first, then run: nyanya setup");
    if (process.platform === "darwin") {
        console.error("macOS example: brew install python@3.12");
    }
    else if (process.platform === "win32") {
        console.error("Windows example: winget install Python.Python.3.12");
    }
    else {
        console.error("Linux example: use your distribution package manager to install python3.11+ and python3-venv.");
    }
}
function ensureRuntimeFiles(projectRoot) {
    for (const name of ["data", "logs", "run", "downloads", "config"]) {
        const dir = path_1.default.join(projectRoot, name);
        (0, project_1.ensureDir)(dir);
        (0, project_1.chmodDirOwnerOnly)(dir);
    }
    const envPath = path_1.default.join(projectRoot, ".env");
    const samplePath = path_1.default.join(projectRoot, ".env.example");
    if (!fs_1.default.existsSync(envPath) && fs_1.default.existsSync(samplePath)) {
        fs_1.default.copyFileSync(samplePath, envPath);
        (0, project_1.chmodOwnerOnly)(envPath);
        console.log("env_file=created");
    }
    else if (fs_1.default.existsSync(envPath)) {
        (0, project_1.chmodOwnerOnly)(envPath);
        console.log("env_file=present");
    }
    else {
        console.log("env_file=missing_sample");
    }
}
function setup(projectRoot, args) {
    const options = parseSetupOptions(args);
    const python = (0, python_2.findPython)();
    if (!(0, python_2.satisfiesPython)(python)) {
        printPrerequisiteHelp();
        return 1;
    }
    ensureRuntimeFiles(projectRoot);
    if (!options.skipDeps) {
        if (!(0, python_2.venvExists)(projectRoot)) {
            console.log(`venv=create python=${python?.command}`);
            const venvRc = (0, python_2.createVenv)(projectRoot, python.command);
            if (venvRc !== 0) {
                return venvRc;
            }
        }
        else {
            console.log("venv=present");
        }
        console.log("python_dependencies=install");
        const depsRc = (0, python_2.installPythonDependencies)(projectRoot);
        if (depsRc !== 0) {
            return depsRc;
        }
    }
    else {
        console.log("python_dependencies=skipped");
    }
    if (options.all) {
        if (process.platform !== "darwin") {
            console.error("service_install=skipped reason=launchagent_requires_macos");
        }
        else {
            const serviceRc = (0, python_1.runPythonModule)(projectRoot, "nyanya_agent.manager", ["start-all"]);
            if (serviceRc !== 0) {
                return serviceRc;
            }
        }
    }
    return (0, doctor_1.doctor)(projectRoot);
}
