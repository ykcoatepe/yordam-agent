from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: str
    requires_approval: bool


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolSpec]) -> None:
        self._tools: Dict[str, ToolSpec] = {tool.name: tool for tool in tools}

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def require(self, name: str) -> ToolSpec:
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")
        return tool

    def names(self) -> List[str]:
        return sorted(self._tools.keys())


DEFAULT_TOOLS = [
    ToolSpec(name="fs.read_text", category="read", requires_approval=False),
    ToolSpec(name="fs.list_dir", category="read", requires_approval=False),
    ToolSpec(name="fs.propose_write_file", category="write", requires_approval=False),
    ToolSpec(name="fs.apply_write_file", category="write", requires_approval=True),
    ToolSpec(name="fs.move", category="write", requires_approval=True),
    ToolSpec(name="fs.rename", category="write", requires_approval=True),
    ToolSpec(name="doc.extract_pdf_text", category="read", requires_approval=False),
    ToolSpec(name="web.fetch", category="network", requires_approval=True),
]


DEFAULT_REGISTRY = ToolRegistry(DEFAULT_TOOLS)
