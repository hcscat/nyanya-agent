"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.service = service;
const python_1 = require("../runtime/python");
const serviceMap = {
    status: "status-all",
    start: "start-all",
    stop: "stop-all",
    restart: "restart-all",
    uninstall: "uninstall-all",
    health: "health",
    "deep-health": "deep-health",
    repair: "repair",
    "stop-all": "stop-all",
    "uninstall-all": "uninstall-all",
    "discord-status": "status",
    "discord-start": "start",
    "discord-stop": "stop",
    "discord-uninstall": "uninstall",
    "discord-restart": "restart",
    "dashboard-status": "dashboard-status",
    "dashboard-start": "dashboard-start",
    "dashboard-stop": "dashboard-stop",
    "dashboard-uninstall": "dashboard-uninstall",
    "dashboard-restart": "dashboard-restart",
    "memory-status": "memory-worker-status",
    "memory-start": "memory-worker-start",
    "memory-stop": "memory-worker-stop",
    "memory-uninstall": "memory-worker-uninstall",
    "memory-restart": "memory-worker-restart"
};
function service(projectRoot, args) {
    const command = args[0] || "status";
    const managerCommand = serviceMap[command];
    if (!managerCommand) {
        console.error(`Unknown service command: ${command}`);
        console.error(`Available: ${Object.keys(serviceMap).sort().join(", ")}`);
        return 2;
    }
    return (0, python_1.runPythonModule)(projectRoot, "nyanya_agent.manager", [managerCommand, ...args.slice(1)]);
}
