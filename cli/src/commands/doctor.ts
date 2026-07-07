import fs from "fs";
import path from "path";
import { run } from "../runtime/process";
import { findPython, pythonCommand, pythonEnv, satisfiesPython, venvExists } from "../runtime/python";

type Check = {
  name: string;
  ok: boolean;
  detail: string;
};

function checkImport(projectRoot: string, moduleName: string): Check {
  const result = run(pythonCommand(projectRoot), ["-c", `import ${moduleName}; print("ok")`], {
    cwd: projectRoot,
    env: pythonEnv(projectRoot)
  });
  return {
    name: `python_import_${moduleName}`,
    ok: result.status === 0,
    detail: result.status === 0 ? "ok" : "missing"
  };
}

export function doctor(projectRoot: string): number {
  const python = findPython();
  const nodeVersion = process.version;
  const git = run("git", ["--version"]);
  const envPath = path.join(projectRoot, ".env");
  const checks: Check[] = [
    { name: "project_root", ok: fs.existsSync(path.join(projectRoot, "pyproject.toml")), detail: projectRoot },
    { name: "node", ok: true, detail: nodeVersion },
    {
      name: "python_3_11_plus",
      ok: satisfiesPython(python),
      detail: python ? `${python.command} ${python.versionText}` : "missing"
    },
    { name: "git", ok: git.status === 0, detail: git.status === 0 ? git.stdout.trim() : "missing" },
    { name: "venv", ok: venvExists(projectRoot), detail: venvExists(projectRoot) ? ".venv present" : ".venv missing" },
    { name: "env_file", ok: fs.existsSync(envPath), detail: fs.existsSync(envPath) ? "configured" : "missing" },
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
  return rc;
}
