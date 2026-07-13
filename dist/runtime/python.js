"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.venvPython = venvPython;
exports.venvExists = venvExists;
exports.pythonCommand = pythonCommand;
exports.pythonEnv = pythonEnv;
exports.findPython = findPython;
exports.satisfiesPython = satisfiesPython;
exports.createVenv = createVenv;
exports.installPythonDependencies = installPythonDependencies;
exports.runPythonModule = runPythonModule;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const process_1 = require("./process");
const project_1 = require("./project");
function venvPython(stateRoot) {
    return process.platform === "win32"
        ? path_1.default.join(stateRoot, ".venv", "Scripts", "python.exe")
        : path_1.default.join(stateRoot, ".venv", "bin", "python");
}
function venvExists(stateRoot) {
    return fs_1.default.existsSync(venvPython(stateRoot));
}
function pythonCommand(layout) {
    const localPython = venvPython(layout.stateRoot);
    if (fs_1.default.existsSync(localPython)) {
        return localPython;
    }
    return process.env.PYTHON || "python3";
}
function pythonEnv(layout) {
    const srcPath = path_1.default.join(layout.codeRoot, "src");
    return {
        ...process.env,
        NYANYA_PROJECT_ROOT: layout.codeRoot,
        NYANYA_HOME: layout.stateRoot,
        NYANYA_ENV_FILE: layout.envPath,
        PYTHONPATH: process.env.PYTHONPATH ? `${srcPath}${path_1.default.delimiter}${process.env.PYTHONPATH}` : srcPath
    };
}
function findPython() {
    const candidates = [process.env.PYTHON, "python3.12", "python3.11", "python3"].filter(Boolean);
    for (const command of candidates) {
        const result = (0, process_1.run)(command, ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"]);
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
function satisfiesPython(candidate) {
    if (!candidate) {
        return false;
    }
    return candidate.major > 3 || (candidate.major === 3 && candidate.minor >= 11);
}
function createVenv(layout, python) {
    return (0, process_1.runInherit)(python, ["-m", "venv", layout.venvRoot], { cwd: layout.codeRoot });
}
function installPythonDependencies(layout) {
    const python = venvPython(layout.stateRoot);
    const pipUpgrade = (0, process_1.runInherit)(python, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: layout.codeRoot });
    if (pipUpgrade !== 0) {
        return pipUpgrade;
    }
    return (0, process_1.runInherit)(python, ["-m", "pip", "install", "--upgrade", `${layout.codeRoot}[bots,dashboard]`], { cwd: layout.codeRoot });
}
function runPythonModule(projectRoot, moduleName, args) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    return (0, process_1.runInherit)(pythonCommand(layout), ["-m", moduleName, ...args], {
        cwd: layout.codeRoot,
        env: pythonEnv(layout)
    });
}
