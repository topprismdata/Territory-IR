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
