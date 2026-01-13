from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from antlr4 import InputStream
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_PREPARE_RENAME,
    TEXT_DOCUMENT_RENAME,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionParams,
    DefinitionParams,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidOpenTextDocumentParams,
    DocumentSymbol,
    DocumentSymbolParams,
    Hover,
    HoverParams,
    Location,
    MarkupContent,
    MarkupKind,
    Position,
    PrepareRenameParams,
    Range,
    RenameParams,
    SemanticTokens,
    SemanticTokensLegend,
    SemanticTokensParams,
    SymbolKind,
    TextDocumentSyncKind,
    TextEdit,
    WorkspaceEdit,
)
from pygls.server import LanguageServer

from .analysis.indexer import CallSite, Index, Span, Symbol, build_index
from .fizz_parser.FizzLexer import FizzLexer
from .parse import ParseError, parse_text
from .positions import codepoint_index_to_utf16_units, utf16_units_to_codepoint_index

_LOG_LEVEL = os.getenv("FIZZ_LSP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=_LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fizz_lsp")


@dataclass
class DocumentState:
    version: int
    text: str
    last_good_text: Optional[str] = None
    index: Optional[Index] = None
    type_env: Optional[Dict[str, str]] = None
    index_version: int = -1
    diagnostics_task: Optional[asyncio.Task] = None


class FizzLanguageServer(LanguageServer):
    """Fizz language server."""

    def __init__(self) -> None:
        super().__init__("fizz-lsp", "0.0.1")
        self._docs: Dict[str, DocumentState] = {}

    def _publish_diagnostics_for(self, uri: str, text: str) -> None:
        parsed = parse_text(text)

        diagnostics: list[Diagnostic] = []
        for err in parsed.errors:
            diagnostics.append(_parse_error_to_diagnostic(text, err))

        self.publish_diagnostics(uri, diagnostics)
        logger.debug("published %d diagnostics for %s", len(diagnostics), uri)

    def _analyze(self, uri: str) -> Optional[Index]:
        doc = self._docs.get(uri)
        if doc is None:
            return None
        if doc.index is not None and doc.index_version == doc.version:
            return doc.index

        parsed = parse_text(doc.text)
        if parsed.tree is None:
            return doc.index
        idx = build_index(parsed.tree)
        doc.index = idx
        doc.type_env = _build_type_env(doc.text, idx)
        doc.index_version = doc.version
        return idx

    def _schedule_diagnostics(self, uri: str, delay_s: float = 0.2) -> None:
        doc = self._docs.get(uri)
        if doc is None:
            return

        if doc.diagnostics_task is not None and not doc.diagnostics_task.done():
            doc.diagnostics_task.cancel()

        async def _run(expected_version: int) -> None:
            try:
                await asyncio.sleep(delay_s)
                cur = self._docs.get(uri)
                if cur is None:
                    return
                # If the document has changed again, let the newer task handle it.
                if cur.version != expected_version:
                    return
                self._publish_diagnostics_for(uri, cur.text)
            except asyncio.CancelledError:
                return

        doc.diagnostics_task = asyncio.create_task(_run(doc.version))


def _parse_error_to_diagnostic(text: str, err: ParseError) -> Diagnostic:
    # ANTLR: line is 1-based, column is 0-based.
    line0 = max(0, err.line - 1)
    lines = text.splitlines()
    line_text = lines[line0] if line0 < len(lines) else ""

    start_char = codepoint_index_to_utf16_units(line_text, err.column)
    end_char = min(
        start_char + 1, codepoint_index_to_utf16_units(line_text, len(line_text))
    )

    return Diagnostic(
        range=Range(
            start=Position(line=line0, character=start_char),
            end=Position(line=line0, character=end_char),
        ),
        message=err.message,
        severity=DiagnosticSeverity.Error,
        source="fizz",
    )


def _span_to_range(text: str, span: Span) -> Range:
    lines = text.splitlines()
    s_line0 = max(0, span.start_line - 1)
    e_line0 = max(0, span.end_line - 1)
    s_line_text = lines[s_line0] if s_line0 < len(lines) else ""
    e_line_text = lines[e_line0] if e_line0 < len(lines) else ""

    s_char = codepoint_index_to_utf16_units(s_line_text, span.start_col)
    e_char = codepoint_index_to_utf16_units(e_line_text, span.end_col)

    return Range(
        start=Position(line=s_line0, character=s_char),
        end=Position(line=e_line0, character=e_char),
    )


def _symbol_kind(sym: Symbol) -> SymbolKind:
    if sym.kind == "role":
        return SymbolKind.Class
    if sym.container is not None:
        return SymbolKind.Method
    if sym.kind in ("action", "function", "assertion"):
        return SymbolKind.Function
    return SymbolKind.Variable


def _role_at_position(idx: Index, line1: int, col_codepoint: int) -> Optional[str]:
    for role_name, span in idx.role_blocks.items():
        if line1 < span.start_line or line1 > span.end_line:
            continue
        if line1 == span.start_line and col_codepoint < span.start_col:
            continue
        if line1 == span.end_line and col_codepoint > span.end_col:
            continue
        return role_name
    return None


def _identifier_at(line_text: str, utf16_character: int) -> str:
    col = utf16_units_to_codepoint_index(line_text, utf16_character)
    if col > len(line_text):
        col = len(line_text)

    def is_ident(ch: str) -> bool:
        return ch == "_" or ch.isalnum()

    l = col
    while l > 0 and is_ident(line_text[l - 1]):
        l -= 1
    r = col
    while r < len(line_text) and is_ident(line_text[r]):
        r += 1
    return line_text[l:r]


def _is_valid_identifier(name: str) -> bool:
    import re

    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None


def _frontmatter_line_count(text: str) -> int:
    """Return number of lines occupied by YAML frontmatter block, if present."""
    import re

    m = re.search(r"^(\s*)---[^\n]*\n([\s\S]*?)---[^\n]*\n", text, re.MULTILINE)
    if not m:
        return 0
    return len(m.group(0).splitlines())


def _name_token_at_position(text: str, line0: int, char0_utf16: int):
    """Return lexer token for the NAME under cursor, or None."""
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    col_cp = utf16_units_to_codepoint_index(line_text, char0_utf16)
    line1 = line0 + 1

    fm_lines = _frontmatter_line_count(text)

    stream = InputStream(text)
    lexer = FizzLexer(stream)
    tokens = lexer.getAllTokens()

    for tok in tokens:
        if tok.line is None:
            continue
        if fm_lines and tok.line <= fm_lines:
            continue
        if tok.line != line1:
            continue
        if tok.text is None:
            continue
        tname = (
            lexer.symbolicNames[tok.type]
            if 0 <= tok.type < len(lexer.symbolicNames)
            else None
        )
        if tname != "NAME":
            continue
        start = tok.column
        end = tok.column + len(tok.text)
        if start <= col_cp < end:
            return tok
    return None


def _rename_edits_for_document(text: str, old: str, new: str) -> list[TextEdit]:
    """Compute file-local rename edits for NAME tokens, skipping strings/comments/frontmatter."""
    if not _is_valid_identifier(new):
        return []
    if old in ("self",):
        return []

    fm_lines = _frontmatter_line_count(text)

    stream = InputStream(text)
    lexer = FizzLexer(stream)
    tokens = lexer.getAllTokens()
    lines = text.splitlines()

    edits: list[TextEdit] = []
    for tok in tokens:
        if tok.line is None or tok.text is None:
            continue
        if fm_lines and tok.line <= fm_lines:
            continue
        tname = (
            lexer.symbolicNames[tok.type]
            if 0 <= tok.type < len(lexer.symbolicNames)
            else None
        )
        if tname != "NAME":
            continue
        if tok.text != old:
            continue
        line0 = tok.line - 1
        if not (0 <= line0 < len(lines)):
            continue
        line_text = lines[line0]
        start_char = codepoint_index_to_utf16_units(line_text, tok.column)
        end_char = codepoint_index_to_utf16_units(line_text, tok.column + len(tok.text))
        edits.append(
            TextEdit(
                range=Range(
                    start=Position(line=line0, character=start_char),
                    end=Position(line=line0, character=end_char),
                ),
                new_text=new,
            )
        )
    return edits


_SEMANTIC_TOKEN_TYPES = [
    # lexical-ish
    "comment",
    "string",
    "number",
    "keyword",
    "operator",
    # structural
    "class",
    "function",
    "method",
]
_SEMANTIC_TOKEN_LEGEND = SemanticTokensLegend(
    token_types=_SEMANTIC_TOKEN_TYPES, token_modifiers=[]
)


def _semantic_token_type(sym: Symbol) -> Optional[int]:
    if sym.kind == "role":
        return _SEMANTIC_TOKEN_TYPES.index("class")
    if sym.container is not None:
        return _SEMANTIC_TOKEN_TYPES.index("method")
    if sym.kind in ("action", "function", "assertion"):
        return _SEMANTIC_TOKEN_TYPES.index("function")
    return None


def _encode_semantic_tokens(
    text: str, symbols: list[Symbol], calls: list[CallSite]
) -> list[int]:
    lines = text.splitlines()
    toks: list[tuple[int, int, int, int]] = (
        []
    )  # (line0, startCharUtf16, lengthUtf16, tokenType)

    # Lexical tokens (to avoid "semantic tokens blanks out TextMate" behavior in some clients).
    toks.extend(_lexical_semantic_tokens(text))

    for sym in symbols:
        ttype = _semantic_token_type(sym)
        if ttype is None:
            continue
        if sym.span.start_line != sym.span.end_line:
            continue  # should not happen for name spans
        line0 = sym.span.start_line - 1
        if not (0 <= line0 < len(lines)):
            continue
        line_text = lines[line0]
        start = codepoint_index_to_utf16_units(line_text, sym.span.start_col)
        end = codepoint_index_to_utf16_units(line_text, sym.span.end_col)
        length = max(1, end - start)
        toks.append((line0, start, length, ttype))

    # Call sites (best effort): treat attribute calls as methods, bare calls as functions.
    for call in calls:
        if call.span.start_line != call.span.end_line:
            continue
        line0 = call.span.start_line - 1
        if not (0 <= line0 < len(lines)):
            continue
        line_text = lines[line0]
        start = codepoint_index_to_utf16_units(line_text, call.span.start_col)
        end = codepoint_index_to_utf16_units(line_text, call.span.end_col)
        length = max(1, end - start)
        ttype = _SEMANTIC_TOKEN_TYPES.index("method" if call.receiver else "function")
        toks.append((line0, start, length, ttype))

    toks.sort()

    data: list[int] = []
    prev_line = 0
    prev_start = 0
    for line0, start, length, ttype in toks:
        delta_line = line0 - prev_line
        delta_start = start - prev_start if delta_line == 0 else start
        data.extend([delta_line, delta_start, length, ttype, 0])
        prev_line = line0
        prev_start = start
    return data


_NUMERIC_TOKEN_NAMES = {
    "DECIMAL_INTEGER",
    "OCT_INTEGER",
    "HEX_INTEGER",
    "BIN_INTEGER",
    "FLOAT_NUMBER",
    "IMAG_NUMBER",
}

_OPERATOR_TOKEN_NAMES = {
    "DOT",
    "ELLIPSIS",
    "STAR",
    "COMMA",
    "COLON",
    "SEMI_COLON",
    "POWER",
    "ASSIGN",
    "OR_OP",
    "XOR",
    "AND_OP",
    "LEFT_SHIFT",
    "RIGHT_SHIFT",
    "ADD",
    "MINUS",
    "DIV",
    "MOD",
    "IDIV",
    "NOT_OP",
    "LESS_THAN",
    "GREATER_THAN",
    "EQUALS",
    "GT_EQ",
    "LT_EQ",
    "NOT_EQ_1",
    "NOT_EQ_2",
    "AT",
    "ARROW",
    "ADD_ASSIGN",
    "SUB_ASSIGN",
    "MULT_ASSIGN",
    "AT_ASSIGN",
    "DIV_ASSIGN",
    "MOD_ASSIGN",
    "AND_ASSIGN",
    "OR_ASSIGN",
    "XOR_ASSIGN",
    "LEFT_SHIFT_ASSIGN",
    "RIGHT_SHIFT_ASSIGN",
    "POWER_ASSIGN",
    "IDIV_ASSIGN",
    "OPEN_PAREN",
    "CLOSE_PAREN",
    "OPEN_BRACE",
    "CLOSE_BRACE",
    "OPEN_BRACKET",
    "CLOSE_BRACKET",
}

_SKIP_TOKEN_NAMES = {
    "WS",
    "NEWLINE",
    "LINE_JOIN",
    "INDENT",
    "DEDENT",
    "LINE_BREAK",
}


def _lexical_semantic_tokens(text: str) -> list[tuple[int, int, int, int]]:
    """Return semantic tokens for comments/strings/numbers/keywords/operators.

    This intentionally ignores NAME-like identifiers; those are handled by the
    indexer (definitions/calls) so we avoid overlaps.
    """
    lines = text.splitlines()
    stream = InputStream(text)
    lexer = FizzLexer(stream)
    all_tokens = lexer.getAllTokens()

    out: list[tuple[int, int, int, int]] = []
    for tok in all_tokens:
        tname = (
            lexer.symbolicNames[tok.type]
            if 0 <= tok.type < len(lexer.symbolicNames)
            else None
        )
        if not tname or tname in _SKIP_TOKEN_NAMES:
            continue
        if tok.text is None or tok.text == "":
            continue

        # Skip generic names; we handle identifiers structurally.
        if tname == "NAME":
            continue

        if tok.line is None:
            continue
        line0 = tok.line - 1
        if line0 < 0 or line0 >= len(lines):
            continue
        line_text = lines[line0]
        start = codepoint_index_to_utf16_units(line_text, tok.column)
        end = codepoint_index_to_utf16_units(line_text, tok.column + len(tok.text))
        length = max(1, end - start)

        if tname == "COMMENT":
            ttype = _SEMANTIC_TOKEN_TYPES.index("comment")
        elif tname == "STRING" or tname == "LABEL":
            ttype = _SEMANTIC_TOKEN_TYPES.index("string")
        elif tname in _NUMERIC_TOKEN_NAMES:
            ttype = _SEMANTIC_TOKEN_TYPES.index("number")
        elif tname in _OPERATOR_TOKEN_NAMES:
            ttype = _SEMANTIC_TOKEN_TYPES.index("operator")
        else:
            # Treat everything else in the lexer vocabulary as a keyword-ish token.
            # This covers Python keywords + Fizz keywords like ACTION/FUNC/ROLE/ATOMIC/etc.
            ttype = _SEMANTIC_TOKEN_TYPES.index("keyword")

        out.append((line0, start, length, ttype))

    return out


def _build_type_env(text: str, idx: Index) -> Dict[str, str]:
    """Best-effort type inference for role instances.

    Goal: enable navigation from call-sites like `rm.Prepare()` to the matching
    role method definition.
    """
    roles = {s.name for s in idx.symbols if s.kind == "role"}
    var_type: Dict[str, str] = {}
    list_elem_type: Dict[str, str] = {}

    # Constructor calls: `x = RoleName(...)`
    for call in idx.calls:
        if call.assigned_to and call.receiver is None and call.callee in roles:
            var_type[call.assigned_to] = call.callee

    # Very small collection inference: `xs.append(x)` where x is a known role instance
    for call in idx.calls:
        if call.receiver and call.callee == "append" and call.args:
            arg0 = call.args[0]
            # Best-effort: strip kwarg, indexing, etc.
            arg0 = arg0.split("=", 1)[-1].strip()
            if arg0 in var_type:
                list_elem_type[call.receiver] = var_type[arg0]

    # Loop var inference: `for rm in participants:`
    import re

    for m in re.finditer(
        r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", text
    ):
        loop_var, iterable = m.group(1), m.group(2)
        if iterable in list_elem_type:
            var_type[loop_var] = list_elem_type[iterable]

    return var_type


def _callsite_at(idx: Index, line1: int, col_codepoint: int) -> Optional[CallSite]:
    for call in idx.calls:
        if call.span.start_line != line1:
            continue
        if call.span.start_col <= col_codepoint <= call.span.end_col:
            return call
    return None


_KEYWORD_COMPLETIONS = [
    "action",
    "func",
    "init",
    "role",
    "symmetric",
    "atomic",
    "serial",
    "parallel",
    "oneof",
    "any",
    "exists",
    "fair",
    "require",
    "invariants",
    "always",
    "eventually",
    "assertion",
    "transition",
    "compose",
    "refine",
]


def _completion_for_position(
    text: str, idx: Index, line0: int, char0_utf16: int
) -> list[CompletionItem]:
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    col_cp = utf16_units_to_codepoint_index(line_text, char0_utf16)
    prefix = line_text[:col_cp]

    items: list[CompletionItem] = []

    # Member completions after self.
    if prefix.endswith("self."):
        role = _role_at_position(idx, line0 + 1, col_cp)
        if role:
            members = [
                s
                for s in idx.symbols
                if s.container == role and s.kind in ("action", "function")
            ]
            for m in sorted(members, key=lambda s: s.name):
                items.append(
                    CompletionItem(
                        label=m.name,
                        kind=(
                            CompletionItemKind.Method
                            if m.container
                            else CompletionItemKind.Function
                        ),
                        detail=f"{m.kind} {m.name}",
                    )
                )
            return items

    # Fallback: keywords + known top-level symbols.
    for kw in _KEYWORD_COMPLETIONS:
        items.append(CompletionItem(label=kw, kind=CompletionItemKind.Keyword))

    for s in sorted(
        (s for s in idx.symbols if s.container is None), key=lambda s: s.name
    ):
        kind = (
            CompletionItemKind.Class
            if s.kind == "role"
            else CompletionItemKind.Function
        )
        items.append(CompletionItem(label=s.name, kind=kind, detail=s.kind))

    return items


server = FizzLanguageServer()
server.text_document_sync_kind = TextDocumentSyncKind.Full


@server.feature("textDocument/didOpen")
def did_open(ls: FizzLanguageServer, params: DidOpenTextDocumentParams) -> None:
    doc = params.text_document
    ls._docs[doc.uri] = DocumentState(
        version=doc.version or 0, text=doc.text, last_good_text=doc.text
    )
    logger.info("didOpen uri=%s version=%s", doc.uri, doc.version)
    ls._publish_diagnostics_for(doc.uri, doc.text)


@server.feature("textDocument/didChange")
def did_change(ls: FizzLanguageServer, params: DidChangeTextDocumentParams) -> None:
    doc = params.text_document
    uri = doc.uri
    if uri not in ls._docs:
        ls._docs[uri] = DocumentState(
            version=doc.version or 0, text="", last_good_text=None
        )

    # v1: accept full-sync only (the client will be configured accordingly).
    new_text = params.content_changes[0].text if params.content_changes else ""
    ls._docs[uri].text = new_text
    ls._docs[uri].version = doc.version or ls._docs[uri].version
    ls._docs[uri].last_good_text = new_text
    logger.debug("didChange uri=%s version=%s", uri, doc.version)
    ls._schedule_diagnostics(uri)


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbols(
    ls: FizzLanguageServer, params: DocumentSymbolParams
) -> list[DocumentSymbol]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return []
    idx = ls._analyze(uri)
    if idx is None:
        return []

    by_role: Dict[str, list[Symbol]] = {}
    top_level: list[Symbol] = []
    role_syms: list[Symbol] = []
    for s in idx.symbols:
        if s.kind == "role":
            role_syms.append(s)
            continue
        if s.container:
            by_role.setdefault(s.container, []).append(s)
        else:
            top_level.append(s)

    symbols: list[DocumentSymbol] = []

    for role_sym in sorted(
        role_syms, key=lambda x: (x.span.start_line, x.span.start_col)
    ):
        children = [
            DocumentSymbol(
                name=child.name,
                kind=_symbol_kind(child),
                range=_span_to_range(doc.text, child.span),
                selection_range=_span_to_range(doc.text, child.span),
            )
            for child in sorted(
                by_role.get(role_sym.name, []),
                key=lambda x: (x.span.start_line, x.span.start_col),
            )
        ]
        role_range = idx.role_blocks.get(role_sym.name, role_sym.span)
        symbols.append(
            DocumentSymbol(
                name=role_sym.name,
                kind=_symbol_kind(role_sym),
                range=_span_to_range(doc.text, role_range),
                selection_range=_span_to_range(doc.text, role_sym.span),
                children=children or None,
            )
        )

    for s in sorted(top_level, key=lambda x: (x.span.start_line, x.span.start_col)):
        symbols.append(
            DocumentSymbol(
                name=s.name,
                kind=_symbol_kind(s),
                range=_span_to_range(doc.text, s.span),
                selection_range=_span_to_range(doc.text, s.span),
            )
        )

    return symbols


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(
    ls: FizzLanguageServer, params: DefinitionParams
) -> Optional[list[Location]]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    idx = ls._analyze(uri)
    if idx is None:
        return None

    line0 = params.position.line
    char0 = params.position.character
    lines = doc.text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    ident = _identifier_at(line_text, char0)
    if not ident:
        return None

    col_codepoint = utf16_units_to_codepoint_index(line_text, char0)
    role = _role_at_position(idx, line0 + 1, col_codepoint)

    call = _callsite_at(idx, line0 + 1, col_codepoint)
    if call is not None and call.callee == ident:
        # Resolve method calls like `rm.Prepare()`.
        if call.receiver == "self" and role is not None:
            sym = idx.role_methods.get((role, ident))
            if sym is not None:
                return [Location(uri=uri, range=_span_to_range(doc.text, sym.span))]
        elif call.receiver:
            recv_type = doc.type_env.get(call.receiver) if doc.type_env else None
            if recv_type:
                sym = idx.role_methods.get((recv_type, ident))
                if sym is not None:
                    return [Location(uri=uri, range=_span_to_range(doc.text, sym.span))]

    if role is not None:
        sym = idx.role_methods.get((role, ident))
        if sym is not None:
            return [Location(uri=uri, range=_span_to_range(doc.text, sym.span))]

    candidates = idx.by_name.get(ident, [])
    if len(candidates) == 1:
        sym = candidates[0]
        return [Location(uri=uri, range=_span_to_range(doc.text, sym.span))]

    return None


@server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, _SEMANTIC_TOKEN_LEGEND)
def semantic_tokens_full(
    ls: FizzLanguageServer, params: SemanticTokensParams
) -> SemanticTokens:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return SemanticTokens(data=[])
    idx = ls._analyze(uri)
    if idx is None:
        return SemanticTokens(data=[])
    data = _encode_semantic_tokens(doc.text, idx.symbols, idx.calls)
    return SemanticTokens(data=data)


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completion(ls: FizzLanguageServer, params: CompletionParams) -> CompletionList:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return CompletionList(is_incomplete=False, items=[])
    idx = ls._analyze(uri)
    if idx is None:
        return CompletionList(is_incomplete=False, items=[])

    items = _completion_for_position(
        doc.text, idx, params.position.line, params.position.character
    )
    return CompletionList(is_incomplete=False, items=items)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: FizzLanguageServer, params: HoverParams) -> Optional[Hover]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    idx = ls._analyze(uri)
    if idx is None:
        return None

    line0 = params.position.line
    char0 = params.position.character
    lines = doc.text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    ident = _identifier_at(line_text, char0)
    if not ident:
        return None

    candidates = idx.by_name.get(ident, [])
    if not candidates:
        return None

    # Prefer role-local resolution when possible.
    col_codepoint = utf16_units_to_codepoint_index(line_text, char0)
    role = _role_at_position(idx, line0 + 1, col_codepoint)
    sym = idx.role_methods.get((role, ident)) if role else None
    if sym is None and len(candidates) == 1:
        sym = candidates[0]
    if sym is None:
        return None

    detail = f"{sym.kind} {sym.name}"
    if sym.container:
        detail = f"{sym.container}.{sym.name} ({sym.kind})"

    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.Markdown, value=f"```fizz\n{detail}\n```"
        ),
        range=_span_to_range(doc.text, sym.span),
    )


@server.feature(TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename(
    ls: FizzLanguageServer, params: PrepareRenameParams
) -> Optional[Range]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    tok = _name_token_at_position(
        doc.text, params.position.line, params.position.character
    )
    if tok is None or tok.text is None:
        return None
    if tok.text in ("self",):
        return None
    lines = doc.text.splitlines()
    line0 = tok.line - 1
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    start_char = codepoint_index_to_utf16_units(line_text, tok.column)
    end_char = codepoint_index_to_utf16_units(line_text, tok.column + len(tok.text))
    return Range(
        start=Position(line=line0, character=start_char),
        end=Position(line=line0, character=end_char),
    )


@server.feature(TEXT_DOCUMENT_RENAME)
def rename(ls: FizzLanguageServer, params: RenameParams) -> Optional[WorkspaceEdit]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    tok = _name_token_at_position(
        doc.text, params.position.line, params.position.character
    )
    if tok is None or tok.text is None:
        return None
    old = tok.text
    new = params.new_name
    edits = _rename_edits_for_document(doc.text, old, new)
    if not edits:
        return None
    return WorkspaceEdit(changes={uri: edits})
