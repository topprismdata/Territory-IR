"""43 案例本地四向评估（论文口径复现器；数据不随仓发布，D5 纪律）。

用法（本地）：
    python scripts/eval43.py <fences.json> <data_dir>
      fences.json: [{"name": str, "rings": [[ [lon,lat], ... ]]}, ...]
                   （GCJ-02 环，与生产围栏包同格式）
      data_dir:    Territory-IR 广州数据集目录（含 territory_ir_dataset.json
                   或 TIR_GZ_* 环境变量三件套）

输出：每围栏 J（片集合闭环）/ IoU（重解析几何 vs 原环）/ 条款数；
汇总 J 通过率与 IoU 中位数——论文 42/43 与 0.99 口径。
本脚本刻意不进 CI（hermetic 金标在 tests/test_api.py）。
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from territory_ir.api import TerritoryAPI  # noqa: E402
from territory_ir.dataset import Dataset  # noqa: E402


def main(fences_path: str, data_dir: str) -> int:
    fences = json.loads(Path(fences_path).read_text(encoding="utf-8"))
    ds = Dataset.guangzhou(data_dir=data_dir)
    api = TerritoryAPI(ds)
    j_pass, ious = 0, []
    for i, f in enumerate(fences, 1):
        rings = f["rings"]
        if not rings or not rings[0]:
            print(f"[{i:02d}] {f['name']}: 无环，跳过")
            continue
        rt = api.roundtrip(f["name"], rings[0])
        ious.append(rt.iou)
        j_pass += int(rt.j_exact)
        flag = "J=1" if rt.j_exact else "J=0"
        print(f"[{i:02d}] {f['name']}: {flag} iou={rt.iou:.4f} terms={len(rt.terms)}")
    med = statistics.median(ious) if ious else 0.0
    print(f"\n== 汇总: J {j_pass}/{len(ious)} | IoU 中位 {med:.4f} ==")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
