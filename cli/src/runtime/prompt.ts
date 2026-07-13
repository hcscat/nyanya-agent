import fs from "fs";

const promptWaitBuffer = new Int32Array(new SharedArrayBuffer(4));

function canPrompt(): boolean {
  return Boolean(process.stdin.isTTY && process.stdout.isTTY);
}

export function interactiveAvailable(): boolean {
  return canPrompt();
}

export function ask(prompt: string, defaultValue = "", secret = false): string {
  if (!canPrompt()) {
    return defaultValue;
  }
  process.stdout.write(`${prompt}${defaultValue && !secret ? ` [${defaultValue}]` : ""}: `);
  const stdin = process.stdin;
  const wasRaw = stdin.isRaw;
  stdin.setRawMode?.(true);
  stdin.resume();
  const bytes: number[] = [];
  const buffer = Buffer.alloc(1);
  try {
    while (true) {
      let count: number;
      try {
        count = fs.readSync(stdin.fd, buffer, 0, 1, null);
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code;
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
  } finally {
    stdin.setRawMode?.(Boolean(wasRaw));
    stdin.pause();
  }
  return Buffer.from(bytes).toString("utf8") || defaultValue;
}

export function confirm(prompt: string, defaultYes = true): boolean {
  const suffix = defaultYes ? "Y/n" : "y/N";
  const answer = ask(`${prompt} (${suffix})`).trim().toLowerCase();
  if (!answer) {
    return defaultYes;
  }
  return ["y", "yes", "1", "true"].includes(answer);
}

export function choose(prompt: string, choices: string[], defaultIndex = 0): number {
  console.log(prompt);
  choices.forEach((choice, index) => console.log(`  ${index + 1}. ${choice}`));
  const raw = ask("Select", String(defaultIndex + 1));
  const index = Number.parseInt(raw, 10) - 1;
  return Number.isInteger(index) && index >= 0 && index < choices.length ? index : defaultIndex;
}
