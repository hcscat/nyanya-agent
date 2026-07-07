import { findProjectRoot } from "../runtime/project";
import { runPythonModule } from "../runtime/python";

export function runModule(moduleName: string, argv: string[]): number {
  return runPythonModule(findProjectRoot(__dirname), moduleName, argv);
}
