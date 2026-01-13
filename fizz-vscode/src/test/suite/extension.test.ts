import * as assert from "assert";
import * as fs from "fs/promises";
import * as os from "os";
import * as path from "path";

import * as vscode from "vscode";

suite("Fizz extension smoke tests", () => {
  test("opens .fizz file with fizz language id", async () => {
    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "fizz-vscode-test-"));
    const filePath = path.join(tmpDir, "Sample.fizz");
    await fs.writeFile(
      filePath,
      [
        "init:",
        "  a = 0",
        "",
        "action Add:",
        "  atomic:",
        "    a = a + 1",
        ""
      ].join("\n"),
      "utf8"
    );

    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(filePath));
    await vscode.window.showTextDocument(doc);

    assert.strictEqual(doc.languageId, "fizz");
  });
});

