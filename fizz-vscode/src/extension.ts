import * as path from "path";
import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions, TransportKind } from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let output: vscode.OutputChannel | undefined;

function resolveUnder(root: string, ...parts: string[]): string {
  const resolvedRoot = path.resolve(root);
  const p = path.resolve(resolvedRoot, ...parts);
  if (!p.startsWith(resolvedRoot + path.sep) && p !== resolvedRoot) {
    throw new Error(`Path escapes root: ${p}`);
  }
  return p;
}

async function copyDir(src: string, dst: string): Promise<void> {
  await vscode.workspace.fs.createDirectory(vscode.Uri.file(dst));
  const entries = await vscode.workspace.fs.readDirectory(vscode.Uri.file(src));
  const skipNames = new Set<string>([".venv", "__pycache__", ".pytest_cache"]);
  await Promise.all(
    entries.map(async ([name, type]) => {
      if (skipNames.has(name)) {
        return;
      }
      const s = path.join(src, name);
      const d = path.join(dst, name);
      if (type === vscode.FileType.Directory) {
        await copyDir(s, d);
      } else if (type === vscode.FileType.File) {
        await vscode.workspace.fs.copy(vscode.Uri.file(s), vscode.Uri.file(d), { overwrite: true });
      }
    })
  );
}

async function ensureServerProject(context: vscode.ExtensionContext): Promise<string> {
  const srcServerDir = resolveUnder(context.extensionPath, "server");
  const dstServerDir = resolveUnder(context.globalStorageUri.fsPath, "server");
  const markerPath = resolveUnder(dstServerDir, ".installed-version");

  const version = context.extension.packageJSON?.version ?? "0.0.0";
  let installedVersion: string | undefined;
  try {
    const bytes = await vscode.workspace.fs.readFile(vscode.Uri.file(markerPath));
    installedVersion = Buffer.from(bytes).toString("utf8").trim();
  } catch {
    installedVersion = undefined;
  }

  let dstExists = true;
  try {
    await vscode.workspace.fs.stat(vscode.Uri.file(dstServerDir));
  } catch {
    dstExists = false;
  }

  if (!dstExists || installedVersion !== version) {
    await vscode.workspace.fs.createDirectory(context.globalStorageUri);
    // Fresh copy (small): ensures uv can create a venv next to pyproject.toml.
    await copyDir(srcServerDir, dstServerDir);
    await vscode.workspace.fs.writeFile(vscode.Uri.file(markerPath), Buffer.from(`${version}\n`, "utf8"));
  }

  return dstServerDir;
}

export async function deactivate() {
  if (client) {
    await client.stop();
    client = undefined;
  }
  if (output) {
    output.dispose();
    output = undefined;
  }
}

export async function activate(context: vscode.ExtensionContext) {
  output = vscode.window.createOutputChannel("FizzBee Fizz");
  output.appendLine(`[ext] activating fizzbee-fizz v${context.extension.packageJSON?.version ?? "?"}`);

  if (process.env.FIZZ_LSP_DISABLE === "1") {
    output.appendLine("[ext] FIZZ_LSP_DISABLE=1; skipping LSP startup");
    return;
  }

  const serverDir = await ensureServerProject(context);
  output.appendLine(`[ext] serverDir=${serverDir}`);

  const serverOptions: ServerOptions = {
    command: "uv",
    args: ["run", "--directory", serverDir, "--frozen", "--no-dev", "-m", "fizz_lsp"],
    options: {
      cwd: serverDir,
      env: {
        ...process.env,
        UV_NO_PROGRESS: "1"
      }
    },
    transport: TransportKind.stdio
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ language: "fizz" }],
    outputChannel: output,
    traceOutputChannel: output,
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.fizz")
    }
  };

  client = new LanguageClient("fizzbee-fizz", "Fizz Language Server", serverOptions, clientOptions);
  void client.start();
  context.subscriptions.push({
    dispose: () => {
      void client?.stop();
    }
  });

  client.onDidChangeState((e) => {
    output?.appendLine(`[lsp] state=${e.newState}`);
  });
}

