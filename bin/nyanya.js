#!/usr/bin/env node
const { main } = require("../dist/bin/nyanya.js");

process.exit(main(process.argv.slice(2)));
