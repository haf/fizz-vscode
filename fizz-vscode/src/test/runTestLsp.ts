import * as path from "path";

import { runTests } from "@vscode/test-electron";

async function main() {
  try {
    const extensionDevelopmentPath = path.resolve(__dirname, "../../");
    const extensionTestsPath = path.resolve(__dirname, "./suite/index");

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
      // Keep LSP enabled for this run; tests will wait for uv boot.
      extensionTestsEnv: {
        FIZZ_LSP_DISABLE: "0"
      }
    });
  } catch (err) {
    console.error("Failed to run tests", err);
    process.exit(1);
  }
}

void main();

