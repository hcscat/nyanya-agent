import fs from "fs";
import os from "os";
import path from "path";

export type RuntimeLayout = {
  codeRoot: string;
  stateRoot: string;
  envPath: string;
  venvRoot: string;
  legacyState: boolean;
};

export function findProjectRoot(startDir: string = __dirname): string {
  const override = process.env.NYANYA_PROJECT_ROOT?.trim();
  if (override) {
    return path.resolve(expandHome(override));
  }

  let current = path.resolve(startDir);
  while (true) {
    if (
      fs.existsSync(path.join(current, "pyproject.toml")) &&
      fs.existsSync(path.join(current, "src", "nyanya_agent"))
    ) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return path.resolve(process.cwd());
    }
    current = parent;
  }
}

export function expandHome(value: string): string {
  if (value === "~") {
    return os.homedir();
  }
  if (value.startsWith("~/")) {
    return path.join(os.homedir(), value.slice(2));
  }
  return value;
}

export function defaultUserStateRoot(
  platform: NodeJS.Platform = process.platform,
  homeDir: string = os.homedir(),
  env: NodeJS.ProcessEnv = process.env
): string {
  if (platform === "darwin") {
    return path.join(homeDir, "Library", "Application Support", "NyaNya Agent");
  }
  if (platform === "win32") {
    return path.join(env.LOCALAPPDATA || path.join(homeDir, "AppData", "Local"), "NyaNya Agent");
  }
  return path.join(env.XDG_DATA_HOME || path.join(homeDir, ".local", "share"), "nyanya-agent");
}

export function resolveRuntimeLayout(
  projectRoot: string,
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
  homeDir: string = os.homedir()
): RuntimeLayout {
  const codeRoot = path.resolve(projectRoot);
  const configuredHome = env.NYANYA_HOME?.trim();
  const legacyEnvPath = path.join(codeRoot, ".env");
  const legacyState = !configuredHome && fs.existsSync(legacyEnvPath);
  const stateRoot = configuredHome
    ? path.resolve(expandHome(configuredHome))
    : legacyState
      ? codeRoot
      : path.resolve(defaultUserStateRoot(platform, homeDir, env));
  const configuredEnv = env.NYANYA_ENV_FILE?.trim();
  const envPath = configuredEnv
    ? path.resolve(expandHome(configuredEnv))
    : path.join(stateRoot, ".env");
  return {
    codeRoot,
    stateRoot,
    envPath,
    venvRoot: path.join(stateRoot, ".venv"),
    legacyState
  };
}

export function ensureRuntimeDirectories(layout: RuntimeLayout): void {
  ensureDir(layout.stateRoot);
  chmodDirOwnerOnly(layout.stateRoot);
  for (const name of ["config", "data", "downloads", "logs", "run", "sessions"]) {
    const dir = path.join(layout.stateRoot, name);
    ensureDir(dir);
    chmodDirOwnerOnly(dir);
  }
}

export function projectPath(root: string, ...parts: string[]): string {
  return path.join(root, ...parts);
}

export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

export function chmodOwnerOnly(filePath: string): void {
  if (process.platform !== "win32") {
    fs.chmodSync(filePath, 0o600);
  }
}

export function chmodDirOwnerOnly(dirPath: string): void {
  if (process.platform !== "win32") {
    fs.chmodSync(dirPath, 0o700);
  }
}
