"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.state = state;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const process_1 = require("../runtime/process");
const python_1 = require("../runtime/python");
const project_1 = require("../runtime/project");
const DURABLE_ITEMS = [".env", "config", "data", "sessions"];
const MIGRATION_ITEMS = [...DURABLE_ITEMS, "downloads", "logs"];
function timestamp() {
    return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}
function isNonEmptyDirectory(directory) {
    return fs_1.default.existsSync(directory) && fs_1.default.statSync(directory).isDirectory() && fs_1.default.readdirSync(directory).length > 0;
}
function canonicalDestination(value) {
    const full = path_1.default.resolve(value);
    if (fs_1.default.existsSync(full))
        return fs_1.default.realpathSync(full);
    const parent = path_1.default.dirname(full);
    return path_1.default.join(canonicalDestination(parent), path_1.default.basename(full));
}
function copyItems(sourceRoot, targetRoot, items, layout) {
    const relative = path_1.default.relative(fs_1.default.realpathSync(sourceRoot), canonicalDestination(targetRoot));
    if (!relative || (!relative.startsWith(`..${path_1.default.sep}`) && relative !== ".." && !path_1.default.isAbsolute(relative))) {
        throw new Error("State copy destination must be outside the source state directory");
    }
    (0, project_1.ensureDir)(targetRoot);
    (0, project_1.chmodDirOwnerOnly)(targetRoot);
    const copied = [];
    for (const item of items) {
        const source = path_1.default.join(sourceRoot, item);
        if (!fs_1.default.existsSync(source)) {
            continue;
        }
        const target = path_1.default.join(targetRoot, item);
        copyStateEntry(source, target, layout);
        copied.push(item);
    }
    const envPath = path_1.default.join(targetRoot, ".env");
    if (fs_1.default.existsSync(envPath)) {
        (0, project_1.chmodOwnerOnly)(envPath);
    }
    return copied;
}
function copyStateEntry(source, target, layout) {
    const stat = fs_1.default.lstatSync(source);
    if (stat.isSymbolicLink())
        throw new Error("State backup refuses symlinks");
    if (stat.isDirectory()) {
        fs_1.default.mkdirSync(target, { mode: 0o700 });
        for (const name of fs_1.default.readdirSync(source)) {
            if (name.endsWith("-wal") || name.endsWith("-shm"))
                continue;
            copyStateEntry(path_1.default.join(source, name), path_1.default.join(target, name), layout);
        }
    }
    else if (stat.isFile()) {
        if (/\.(db|sqlite|sqlite3)$/i.test(source)) {
            const result = (0, process_1.run)((0, python_1.pythonCommand)(layout), ["-m", "nyanya_agent.state_backup", source, target], {
                cwd: layout.codeRoot, env: (0, python_1.pythonEnv)(layout)
            });
            if (result.status !== 0)
                throw new Error("Consistent database backup failed; source state was preserved");
        }
        else {
            fs_1.default.copyFileSync(source, target, fs_1.default.constants.COPYFILE_EXCL);
            (0, project_1.chmodOwnerOnly)(target);
        }
    }
    else {
        throw new Error("State backup refuses special files");
    }
}
function backup(layout, args) {
    const targetArg = args.find((arg) => arg.startsWith("--to="))?.slice("--to=".length);
    const target = path_1.default.resolve(targetArg || path_1.default.join(path_1.default.dirname(layout.stateRoot), "NyaNya Agent Backups", timestamp()));
    if (fs_1.default.existsSync(target)) {
        console.error(`backup_error=target already exists: ${target}`);
        return 1;
    }
    const copied = copyItems(layout.stateRoot, target, DURABLE_ITEMS, layout);
    console.log(`backup_root=${target}`);
    console.log(`backup_items=${copied.join(",")}`);
    console.log("backup_excluded=.venv,run,logs,downloads");
    return 0;
}
function migrate(layout, args) {
    const targetArg = args.find((arg) => arg.startsWith("--to="))?.slice("--to=".length);
    const target = path_1.default.resolve(targetArg || (0, project_1.defaultUserStateRoot)());
    if (path_1.default.resolve(layout.stateRoot) === target) {
        console.log(`state_root=${target}`);
        console.log("migration_needed=false");
        return 0;
    }
    if (isNonEmptyDirectory(target)) {
        console.error(`migration_error=target is not empty: ${target}`);
        return 1;
    }
    const copied = copyItems(layout.stateRoot, target, MIGRATION_ITEMS, layout);
    console.log(`migration_source=${layout.stateRoot}`);
    console.log(`migration_target=${target}`);
    console.log(`migration_items=${copied.join(",")}`);
    console.log("migration_excluded=.venv,run");
    console.log(`next=NYANYA_HOME="${target}" nyanya setup --non-interactive`);
    return 0;
}
function stateCommand(projectRoot, args) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    const command = args[0] || "show";
    if (command === "show") {
        console.log(`code_root=${layout.codeRoot}`);
        console.log(`state_root=${layout.stateRoot}`);
        console.log(`state_mode=${layout.legacyState ? "legacy-source" : "user"}`);
        return 0;
    }
    if (command === "backup") {
        return backup(layout, args.slice(1));
    }
    if (command === "migrate") {
        return migrate(layout, args.slice(1));
    }
    console.error(`Unknown state command: ${command}`);
    console.error("Available: show, backup, migrate");
    return 2;
}
function state(projectRoot, args) {
    try {
        return stateCommand(projectRoot, args);
    }
    catch (error) {
        console.error(error instanceof Error ? error.message : "State operation failed");
        return 1;
    }
}
