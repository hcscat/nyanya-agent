"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.state = state;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const project_1 = require("../runtime/project");
const DURABLE_ITEMS = [".env", "config", "data", "sessions"];
const MIGRATION_ITEMS = [...DURABLE_ITEMS, "downloads", "logs"];
function timestamp() {
    return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}
function isNonEmptyDirectory(directory) {
    return fs_1.default.existsSync(directory) && fs_1.default.statSync(directory).isDirectory() && fs_1.default.readdirSync(directory).length > 0;
}
function copyItems(sourceRoot, targetRoot, items) {
    (0, project_1.ensureDir)(targetRoot);
    (0, project_1.chmodDirOwnerOnly)(targetRoot);
    const copied = [];
    for (const item of items) {
        const source = path_1.default.join(sourceRoot, item);
        if (!fs_1.default.existsSync(source)) {
            continue;
        }
        const target = path_1.default.join(targetRoot, item);
        fs_1.default.cpSync(source, target, { recursive: true, errorOnExist: true, force: false });
        copied.push(item);
    }
    const envPath = path_1.default.join(targetRoot, ".env");
    if (fs_1.default.existsSync(envPath)) {
        (0, project_1.chmodOwnerOnly)(envPath);
    }
    return copied;
}
function backup(layout, args) {
    const targetArg = args.find((arg) => arg.startsWith("--to="))?.slice("--to=".length);
    const target = path_1.default.resolve(targetArg || path_1.default.join(path_1.default.dirname(layout.stateRoot), "NyaNya Agent Backups", timestamp()));
    if (fs_1.default.existsSync(target)) {
        console.error(`backup_error=target already exists: ${target}`);
        return 1;
    }
    const copied = copyItems(layout.stateRoot, target, DURABLE_ITEMS);
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
    const copied = copyItems(layout.stateRoot, target, MIGRATION_ITEMS);
    console.log(`migration_source=${layout.stateRoot}`);
    console.log(`migration_target=${target}`);
    console.log(`migration_items=${copied.join(",")}`);
    console.log("migration_excluded=.venv,run");
    console.log(`next=NYANYA_HOME="${target}" nyanya setup --non-interactive`);
    return 0;
}
function state(projectRoot, args) {
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
