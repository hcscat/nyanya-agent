#!/usr/bin/env node
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const python_module_1 = require("./python-module");
process.exit((0, python_module_1.runModule)("nyanya_agent.dashboard_api", process.argv.slice(2)));
