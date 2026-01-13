import * as assert from "assert";
import * as fs from "fs/promises";
import * as os from "os";
import * as path from "path";

import * as vscode from "vscode";

async function waitFor<T>(
  fn: () => Promise<T> | T,
  predicate: (v: T) => boolean,
  timeoutMs: number,
  intervalMs: number
): Promise<T> {
  const start = Date.now();
  while (true) {
    const v = await fn();
    if (predicate(v)) return v;
    if (Date.now() - start > timeoutMs) {
      throw new Error("timeout waiting for condition");
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

suite("Fizz LSP smoke tests (uv + python)", function () {
  // uv boot on first run can take a while.
  this.timeout(180_000);

  test("publishes diagnostics and supports document symbols / go-to-definition", async function () {
    if (process.env.FIZZ_LSP_DISABLE === "1") {
      this.skip();
    }

    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "fizz-vscode-lsp-test-"));
    const filePath = path.join(tmpDir, "Roles.fizz");
    const text = [
      "role Participant:",
      "  atomic func Prepare():",
      "    return 1",
      "",
      "action Init:",
      "  participants = []",
      "  p = Participant()",
      "  participants.append(p)",
      "  for rm in participants:",
      "    rm.Prepare()",
      "",
      "action Broken:",
      "  atomic:",
      "    if:", // invalid
      "      pass",
      ""
    ].join("\n");
    await fs.writeFile(filePath, text, "utf8");

    const uri = vscode.Uri.file(filePath);
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);

    // Diagnostics: wait until we see at least one error.
    await waitFor(
      () => vscode.languages.getDiagnostics(uri),
      (d) => d.length > 0,
      120_000,
      250
    );

    // Document symbols should include Participant.
    const symbols = (await vscode.commands.executeCommand(
      "vscode.executeDocumentSymbolProvider",
      uri
    )) as vscode.DocumentSymbol[] | undefined;
    assert.ok(symbols && symbols.some((s) => s.name === "Participant"));

    // Go-to-definition from rm.Prepare should land on Prepare definition.
    const callLine = 9; // 0-based; line with "rm.Prepare()"
    const callChar = "    rm.".length; // position on "Prepare"
    const defs = (await vscode.commands.executeCommand(
      "vscode.executeDefinitionProvider",
      uri,
      new vscode.Position(callLine, callChar)
    )) as vscode.Location[] | undefined;
    assert.ok(defs && defs.length >= 1);
    const first = defs?.[0];
    assert.ok(first);
    assert.strictEqual(first.uri.fsPath, uri.fsPath);
    assert.strictEqual(first.range.start.line, 1); // line with func Prepare
  });
});

