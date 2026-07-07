#!/usr/bin/env node
import { runModule } from "./python-module";

process.exit(runModule("nyanya_agent.manager", process.argv.slice(2)));
