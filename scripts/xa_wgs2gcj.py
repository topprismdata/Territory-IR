"""安居客西安数据 WGS-84 → GCJ-02 批量转换（列10=经度, 列11=纬度）。"""

import csv
import math
import sys

sys.path.insert(0, "/Users/ghb/territory-ir")
from territory_ir.coords import wgs2gcj_vec  # noqa: E402

SRC = "/Users/ghb/Downloads/安居客8月西安数据-12517条-WGS84.csv"
DST = "/Users/ghb/Downloads/安居客8月西安数据-12517条-GCJ02.csv"

csv.field_size_limit(10 * 1024 * 1024)

with open(SRC, encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

ILAT, ILON = 11, 10
lons = [float(r[ILON]) for r in rows]
lats = [float(r[ILAT]) for r in rows]
glon, glat = wgs2gcj_vec(lons, lats)

for r, lo, la in zip(rows, glon, glat, strict=True):
    r[ILON] = f"{lo:.6f}"
    r[ILAT] = f"{la:.6f}"

with open(DST, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(rows)


shifts = [
    math.hypot((float(r[ILON]) - lo) * 92, (float(r[ILAT]) - la) * 110)
    for r, lo, la in zip(rows, lons, lats, strict=True)
]
print(f"转换完成: {len(rows)} 行 → {DST}")
print(
    f"偏移量: 均值 {sum(shifts)/len(shifts):.0f}m, "
    f"范围 {min(shifts):.0f}~{max(shifts):.0f}m"
)
