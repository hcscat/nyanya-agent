"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.logs = logs;
const path_1 = __importDefault(require("path"));
const process_1 = require("../runtime/process");
const project_1 = require("../runtime/project");
const python_1 = require("../runtime/python");
function logs(projectRoot, args) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    const env = {};
    for (const key of ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR"]) {
        if (process.env[key] !== undefined)
            env[key] = process.env[key];
    }
    Object.assign(env, {
        NYANYA_PROJECT_ROOT: layout.codeRoot,
        NYANYA_HOME: layout.stateRoot,
        NYANYA_ENV_FILE: layout.envPath,
        PYTHONPATH: path_1.default.join(layout.codeRoot, "src"),
        PYTHONNOUSERSITE: "1"
    });
    // Python rejects a database outside this state root, including stale overrides.
    if (process.env.NYANYA_DASHBOARD_DB_PATH) {
        env.NYANYA_DASHBOARD_DB_PATH = process.env.NYANYA_DASHBOARD_DB_PATH;
    }
    return (0, process_1.runInherit)((0, python_1.pythonCommand)(layout), ["-m", "nyanya_agent.log_maintenance", ...args], {
        cwd: layout.codeRoot, env
    });
}
