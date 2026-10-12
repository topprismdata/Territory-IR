"""GCJ-02 ⇄ WGS-84 坐标转换。

WP03 收敛: 算法本体迁移至 coords-core v0.1.0 (组织唯一事实源)。
本模块保留原 API 名 (wgs2gcj/gcj2wgs/convert/wgs2gcj_vec/gcj2wgs_vec),
全部再导出自 coords_core; 位级一致由 coords-core 金标测试锁定。
帧纪律规范见 coords_core.frames。
"""
from coords_core import (  # noqa: F401
    A,
    EE,
    PI,
    convert,
    gcj2wgs,
    out_of_china,
    wgs2gcj,
)
from coords_core.vector import gcj2wgs_vec, wgs2gcj_vec  # noqa: F401
