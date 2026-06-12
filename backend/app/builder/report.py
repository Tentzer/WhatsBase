from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class BuildReport:
    found: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)
    business_info: list[str] = field(default_factory=list)
    embeddings: dict = field(default_factory=lambda: {"staged": 0, "promoted": 0})
    self_test: dict = field(default_factory=lambda: {"passed": False, "questions": []})
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            "=== Build Report ===",
            f"Assets found:   {len(self.found)}",
            f"Products:       {len(self.created)}",
            f"Assumptions:    {len(self.assumed)}",
            f"Business info:  {len(self.business_info)}",
            f"Embeddings:     {self.embeddings.get('promoted', 0)} active",
            f"Self-test:      {'PASSED' if self.self_test.get('passed') else 'FAILED'}",
        ]
        if self.assumed:
            lines.append("\nAssumptions:")
            for a in self.assumed:
                lines.append(f"  * {a}")
        if self.errors:
            lines.append("\nErrors:")
            for e in self.errors:
                lines.append(f"  X {e}")
        st = self.self_test
        if st.get("questions"):
            lines.append(f"\nSelf-test ({len(st['questions'])} questions):")
            for q in st["questions"]:
                ok = "OK" if q.get("ok") else "FAIL"
                lines.append(f"  [{ok}] [{q.get('kind', '?')}] {q.get('q', '')}")
        return "\n".join(lines)
