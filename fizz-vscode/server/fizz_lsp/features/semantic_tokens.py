from __future__ import annotations

from lsprotocol.types import SemanticTokens, SemanticTokensLegend

from ..analysis.indexer import CallSite, Index, Symbol
from ..lexer_utils import lex, token_name
from ..positions import codepoint_index_to_utf16_units


SEMANTIC_TOKEN_TYPES = [
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

SEMANTIC_TOKEN_LEGEND = SemanticTokensLegend(token_types=SEMANTIC_TOKEN_TYPES, token_modifiers=[])


def _semantic_token_type(sym: Symbol) -> int | None:
    if sym.kind == "role":
        return SEMANTIC_TOKEN_TYPES.index("class")
    if sym.container is not None:
        return SEMANTIC_TOKEN_TYPES.index("method")
    if sym.kind in ("action", "function", "assertion"):
        return SEMANTIC_TOKEN_TYPES.index("function")
    return None


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

    This intentionally ignores NAME-like identifiers; those are handled structurally
    so we avoid overlaps.
    """
    lines = text.splitlines()
    lexer, all_tokens = lex(text)

    out: list[tuple[int, int, int, int]] = []
    for tok in all_tokens:
        tname = token_name(lexer, tok)
        if not tname or tname in _SKIP_TOKEN_NAMES:
            continue
        if tok.text is None or tok.text == "":
            continue

        # Skip generic names; handled elsewhere.
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
            ttype = SEMANTIC_TOKEN_TYPES.index("comment")
        elif tname == "STRING" or tname == "LABEL":
            ttype = SEMANTIC_TOKEN_TYPES.index("string")
        elif tname in _NUMERIC_TOKEN_NAMES:
            ttype = SEMANTIC_TOKEN_TYPES.index("number")
        elif tname in _OPERATOR_TOKEN_NAMES:
            ttype = SEMANTIC_TOKEN_TYPES.index("operator")
        else:
            # Treat everything else as keyword-ish.
            ttype = SEMANTIC_TOKEN_TYPES.index("keyword")

        out.append((line0, start, length, ttype))
    return out


def encode_semantic_tokens(text: str, symbols: list[Symbol], calls: list[CallSite]) -> list[int]:
    lines = text.splitlines()
    toks: list[tuple[int, int, int, int]] = []

    toks.extend(_lexical_semantic_tokens(text))

    for sym in symbols:
        ttype = _semantic_token_type(sym)
        if ttype is None:
            continue
        if sym.span.start_line != sym.span.end_line:
            continue
        line0 = sym.span.start_line - 1
        if not (0 <= line0 < len(lines)):
            continue
        line_text = lines[line0]
        start = codepoint_index_to_utf16_units(line_text, sym.span.start_col)
        end = codepoint_index_to_utf16_units(line_text, sym.span.end_col)
        length = max(1, end - start)
        toks.append((line0, start, length, ttype))

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
        ttype = SEMANTIC_TOKEN_TYPES.index("method" if call.receiver else "function")
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


def semantic_tokens_full(text: str, idx: Index) -> SemanticTokens:
    return SemanticTokens(data=encode_semantic_tokens(text, idx.symbols, idx.calls))

