#!/usr/bin/env node
import { runModule } from "./python-module";

process.exit(runModule("nyanya_agent.discord_bridge", process.argv.slice(2)));
