"""TerritoryIR — 领地单元片编译/重演/调整核心。

一句话：手绘围栏 → 压在统一铺盖上的真值片 T → 文字条款（可人话表达）
→ 条款回放片集合 S（J 验证）→ 片并集即围栏。

快速开始::

    from territory_ir.dataset import Dataset
    ds = Dataset.guangzhou(data_dir="data/gz")
    row = ds.compile_fence(fence)      # → {human_terms, engine_terms, T, S, J, iou}
"""

from . import coords, roadsem, semantics
from .dataset import Dataset

__version__ = "0.3.1"
__all__ = ["Dataset", "coords", "roadsem", "semantics", "__version__"]
