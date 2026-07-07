import { runPythonModule } from "../runtime/python";

const serviceMap: Record<string, string> = {
  status: "status-all",
  start: "start-all",
  restart: "restart-all",
  health: "health",
  "deep-health": "deep-health",
  repair: "repair",
  "discord-status": "status",
  "discord-start": "start",
  "discord-stop": "stop",
  "discord-restart": "restart",
  "dashboard-status": "dashboard-status",
  "dashboard-start": "dashboard-start",
  "dashboard-stop": "dashboard-stop",
  "dashboard-restart": "dashboard-restart",
  "memory-status": "memory-worker-status",
  "memory-start": "memory-worker-start",
  "memory-stop": "memory-worker-stop",
  "memory-restart": "memory-worker-restart"
};

export function service(projectRoot: string, args: string[]): number {
  const command = args[0] || "status";
  const managerCommand = serviceMap[command];
  if (!managerCommand) {
    console.error(`Unknown service command: ${command}`);
    console.error(`Available: ${Object.keys(serviceMap).sort().join(", ")}`);
    return 2;
  }
  return runPythonModule(projectRoot, "nyanya_agent.manager", [managerCommand, ...args.slice(1)]);
}
