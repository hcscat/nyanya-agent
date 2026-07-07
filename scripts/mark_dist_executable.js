#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const binDir = path.resolve(__dirname, "..", "dist", "bin");
if (!fs.existsSync(binDir)) {
  process.exit(0);
}

for (const name of fs.readdirSync(binDir)) {
  if (name.endsWith(".js")) {
    fs.chmodSync(path.join(binDir, name), 0o755);
  }
}
