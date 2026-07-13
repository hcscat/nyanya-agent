"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.doctor = doctor;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const process_1 = require("../runtime/process");
const env_file_1 = require("../runtime/env-file");
const project_1 = require("../runtime/project");
const python_1 = require("../runtime/python");
function checkImport(projectRoot, moduleName) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    const result = (0, process_1.run)((0, python_1.pythonCommand)(layout), ["-c", `import ${moduleName}; print("ok")`], {
        cwd: layout.codeRoot,
        env: (0, python_1.pythonEnv)(layout)
    });
    return {
        name: `python_import_${moduleName}`,
        ok: result.status === 0,
        detail: result.status === 0 ? "ok" : "missing"
    };
}
function doctor(projectRoot, args = []) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    const python = (0, python_1.findPython)();
    const nodeVersion = process.version;
    const git = (0, process_1.run)("git", ["--version"]);
    const validation = (0, env_file_1.readEnvFile)(layout.envPath);
    const host = validation.values.NYANYA_DASHBOARD_HOST || "127.0.0.1";
    const port = validation.values.NYANYA_DASHBOARD_PORT || "8765";
    const checks = [
        { name: "code_root", ok: fs_1.default.existsSync(path_1.default.join(layout.codeRoot, "pyproject.toml")), detail: layout.codeRoot },
        { name: "state_root", ok: fs_1.default.existsSync(layout.stateRoot), detail: layout.stateRoot },
        { name: "node", ok: true, detail: nodeVersion },
        {
            name: "python_3_11_plus",
            ok: (0, python_1.satisfiesPython)(python),
            detail: python ? `${python.command} ${python.versionText}` : "missing"
        },
        { name: "git", ok: git.status === 0, detail: git.status === 0 ? git.stdout.trim() : "missing" },
        { name: "venv", ok: (0, python_1.venvExists)(layout.stateRoot), detail: (0, python_1.venvExists)(layout.stateRoot) ? `${layout.venvRoot} present` : `${layout.venvRoot} missing` },
        { name: "env_file", ok: fs_1.default.existsSync(layout.envPath), detail: fs_1.default.existsSync(layout.envPath) ? layout.envPath : "missing" },
        { name: "config_syntax", ok: validation.errors.length === 0, detail: validation.errors.length ? validation.errors.join("; ") : "ok" },
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
    for (const warning of validation.warnings) {
        console.log(`config_warning=${warning}`);
    }
    console.log(`dashboard_url=http://${host}:${port}`);
    if (args.includes("--backend") && rc === 0) {
        const backend = (0, process_1.run)((0, python_1.pythonCommand)(layout), ["-m", "nyanya_agent.core", "--check"], {
            cwd: layout.codeRoot,
            env: (0, python_1.pythonEnv)(layout)
        });
        process.stdout.write(backend.stdout);
        process.stderr.write(backend.stderr);
        rc = backend.status ?? 1;
    }
    return rc;
}
