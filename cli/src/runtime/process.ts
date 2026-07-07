import { spawnSync, SpawnSyncReturns } from "child_process";

export type CommandResult = SpawnSyncReturns<string>;

export function run(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv } = {}): CommandResult {
  return spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env ?? process.env,
    encoding: "utf8",
    stdio: "pipe"
  });
}

export function runInherit(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv } = {}): number {
  const result = spawnSync(command, args, {
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

export function printCaptured(result: CommandResult): void {
  if (result.stdout) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr) {
    process.stderr.write(result.stderr);
  }
}
