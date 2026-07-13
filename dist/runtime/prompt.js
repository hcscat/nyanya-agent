"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.interactiveAvailable = interactiveAvailable;
exports.ask = ask;
exports.confirm = confirm;
exports.choose = choose;
const fs_1 = __importDefault(require("fs"));
const promptWaitBuffer = new Int32Array(new SharedArrayBuffer(4));
function canPrompt() {
    return Boolean(process.stdin.isTTY && process.stdout.isTTY);
}
function interactiveAvailable() {
    return canPrompt();
}
function ask(prompt, defaultValue = "", secret = false) {
    if (!canPrompt()) {
        return defaultValue;
    }
    process.stdout.write(`${prompt}${defaultValue && !secret ? ` [${defaultValue}]` : ""}: `);
    const stdin = process.stdin;
    const wasRaw = stdin.isRaw;
    stdin.setRawMode?.(true);
    stdin.resume();
    const bytes = [];
    const buffer = Buffer.alloc(1);
    try {
        while (true) {
            let count;
            try {
                count = fs_1.default.readSync(stdin.fd, buffer, 0, 1, null);
            }
            catch (error) {
                const code = error.code;
                if (code === "EAGAIN" || code === "EWOULDBLOCK") {
                    Atomics.wait(promptWaitBuffer, 0, 0, 25);
                    continue;
                }
                throw error;
            }
            if (count === 0) {
                break;
            }
            const code = buffer[0];
            if (code === 3) {
                throw new Error("Interactive configuration cancelled");
            }
            if (code === 13 || code === 10) {
                process.stdout.write("\n");
                break;
            }
            if (code === 127 || code === 8) {
                if (bytes.length > 0) {
                    let removed = bytes.pop();
                    while (removed !== undefined && (removed & 0xc0) === 0x80) {
                        removed = bytes.pop();
                    }
                    process.stdout.write("\b \b");
                }
                continue;
            }
            if (code < 32) {
                continue;
            }
            bytes.push(code);
            process.stdout.write(secret ? "*" : buffer.subarray(0, count));
        }
    }
    finally {
        stdin.setRawMode?.(Boolean(wasRaw));
        stdin.pause();
    }
    return Buffer.from(bytes).toString("utf8") || defaultValue;
}
function confirm(prompt, defaultYes = true) {
    const suffix = defaultYes ? "Y/n" : "y/N";
    const answer = ask(`${prompt} (${suffix})`).trim().toLowerCase();
    if (!answer) {
        return defaultYes;
    }
    return ["y", "yes", "1", "true"].includes(answer);
}
function choose(prompt, choices, defaultIndex = 0) {
    console.log(prompt);
    choices.forEach((choice, index) => console.log(`  ${index + 1}. ${choice}`));
    const raw = ask("Select", String(defaultIndex + 1));
    const index = Number.parseInt(raw, 10) - 1;
    return Number.isInteger(index) && index >= 0 && index < choices.length ? index : defaultIndex;
}
