"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.doctor = doctor;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const process_1 = require("../runtime/process");
const python_1 = require("../runtime/python");
function checkImport(projectRoot, moduleName) {
    const result = (0, process_1.run)((0, python_1.pythonCommand)(projectRoot), ["-c", `import ${moduleName}; print("ok")`], {
        cwd: projectRoot,
        env: (0, python_1.pythonEnv)(projectRoot)
    });
    return {
        name: `python_import_${moduleName}`,
        ok: result.status === 0,
        detail: result.status === 0 ? "ok" : "missing"
    };
}
function doctor(projectRoot) {
    const python = (0, python_1.findPython)();
    const nodeVersion = process.version;
    const git = (0, process_1.run)("git", ["--version"]);
    const envPath = path_1.default.join(projectRoot, ".env");
    const checks = [
        { name: "project_root", ok: fs_1.default.existsSync(path_1.default.join(projectRoot, "pyproject.toml")), detail: projectRoot },
        { name: "node", ok: true, detail: nodeVersion },
        {
            name: "python_3_11_plus",
            ok: (0, python_1.satisfiesPython)(python),
            detail: python ? `${python.command} ${python.versionText}` : "missing"
        },
        { name: "git", ok: git.status === 0, detail: git.status === 0 ? git.stdout.trim() : "missing" },
        { name: "venv", ok: (0, python_1.venvExists)(projectRoot), detail: (0, python_1.venvExists)(projectRoot) ? ".venv present" : ".venv missing" },
        { name: "env_file", ok: fs_1.default.existsSync(envPath), detail: fs_1.default.existsSync(envPath) ? "configured" : "missing" },
        checkImport(projectRoot, "nyanya_agent.core"),
        checkImport(projectRoot, "discord"),
        checkImport(projectRoot, "fastapi"),
        checkImport(projectRoot, "uvicorn")
    ];
    let rc = 0;
    for (const check of checks) {
        const status = check.ok ? "ok" : "fail";
        console.log(`${check.name}=${status} detail=${check.detail}`);
        if (!check.ok && check.name !== "git") {
            rc = 1;
        }
    }
    return rc;
}
