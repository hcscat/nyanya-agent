#!/usr/bin/env node
import { runModule } from "./python-module";

process.exit(runModule("nyanya_agent.memory_worker", process.argv.slice(2)));
