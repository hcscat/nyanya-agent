"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.run = run;
exports.runInherit = runInherit;
exports.printCaptured = printCaptured;
const child_process_1 = require("child_process");
function run(command, args, options = {}) {
    return (0, child_process_1.spawnSync)(command, args, {
        cwd: options.cwd,
        env: options.env ?? process.env,
        encoding: "utf8",
        stdio: "pipe"
    });
}
function runInherit(command, args, options = {}) {
    const result = (0, child_process_1.spawnSync)(command, args, {
        cwd: options.cwd,
        env: options.env ?? process.env,
        stdio: "inherit"
    });
    if (result.error) {
        console.error(`${command}: ${result.error.message}`);
        return 1;
    }
    return result.status ?? 1;
}
function printCaptured(result) {
    if (result.stdout) {
        process.stdout.write(result.stdout);
    }
    if (result.stderr) {
        process.stderr.write(result.stderr);
    }
}
