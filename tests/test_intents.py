"""意图解析回归测试：案例库 = 纠错沉淀（CBR Retain）= 回归断言。

- 确定性子集（规则直通可覆盖的句式）断言意图精确匹配；
- LLM 子集仅断言案例库格式合法（LLM 解析受随机性影响，不做硬断言）。
"""
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "territory_ir" / "intent_cases.json").read_text(encoding="utf-8"))


def test_case_file_wellformed():
    assert isinstance(CASES, list) and CASES
    for c in CASES:
        assert {"text", "action"} <= set(c), c
        assert isinstance(c["text"], str) and c["text"]
        assert isinstance(c.get("params", {}), dict)


def test_fast_intent_deterministic_subset():
    import sys
    sys.path.insert(0, str(ROOT))
    from server import _fast_intent

    # 规则直通必须覆盖的确定句式（来自历史纠正）
    cases = {
        "凤凰街道;联和街道沿思成路;龙洞街道沿渔东路;新塘街道沿天顺路;长兴街道沿天源路 生成围栏":
            ("fence_from_terms", None),
        "把 条款围栏 和 亨啡源北 合并":
            ("merge", None),
        "删除 三高速走廊":
            ("clear", None),
        "把A向西扩展到华南快速":
            ("expand", None),
    }
    for text, (action, _) in cases.items():
        intent = _fast_intent(text)
        assert intent is not None, f"应规则直通: {text}"
        assert intent["action"] == action, (text, intent)


def test_llm_cases_present_for_prompt():
    """LLM 子集案例（enclosed 等）必须在案例库中供 prompt 注入。"""
    actions = {c["action"] for c in CASES}
    assert "enclosed" in actions   # 三路围合教训
    assert "corridor" in actions   # 走廊对照案例
    assert "split" in actions
