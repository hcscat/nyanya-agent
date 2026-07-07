"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runModule = runModule;
const project_1 = require("../runtime/project");
const python_1 = require("../runtime/python");
function runModule(moduleName, argv) {
    return (0, python_1.runPythonModule)((0, project_1.findProjectRoot)(__dirname), moduleName, argv);
}
