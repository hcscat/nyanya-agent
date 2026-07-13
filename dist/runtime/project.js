"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.findProjectRoot = findProjectRoot;
exports.expandHome = expandHome;
exports.defaultUserStateRoot = defaultUserStateRoot;
exports.resolveRuntimeLayout = resolveRuntimeLayout;
exports.ensureRuntimeDirectories = ensureRuntimeDirectories;
exports.projectPath = projectPath;
exports.ensureDir = ensureDir;
exports.chmodOwnerOnly = chmodOwnerOnly;
exports.chmodDirOwnerOnly = chmodDirOwnerOnly;
const fs_1 = __importDefault(require("fs"));
const os_1 = __importDefault(require("os"));
const path_1 = __importDefault(require("path"));
function findProjectRoot(startDir = __dirname) {
    const override = process.env.NYANYA_PROJECT_ROOT?.trim();
    if (override) {
        return path_1.default.resolve(expandHome(override));
    }
    let current = path_1.default.resolve(startDir);
    while (true) {
        if (fs_1.default.existsSync(path_1.default.join(current, "pyproject.toml")) &&
            fs_1.default.existsSync(path_1.default.join(current, "src", "nyanya_agent"))) {
            return current;
        }
        const parent = path_1.default.dirname(current);
        if (parent === current) {
            return path_1.default.resolve(process.cwd());
        }
        current = parent;
    }
}
function expandHome(value) {
    if (value === "~") {
        return os_1.default.homedir();
    }
    if (value.startsWith("~/")) {
        return path_1.default.join(os_1.default.homedir(), value.slice(2));
    }
    return value;
}
function defaultUserStateRoot(platform = process.platform, homeDir = os_1.default.homedir(), env = process.env) {
    if (platform === "darwin") {
        return path_1.default.join(homeDir, "Library", "Application Support", "NyaNya Agent");
    }
    if (platform === "win32") {
        return path_1.default.join(env.LOCALAPPDATA || path_1.default.join(homeDir, "AppData", "Local"), "NyaNya Agent");
    }
    return path_1.default.join(env.XDG_DATA_HOME || path_1.default.join(homeDir, ".local", "share"), "nyanya-agent");
}
function resolveRuntimeLayout(projectRoot, env = process.env, platform = process.platform, homeDir = os_1.default.homedir()) {
    const codeRoot = path_1.default.resolve(projectRoot);
    const configuredHome = env.NYANYA_HOME?.trim();
    const legacyEnvPath = path_1.default.join(codeRoot, ".env");
    const legacyState = !configuredHome && fs_1.default.existsSync(legacyEnvPath);
    const stateRoot = configuredHome
        ? path_1.default.resolve(expandHome(configuredHome))
        : legacyState
            ? codeRoot
            : path_1.default.resolve(defaultUserStateRoot(platform, homeDir, env));
    const configuredEnv = env.NYANYA_ENV_FILE?.trim();
    const envPath = configuredEnv
        ? path_1.default.resolve(expandHome(configuredEnv))
        : path_1.default.join(stateRoot, ".env");
    return {
        codeRoot,
        stateRoot,
        envPath,
        venvRoot: path_1.default.join(stateRoot, ".venv"),
        legacyState
    };
}
function ensureRuntimeDirectories(layout) {
    ensureDir(layout.stateRoot);
    chmodDirOwnerOnly(layout.stateRoot);
    for (const name of ["config", "data", "downloads", "logs", "run", "sessions"]) {
        const dir = path_1.default.join(layout.stateRoot, name);
        ensureDir(dir);
        chmodDirOwnerOnly(dir);
    }
}
function projectPath(root, ...parts) {
    return path_1.default.join(root, ...parts);
}
function ensureDir(dir) {
    fs_1.default.mkdirSync(dir, { recursive: true });
}
function chmodOwnerOnly(filePath) {
    if (process.platform !== "win32") {
        fs_1.default.chmodSync(filePath, 0o600);
    }
}
function chmodDirOwnerOnly(dirPath) {
    if (process.platform !== "win32") {
        fs_1.default.chmodSync(dirPath, 0o700);
    }
}
