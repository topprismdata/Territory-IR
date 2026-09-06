"""GCJ-02 ⇄ WGS-84 坐标转换（中国国标偏移模型，与线上实现逐位一致）。"""

from __future__ import annotations

import math

A = 6378245.0
EE = 0.00669342162296594323
PI = math.pi


def _tl(x: float, y: float) -> float:
    r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return r


def _to(x: float, y: float) -> float:
    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x * PI / 30.0)) * 2.0 / 3.0
    return r


def wgs2gcj(lon: float, lat: float) -> tuple[float, float]:
    if out_of_china(lon, lat):
        return lon, lat
    rl = lat / 180.0 * PI
    magic = 1.0 - EE * math.sin(rl) ** 2
    sm = math.sqrt(magic)
    dlat = _tl(lon - 105.0, lat - 35.0)
    dlat = (dlat * 180.0) / ((A * (1.0 - EE)) / (magic * sm) * PI)
    dlon = _to(lon - 105.0, lat - 35.0)
    dlon = (dlon * 180.0) / (A / sm * math.cos(rl) * PI)
    return lon + dlon, lat + dlat


def gcj2wgs(lon: float, lat: float) -> tuple[float, float]:
    w = (lon, lat)
    for _ in range(6):
        g = wgs2gcj(*w)
        w = (lon + w[0] - g[0], lat + w[1] - g[1])
    return w


def out_of_china(lon: float, lat: float) -> bool:
    return not (72.0 <= lon <= 137.8 and 0.8 <= lat <= 55.8)


def convert(pt, to_wgs: bool) -> tuple[float, float]:
    """单点自动方向；境外点原样返回。"""
    lon, lat = pt[0], pt[1]
    if out_of_china(lon, lat):
        return lon, lat
    return gcj2wgs(lon, lat) if to_wgs else wgs2gcj(lon, lat)


# ---------- numpy 向量化批量转换（大对象集一次性转换用） ----------


def _tl_vec(x, y):
    import numpy as np

    r = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * np.sqrt(np.abs(x))
    )
    r += (20.0 * np.sin(6.0 * x * PI) + 20.0 * np.sin(2.0 * x * PI)) * 2.0 / 3.0
    r += (20.0 * np.sin(y * PI) + 40.0 * np.sin(y / 3.0 * PI)) * 2.0 / 3.0
    r += (160.0 * np.sin(y / 12.0 * PI) + 320.0 * np.sin(y * PI / 30.0)) * 2.0 / 3.0
    return r


def _to_vec(x, y):
    import numpy as np

    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * np.sqrt(np.abs(x))
    r += (20.0 * np.sin(6.0 * x * PI) + 20.0 * np.sin(2.0 * x * PI)) * 2.0 / 3.0
    r += (20.0 * np.sin(x * PI) + 40.0 * np.sin(x / 3.0 * PI)) * 2.0 / 3.0
    r += (150.0 * np.sin(x / 12.0 * PI) + 300.0 * np.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return r


def wgs2gcj_vec(lon, lat):
    """numpy 向量化批量 wgs2gcj。"""
    import numpy as np

    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    rl = lat / 180.0 * PI
    magic = 1.0 - EE * np.sin(rl) ** 2
    sm = np.sqrt(magic)
    dlat = _tl_vec(lon - 105.0, lat - 35.0)
    dlat = (dlat * 180.0) / ((A * (1.0 - EE)) / (magic * sm) * PI)
    dlon = _to_vec(lon - 105.0, lat - 35.0)
    dlon = (dlon * 180.0) / (A / sm * np.cos(rl) * PI)
    return lon + dlon, lat + dlat


def gcj2wgs_vec(lon, lat):
    """numpy 向量化批量 gcj2wgs（6 轮定点迭代）。"""
    import numpy as np

    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    w_lon, w_lat = lon.copy(), lat.copy()
    for _ in range(6):
        g_lon, g_lat = wgs2gcj_vec(w_lon, w_lat)
        w_lon = lon + w_lon - g_lon
        w_lat = lat + w_lat - g_lat
    return w_lon, w_lat
