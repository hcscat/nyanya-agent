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
function venvPython(projectRoot) {
    return process.platform === "win32"
        ? path_1.default.join(projectRoot, ".venv", "Scripts", "python.exe")
        : path_1.default.join(projectRoot, ".venv", "bin", "python");
}
function venvExists(projectRoot) {
    return fs_1.default.existsSync(venvPython(projectRoot));
}
function pythonCommand(projectRoot) {
    const localPython = venvPython(projectRoot);
    if (fs_1.default.existsSync(localPython)) {
        return localPython;
    }
    return process.env.PYTHON || "python3";
}
function pythonEnv(projectRoot) {
    const srcPath = path_1.default.join(projectRoot, "src");
    return {
        ...process.env,
        NYANYA_PROJECT_ROOT: projectRoot,
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
function createVenv(projectRoot, python) {
    return (0, process_1.runInherit)(python, ["-m", "venv", path_1.default.join(projectRoot, ".venv")], { cwd: projectRoot });
}
function installPythonDependencies(projectRoot) {
    const python = venvPython(projectRoot);
    const pipUpgrade = (0, process_1.runInherit)(python, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: projectRoot });
    if (pipUpgrade !== 0) {
        return pipUpgrade;
    }
    return (0, process_1.runInherit)(python, ["-m", "pip", "install", "-e", ".[bots,dashboard]"], { cwd: projectRoot });
}
function runPythonModule(projectRoot, moduleName, args) {
    return (0, process_1.runInherit)(pythonCommand(projectRoot), ["-m", moduleName, ...args], {
        cwd: projectRoot,
        env: pythonEnv(projectRoot)
    });
}
