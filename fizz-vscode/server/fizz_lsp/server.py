from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_PREPARE_RENAME,
    TEXT_DOCUMENT_RENAME,
    TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
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
    Position,
    PrepareRenameParams,
    Range,
    RenameParams,
    SemanticTokens,
    SemanticTokensParams,
    TextDocumentSyncKind,
    WorkspaceEdit,
)
from pygls.server import LanguageServer

from .analysis.indexer import Index, build_index
from .analysis.type_env import build_type_env
from .features.completion import completion_items_for_position
from .features.definition import definition_locations
from .features.hover import hover_for_position
from .features.rename import prepare_rename_range, workspace_edit_for_rename
from .features.semantic_tokens import SEMANTIC_TOKEN_LEGEND
from .features.semantic_tokens import (
    semantic_tokens_full as semantic_tokens_full_result,
)
from .features.symbols import document_symbols_for
from .parse import ParseError, parse_text
from .positions import codepoint_index_to_utf16_units

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
        doc.type_env = build_type_env(doc.text, idx)
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
    return document_symbols_for(doc.text, idx)


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
    return definition_locations(
        text=doc.text, idx=idx, type_env=doc.type_env, uri=uri, position=params.position
    )


@server.feature(TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, SEMANTIC_TOKEN_LEGEND)
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
    return semantic_tokens_full_result(doc.text, idx)


@server.feature(TEXT_DOCUMENT_COMPLETION)
def completion(ls: FizzLanguageServer, params: CompletionParams) -> CompletionList:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return CompletionList(is_incomplete=False, items=[])
    idx = ls._analyze(uri)
    if idx is None:
        return CompletionList(is_incomplete=False, items=[])

    items = completion_items_for_position(
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
    return hover_for_position(doc.text, idx, params.position)


@server.feature(TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename(
    ls: FizzLanguageServer, params: PrepareRenameParams
) -> Optional[Range]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    return prepare_rename_range(
        doc.text, params.position.line, params.position.character
    )


@server.feature(TEXT_DOCUMENT_RENAME)
def rename(ls: FizzLanguageServer, params: RenameParams) -> Optional[WorkspaceEdit]:
    uri = params.text_document.uri
    doc = ls._docs.get(uri)
    if doc is None:
        return None
    return workspace_edit_for_rename(
        doc.text, uri, params.position.line, params.position.character, params.new_name
    )
