import fs from "fs";
import path from "path";
import { run } from "../runtime/process";
import { readEnvFile } from "../runtime/env-file";
import { resolveRuntimeLayout } from "../runtime/project";
import { findPython, pythonCommand, pythonEnv, satisfiesPython, venvExists } from "../runtime/python";

type Check = {
  name: string;
  ok: boolean;
  detail: string;
};

function checkImport(projectRoot: string, moduleName: string): Check {
  const layout = resolveRuntimeLayout(projectRoot);
  const result = run(pythonCommand(layout), ["-c", `import ${moduleName}; print("ok")`], {
    cwd: layout.codeRoot,
    env: pythonEnv(layout)
  });
  return {
    name: `python_import_${moduleName}`,
    ok: result.status === 0,
    detail: result.status === 0 ? "ok" : "missing"
  };
}

export function doctor(projectRoot: string, args: string[] = []): number {
  const layout = resolveRuntimeLayout(projectRoot);
  const python = findPython();
  const nodeVersion = process.version;
  const git = run("git", ["--version"]);
  const validation = readEnvFile(layout.envPath);
  const host = validation.values.NYANYA_DASHBOARD_HOST || "127.0.0.1";
  const port = validation.values.NYANYA_DASHBOARD_PORT || "8765";
  const checks: Check[] = [
    { name: "code_root", ok: fs.existsSync(path.join(layout.codeRoot, "pyproject.toml")), detail: layout.codeRoot },
    { name: "state_root", ok: fs.existsSync(layout.stateRoot), detail: layout.stateRoot },
    { name: "node", ok: true, detail: nodeVersion },
    {
      name: "python_3_11_plus",
      ok: satisfiesPython(python),
      detail: python ? `${python.command} ${python.versionText}` : "missing"
    },
    { name: "git", ok: git.status === 0, detail: git.status === 0 ? git.stdout.trim() : "missing" },
    { name: "venv", ok: venvExists(layout.stateRoot), detail: venvExists(layout.stateRoot) ? `${layout.venvRoot} present` : `${layout.venvRoot} missing` },
    { name: "env_file", ok: fs.existsSync(layout.envPath), detail: fs.existsSync(layout.envPath) ? layout.envPath : "missing" },
    { name: "config_syntax", ok: validation.errors.length === 0, detail: validation.errors.length ? validation.errors.join("; ") : "ok" },
    checkImport(projectRoot, "nyanya_agent.core"),
    checkImport(projectRoot, "discord"),
    checkImport(projectRoot, "fastapi"),
    checkImport(projectRoot, "uvicorn")
  ];

  let rc = 0;
  for (const check of checks) {
    const status = check.ok ? "ok" : "fail";
    console.log(`${check.name}=${status} detail=${check.detail}`);
    if (!check.ok && check.name !== "git") {
      rc = 1;
    }
  }
  for (const warning of validation.warnings) {
    console.log(`config_warning=${warning}`);
  }
  console.log(`dashboard_url=http://${host}:${port}`);
  if (args.includes("--backend") && rc === 0) {
    const backend = run(pythonCommand(layout), ["-m", "nyanya_agent.core", "--check"], {
      cwd: layout.codeRoot,
      env: pythonEnv(layout)
    });
    process.stdout.write(backend.stdout);
    process.stderr.write(backend.stderr);
    rc = backend.status ?? 1;
  }
  return rc;
}
