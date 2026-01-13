from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .indexer import CallSite, Index


def build_type_env(text: str, idx: Index) -> Dict[str, str]:
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
        r"\bfor\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*:",
        text,
    ):
        loop_var, iterable = m.group(1), m.group(2)
        if iterable in list_elem_type:
            var_type[loop_var] = list_elem_type[iterable]

    return var_type


def callsite_at(idx: Index, line1: int, col_codepoint: int) -> Optional[CallSite]:
    for call in idx.calls:
        if call.span.start_line != line1:
            continue
        if call.span.start_col <= col_codepoint <= call.span.end_col:
            return call
    return None

