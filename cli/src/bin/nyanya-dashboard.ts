#!/usr/bin/env node
import { runModule } from "./python-module";

process.exit(runModule("nyanya_agent.dashboard_api", process.argv.slice(2)));
