"""Import-safe access to the backend based on ``final_update_2``.

The preserved source file also contains the legacy Streamlit UI.  Executing that
file directly would render two applications, so this loader compiles only its
imports, constants and backend function definitions (through ``run_pipeline``).
This keeps the established classification/guardrail logic while allowing the
current UI to call it through a small schema adapter. Documented workflow fixes,
including auto-excluding sensitive/unavailable posts and preserving QA label
history, live in the adapter, review flow and preserved backend source.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace


SOURCE_PATH = Path(__file__).with_name("final_update2_backend_source.py")
BACKEND_LAST_LINE = 4061


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name)]


@lru_cache(maxsize=1)
def load_backend() -> SimpleNamespace:
    """Load the original final_update_2 backend without executing its old UI."""
    source = SOURCE_PATH.read_text(encoding="utf-8")
    parsed = ast.parse(source, filename=str(SOURCE_PATH))
    selected_nodes: list[ast.stmt] = []
    pipeline_node = next(
        (
            node
            for node in parsed.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run_pipeline"
        ),
        None,
    )
    backend_last_line = getattr(pipeline_node, "end_lineno", BACKEND_LAST_LINE)

    for node in parsed.body:
        if getattr(node, "lineno", backend_last_line + 1) > backend_last_line:
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            selected_nodes.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _assigned_names(node)
            if names and all(name.isupper() for name in names):
                selected_nodes.append(node)

    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "__file__": str(SOURCE_PATH),
        "__name__": "final_update2_backend_runtime",
        "__package__": "",
    }
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace, namespace)

    required = ["run_apify_tiktok_scraper_api", "run_pipeline", "apply_post_guardrails", "validate"]
    missing = [name for name in required if name not in namespace]
    if missing:
        raise RuntimeError(f"final_update_2 backend loader is missing: {', '.join(missing)}")
    return SimpleNamespace(**namespace)
