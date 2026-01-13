# Fizz VS Code / Cursor Extension

This folder contains a self-contained VS Code extension for `.fizz` files:

- **Syntax highlighting** via a TextMate grammar
- **Language Server** (Python) launched via `uv` for:
  - diagnostics
  - document symbols
  - go-to-definition
  - hover
  - completions
  - semantic tokens (definitions + call sites)

## How it works (need-to-know)

- **Client (TypeScript)** lives in `src/extension.ts`.
- **Server (Python)** lives in `server/` and is started with:

```bash
uv run --directory <serverDir> --frozen --no-dev -m fizz_lsp
```

- The extension copies `server/` into VS Code **global storage** (per-user) before launching `uv`.
  - Reason: installed extensions are often read-only; `uv` needs to create a venv alongside `pyproject.toml`.
  - Copy is versioned via a `.installed-version` marker.

## Requirements

- **Node + npm** (for building / packaging the extension)
- **`uv` on PATH** (the extension uses this to provision + run the Python server)
- Internet access is typically needed the **first** time `uv` resolves / installs deps (cached afterward).

## Dev workflow

From this directory:

```bash
npm install
npm test          # fast tests (LSP disabled)
npm run test:lsp  # end-to-end tests (starts LSP via uv)
```

To run the extension interactively:

- Open this folder in VS Code/Cursor
- Press **F5** (Extension Development Host)

## Install it yourself (local)

You have two practical options.

### Option A: Run from source (best for development)

- Open `/Users/h/dev/fizzbee/fizz-vscode` in VS Code/Cursor
- Press **F5** to launch an **Extension Development Host**

### Option B: Build a VSIX and install it (best for “I want to use it”)

1) Build the VSIX:

```bash
cd /Users/h/dev/fizzbee/fizz-vscode
npm install
npm run compile
npm run package
```

This produces something like `fizzbee-fizz-0.0.1.vsix`.

2) Install the VSIX:

- In VS Code/Cursor: Command Palette → **Extensions: Install from VSIX...**
- Or CLI (VS Code):

```bash
code --install-extension ./fizzbee-fizz-0.0.1.vsix
```

## Publish it

Publishing depends on which registry your editor uses.

### Publish to VS Code Marketplace (Microsoft)

1) **Pick a real publisher name** and update `package.json`:
   - `publisher`: change from `"local"` to your publisher ID
   - (Optional but recommended) add `repository`, `homepage`, `bugs`, `license`, `icon`

2) Create a publisher + token in Azure DevOps (Marketplace publishing flow).

3) Publish:

```bash
cd /Users/h/dev/fizzbee/fizz-vscode
npm install
npm run compile
npx @vscode/vsce publish
```

If you need to publish a specific version:

```bash
npx @vscode/vsce publish patch   # or minor/major
```

### Publish to Open VSX (commonly used by non-MS editors)

Some VS Code forks (and sometimes Cursor setups) prefer Open VSX.

1) Create an Open VSX account and token.
2) Publish:

```bash
cd /Users/h/dev/fizzbee/fizz-vscode
npm install
npm run compile
npx ovsx publish -p "$OPEN_VSX_TOKEN"
```

If Cursor doesn’t show Marketplace results, VSIX install (above) is the reliable path.

## Python server

The server lives in [`server/`](server/). It vendors the Fizz ANTLR parser from
`vendor/fizzbee/parser/` and is managed with:

```bash
cd server
uv lock
uv run --group dev python -m pytest
```

### Updating the vendored parser

The server currently vendors these files from `vendor/fizzbee/parser/`:

- `FizzLexer.py`, `FizzParser.py`, `FizzParserVisitor.py`
- `PythonLexerBase.py`, `PythonParserBase.py`

When upstream changes, re-copy those into `server/fizz_lsp/fizz_parser/` and re-run:

```bash
cd /Users/h/dev/fizzbee/fizz-vscode/server
uv lock
uv run --group dev python -m pytest
```

### Test commands (recap)

Extension tests:

```bash
cd /Users/h/dev/fizzbee/fizz-vscode
npm test          # LSP disabled (fast)
npm run test:lsp  # LSP enabled (uv + python)
```

Server tests (includes parsing `vendor/fizzbee/examples/**/*.fizz`):

```bash
cd /Users/h/dev/fizzbee/fizz-vscode/server
uv run --group dev python -m pytest
```

