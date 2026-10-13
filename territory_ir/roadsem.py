"""路名词表与匹配语义（组织唯一事实源，WP11 收敛）。

此前散落三处的路名知识统一至此：
- T-IR ``dataset._norm_key`` × ``semantics._norm_name``（两处重复的归一化）
- SRAF ``intelligence/llm.py`` 后缀裁剪匹配（上塘高架路 → 上塘高架）
- SRAF ``intelligence/roadsem.py`` ``RING_WORDS``/``DIR_KEEP``（环类关键词与方向语义）

纪律：本模块**只依赖标准库**——几何算法（切分/选块/闭合检测/OSM 查询）
留在各引擎仓（SRAF roadsem 几何部分、market_partition、T-IR dataset）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# 环/高速类关键词（原 SRAF roadsem.RING_WORDS）
RING_WORDS = ("绕城", "环城", "高速", "快速路", "G2504", "G2501", "G1501")

# 合同方向 → 保留侧；keep 表示「区域在界线的哪一侧」（原 SRAF roadsem.DIR_KEEP）
# "G2504以南" → G2504 是北界 → 保留界线以南的块
DIR_KEEP = {"北": "south", "南": "north", "东": "west", "西": "east"}


def norm_name(s: object) -> str:
    """路名归一化：小写 + 仅保留字母数字与汉字（分隔符/空格/标点全部剔除）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(s).lower())


def core_candidates(name: str, max_cut: int = 4, min_len: int = 2):
    """后缀裁剪候选链（归一化后）：上塘高架路 → 上塘高架 / 上塘高…（≥min_len 字）。

    覆盖「道路/公路/高架路/大街」等后缀书写差异。
    """
    n = norm_name(name)
    if n:
        yield n
    for cut in range(1, max_cut + 1):
        if len(n) - cut >= min_len:
            yield n[:-cut]


def match_in_text(name: str, text: str) -> bool:
    """路名在自由文本中是否命中（原键或任一后缀裁剪候选出现即算）。

    文本与候选同经 norm_name 归一，大小写/分隔符不敏感。
    """
    t = norm_name(text)
    return any(c and c in t for c in core_candidates(name))


def is_ring_name(name: str) -> bool:
    """名称是否环/高速类（纯词表判定；几何闭合检测留在引擎侧）。"""
    n = norm_name(name)
    return any(norm_name(w) in n for w in RING_WORDS)


def load_aliases(path: str | Path) -> dict[str, str]:
    """道路编号别名表 json → {归一化键: 规范名}；跳过 ``_`` 说明键。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        norm_name(k): str(v)
        for k, v in raw.items()
        if isinstance(k, str) and not k.startswith("_")
    }
