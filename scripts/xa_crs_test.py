"""西安安居客坐标系三重判定：WGS-84 vs GCJ-02 vs BD-09。

参照点：Overpass 提供的大雁塔 WGS 权威坐标 + 三重坐标孪生。
"""
import csv
import json
import math
import urllib.request
import ssl
import urllib.parse

CSV = "/Users/ghb/Downloads/安居客8月数据汇总1（47万）.csv"
A, EE, PI = 6378245.0, 0.00669342162296594323, math.pi
X_PI = math.pi * 3000 / 180


def _tl(x, y):
    r = -100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    r += (20*math.sin(6*x*PI) + 20*math.sin(2*x*PI)) * 2/3
    r += (20*math.sin(y*PI) + 40*math.sin(y/3*PI)) * 2/3
    r += (160*math.sin(y/12*PI) + 320*math.sin(y*PI/30)) * 2/3
    return r


def _to(x, y):
    r = 300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    r += (20*math.sin(6*x*PI) + 20*math.sin(2*x*PI)) * 2/3
    r += (20*math.sin(x*PI) + 40*math.sin(x/3*PI)) * 2/3
    r += (150*math.sin(x/12*PI) + 300*math.sin(x/30*PI)) * 2/3
    return r


def wgs2gcj(lng, lat):
    rl = lat / 180 * PI
    magic = 1 - EE * math.sin(rl) ** 2
    sm = math.sqrt(magic)
    dlat = _tl(lng - 105, lat - 35) * 180 / ((A * (1 - EE)) / (magic * sm) * PI)
    dlon = _to(lng - 105, lat - 35) * 180 / (A / sm * math.cos(rl) * PI)
    return lng + dlon, lat + dlat


def gcj2bd(lng, lat):
    z = math.sqrt(lng**2 + lat**2) + 0.00002 * math.sin(lat * X_PI)
    t = math.atan2(lat, lng) + 0.000003 * math.cos(lng * X_PI)
    return z * math.cos(t) + 0.0065, z * math.sin(t) + 0.006


def dist_m(la1, lo1, la2, lo2):
    dy = (la1 - la2) * 110.574
    dx = (lo1 - lo2) * 111.32 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dy, dx)


def fetch_landmark():
    """Overpass: 大雁塔 attraction 节点 (WGS-84)。"""
    q = ('[out:json][timeout:25];'
         '(node["name"~"大雁塔"](34.19,108.93,34.24,108.99);'
         'way["name"~"大雁塔"](34.19,108.93,34.24,108.99););'
         'out center 8;')
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter", data=data,
        headers={"User-Agent": "TerritoryIR/1.0"})
    ctx = __import__("ssl").create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    d = json.load(urllib.request.urlopen(req, timeout=45, context=ctx))
    e = d["elements"][0]
    return e["lat"], e["lon"]


def main():
    wgs_lat, wgs_lon = fetch_landmark()
    gcj_lon, gcj_lat = wgs2gcj(wgs_lon, wgs_lat)
    bd_lat, bd_lon = gcj2bd(gcj_lon, gcj_lat)
    print(f"大雁塔参照: WGS({wgs_lat:.6f},{wgs_lon:.6f}) "
          f"GCJ({gcj_lat:.6f},{gcj_lon:.6f}) BD({bd_lat:.6f},{bd_lon:.6f})")

    csv.field_size_limit(10 * 1024 * 1024)
    rows = []
    with open(CSV, encoding="gbk", errors="replace") as f:
        reader = csv.reader(f)
        next(reader)
        for r in reader:
            if "西安" not in r[1]:
                continue
            blob = r[4] + r[8] + r[9]
            if "大雁塔" in blob:
                try:
                    rows.append((r[4], float(r[10]), float(r[11])))
                except Exception:
                    pass

    scored = sorted(rows, key=lambda x: min(
        dist_m(x[2], x[1], wgs_lat, wgs_lon),
        dist_m(x[2], x[1], gcj_lat, gcj_lon),
        dist_m(x[2], x[1], bd_lat, bd_lon)))[:8]

    wins = {"WGS-84": 0, "GCJ-02": 0, "BD-09": 0}
    for nm, lo, la in scored:
        ds = {"WGS-84": dist_m(la, lo, wgs_lat, wgs_lon),
              "GCJ-02": dist_m(la, lo, gcj_lat, gcj_lon),
              "BD-09": dist_m(la, lo, bd_lat, bd_lon)}
        best = min(ds, key=ds.get)
        wins[best] += 1
        print(f"  {nm[:18]:18s} → {best} "
              f"(WGS {ds['WGS-84']:.0f}m / GCJ {ds['GCJ-02']:.0f}m / BD {ds['BD-09']:.0f}m)")
    print(f"\n判定: {wins} → 数据坐标系 = {max(wins, key=wins.get)}")


if __name__ == "__main__":
    main()
