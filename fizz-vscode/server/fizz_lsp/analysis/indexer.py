from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from antlr4 import ParserRuleContext

from ..fizz_parser.FizzParser import FizzParser
from ..fizz_parser.FizzParserVisitor import FizzParserVisitor


@dataclass(frozen=True)
class Span:
    start_line: int  # 1-based
    start_col: int  # 0-based codepoints
    end_line: int  # 1-based
    end_col: int  # 0-based codepoints (exclusive)


@dataclass(frozen=True)
class Symbol:
    kind: str  # "role" | "action" | "function" | "assertion"
    name: str
    span: Span
    container: Optional[str] = None  # role name if defined inside a role


@dataclass(frozen=True)
class CallSite:
    """A simplified call site captured by the grammar's func_call_stmt shortcut."""

    span: Span  # span of the callee name
    callee: str
    receiver: Optional[str] = None
    assigned_to: Optional[str] = None
    args: List[str] = field(default_factory=list)


@dataclass
class Index:
    symbols: List[Symbol] = field(default_factory=list)
    by_name: Dict[str, List[Symbol]] = field(default_factory=dict)
    role_methods: Dict[Tuple[str, str], Symbol] = field(default_factory=dict)  # (role, method)->symbol
    role_blocks: Dict[str, Span] = field(default_factory=dict)  # role name -> full span of roledef
    calls: List[CallSite] = field(default_factory=list)

    def add(self, sym: Symbol) -> None:
        self.symbols.append(sym)
        self.by_name.setdefault(sym.name, []).append(sym)
        if sym.container and sym.kind in ("action", "function"):
            self.role_methods[(sym.container, sym.name)] = sym


def _ctx_span(ctx: ParserRuleContext) -> Span:
    start = ctx.start
    stop = ctx.stop
    if stop is None:
        return Span(start.line, start.column, start.line, start.column + 1)
    end_line = stop.line
    end_col = stop.column + (len(stop.text) if stop.text else 1)
    return Span(start.line, start.column, end_line, end_col)


def _name_span(ctx: ParserRuleContext) -> Span:
    # ctx for the `name` rule, prefer the token span
    start = ctx.start
    stop = ctx.stop
    if stop is None:
        return Span(start.line, start.column, start.line, start.column + 1)
    end_col = stop.column + (len(stop.text) if stop.text else 1)
    return Span(start.line, start.column, stop.line, end_col)


def _token_span(tok) -> Span:
    end_col = tok.column + (len(tok.text) if tok.text else 1)
    return Span(tok.line, tok.column, tok.line, end_col)


class IndexVisitor(FizzParserVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.index = Index()
        self._role_stack: List[str] = []

    @property
    def _container(self) -> Optional[str]:
        return self._role_stack[-1] if self._role_stack else None

    def visitRoledef(self, ctx: FizzParser.RoledefContext):  # noqa: N802
        name_ctx = ctx.name()
        role_name = name_ctx.getText() if name_ctx is not None else "<role>"
        self.index.role_blocks[role_name] = _ctx_span(ctx)
        self.index.add(Symbol(kind="role", name=role_name, span=_name_span(name_ctx or ctx), container=None))
        self._role_stack.append(role_name)
        try:
            return self.visitChildren(ctx)
        finally:
            self._role_stack.pop()

    def visitActiondef(self, ctx: FizzParser.ActiondefContext):  # noqa: N802
        name_ctx = ctx.name()
        name = name_ctx.getText() if name_ctx is not None else "<action>"
        self.index.add(
            Symbol(kind="action", name=name, span=_name_span(name_ctx or ctx), container=self._container)
        )
        return self.visitChildren(ctx)

    def visitFunctiondef(self, ctx: FizzParser.FunctiondefContext):  # noqa: N802
        name_ctx = ctx.name()
        name = name_ctx.getText() if name_ctx is not None else "<func>"
        self.index.add(
            Symbol(kind="function", name=name, span=_name_span(name_ctx or ctx), container=self._container)
        )
        return self.visitChildren(ctx)

    def visitAssertiondef(self, ctx: FizzParser.AssertiondefContext):  # noqa: N802
        name_ctx = ctx.name()
        name = name_ctx.getText() if name_ctx is not None else "<assertion>"
        self.index.add(Symbol(kind="assertion", name=name, span=_name_span(name_ctx or ctx), container=self._container))
        return self.visitChildren(ctx)

    def visitFunc_call_stmt(self, ctx: FizzParser.Func_call_stmtContext):  # noqa: N802
        # Grammar: (NAME ASSIGN)? (NAME DOT)? NAME OPEN_PAREN arglist? CLOSE_PAREN
        name_nodes = list(ctx.NAME())
        has_assign = ctx.ASSIGN() is not None
        has_receiver = ctx.DOT() is not None

        assigned_to = None
        receiver = None
        callee_node = None

        idx = 0
        if has_assign and name_nodes:
            assigned_to = name_nodes[0].getText()
            idx = 1

        if has_receiver and len(name_nodes) >= idx + 2:
            receiver = name_nodes[idx].getText()
            callee_node = name_nodes[idx + 1]
        elif len(name_nodes) >= idx + 1:
            callee_node = name_nodes[idx]

        if callee_node is not None:
            tok = callee_node.getSymbol()
            callee = callee_node.getText()
            args: List[str] = []
            arglist = ctx.arglist()
            if arglist is not None:
                # Best-effort: split by comma at the textual level.
                args = [a.strip() for a in arglist.getText().split(",") if a.strip()]
            self.index.calls.append(
                CallSite(
                    span=_token_span(tok),
                    callee=callee,
                    receiver=receiver,
                    assigned_to=assigned_to,
                    args=args,
                )
            )

        return self.visitChildren(ctx)


def build_index(tree) -> Index:
    visitor = IndexVisitor()
    visitor.visit(tree)
    return visitor.index

