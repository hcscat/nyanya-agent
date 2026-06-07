#!/usr/bin/env node
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const python = process.env.PYTHON || "python3";
const env = { ...process.env };
env.PYTHONPATH = env.PYTHONPATH ? `${path.join(root, "src")}${path.delimiter}${env.PYTHONPATH}` : path.join(root, "src");

const result = spawnSync(python, ["-m", "nyanya_agent.core", ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: root,
  env
});
process.exit(result.status ?? 1);
