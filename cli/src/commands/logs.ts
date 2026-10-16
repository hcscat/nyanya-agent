import path from "path";
import { runInherit } from "../runtime/process";
import { resolveRuntimeLayout } from "../runtime/project";
import { pythonCommand } from "../runtime/python";

export function logs(projectRoot: string, args: string[]): number {
  const layout = resolveRuntimeLayout(projectRoot);
  const env: NodeJS.ProcessEnv = {};
  for (const key of ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR"]) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  Object.assign(env, {
    NYANYA_PROJECT_ROOT: layout.codeRoot,
    NYANYA_HOME: layout.stateRoot,
    NYANYA_ENV_FILE: layout.envPath,
    PYTHONPATH: path.join(layout.codeRoot, "src"),
    PYTHONNOUSERSITE: "1"
  });
  // Python rejects a database outside this state root, including stale overrides.
  if (process.env.NYANYA_DASHBOARD_DB_PATH) {
    env.NYANYA_DASHBOARD_DB_PATH = process.env.NYANYA_DASHBOARD_DB_PATH;
  }
  return runInherit(pythonCommand(layout), ["-m", "nyanya_agent.log_maintenance", ...args], {
    cwd: layout.codeRoot, env
  });
}
