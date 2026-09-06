"""coords.py 单元测试:GCJ-02 ⇄ WGS-84 转换

覆盖:
- WGS→GCJ→WGS 往返精度(中国大陆点 < 1m)
- GCJ→WGS→GCJ 往返精度
- 境外点(out_of_china)原样返回,不被偏移
- 边界纬度(0.8° / 55.8°)正确判定
- 边界经度(72° / 137.8°)正确判定
- 矢量版本与标量版本结果一致
- convert() 单点自动方向
"""

import math

import pytest

from territory_ir.coords import (
    convert,
    gcj2wgs,
    gcj2wgs_vec,
    out_of_china,
    wgs2gcj,
    wgs2gcj_vec,
)

# ---------- 已知参考点(网上权威验证) ----------
BEIJING_WGS = (116.397, 39.916)  # 天安门
SHANGHAI_WGS = (121.473, 31.230)  # 人民广场
URUMQI_WGS = (87.617, 43.825)  # 乌鲁木齐(偏远,验证偏移公式一致)
HONG_KONG_WGS = (114.158, 22.286)  # 香港(GCJ 不适用,但在境内框)
NEW_YORK_WGS = (-74.006, 40.712)  # 纽约(完全境外)
SYDNEY_WGS = (151.209, -33.868)  # 悉尼(南半球境外)


def _shift_m(p1, p2):
    """两点近似距离(米)"""
    return math.hypot(
        (p1[0] - p2[0]) * 92_000 * math.cos(math.radians(p1[1])),
        (p1[1] - p2[1]) * 111_000,
    )


# ---------- 往返精度 ----------
class TestRoundTrip:
    def test_wgs_to_gcj_to_wgs_china(self):
        """国内点往返应回到原坐标 < 1m"""
        for label, p in [
            ("北京", BEIJING_WGS),
            ("上海", SHANGHAI_WGS),
            ("乌鲁木齐", URUMQI_WGS),
        ]:
            gcj = wgs2gcj(*p)
            back = gcj2wgs(*gcj)
            shift = _shift_m(p, back)
            assert shift < 1.0, f"{label} 往返 {shift:.3f}m 超过 1m"

    def test_gcj_to_wgs_to_gcj_china(self):
        """反向也是稳定不动点"""
        gcj = wgs2gcj(*BEIJING_WGS)
        back_gcj = wgs2gcj(*gcj2wgs(*gcj))
        assert _shift_m(gcj, back_gcj) < 0.01

    def test_known_offset_magnitude(self):
        """国内点 GCJ 偏移应在 100-700m 之间(中国法定偏移公式)"""
        gcj = wgs2gcj(*BEIJING_WGS)
        shift = _shift_m(BEIJING_WGS, gcj)
        assert 100 < shift < 800, f"北京偏移 {shift:.1f}m 不在预期范围"


# ---------- 境外点 ----------
class TestOutOfChina:
    @pytest.mark.parametrize("p", [NEW_YORK_WGS, SYDNEY_WGS, (0.0, 0.0), (200.0, 50.0)])
    def test_out_of_china_returns_original(self, p):
        """境外点 wgs2gcj 不应被偏移"""
        assert out_of_china(*p) is True
        assert wgs2gcj(*p) == p
        assert gcj2wgs(*p) == p

    @pytest.mark.parametrize(
        "p", [BEIJING_WGS, SHANGHAI_WGS, URUMQI_WGS, HONG_KONG_WGS]
    )
    def test_china_points_in_range(self, p):
        """境内点应在判定框内"""
        assert out_of_china(*p) is False


# ---------- 边界值 ----------
class TestBoundaries:
    """中国经纬度判定框 [72-137.8, 0.8-55.8] 边界"""

    def test_west_boundary_lon_72(self):
        assert out_of_china(72.0, 35.0) is False
        assert out_of_china(71.99, 35.0) is True

    def test_east_boundary_lon_137_8(self):
        assert out_of_china(137.8, 35.0) is False
        assert out_of_china(137.81, 35.0) is True

    def test_south_boundary_lat_0_8(self):
        assert out_of_china(110.0, 0.8) is False
        assert out_of_china(110.0, 0.79) is True

    def test_north_boundary_lat_55_8(self):
        assert out_of_china(110.0, 55.8) is False
        assert out_of_china(110.0, 55.81) is True

    def test_corner_inside(self):
        """四角都应在框内(中国全境)"""
        assert out_of_china(73.0, 1.0) is False  # 西南角附近
        assert out_of_china(135.0, 53.0) is False  # 东北角


# ---------- 矢量 vs 标量 ----------
class TestVectorConsistency:
    def test_vec_matches_scalar(self):
        """wgs2gcj_vec 应与逐点 wgs2gcj 一致"""
        pts = [BEIJING_WGS, SHANGHAI_WGS, URUMQI_WGS, (110.0, 30.0)]
        scalar = [wgs2gcj(*p) for p in pts]
        import numpy as np

        lons = np.array([p[0] for p in pts])
        lats = np.array([p[1] for p in pts])
        v_lon, v_lat = wgs2gcj_vec(lons, lats)
        for (sx, sy), vx, vy in zip(scalar, v_lon, v_lat, strict=True):
            assert abs(sx - vx) < 1e-9
            assert abs(sy - vy) < 1e-9

    def test_gcj2wgs_vec_matches_scalar(self):
        pts = [wgs2gcj(*p) for p in [BEIJING_WGS, SHANGHAI_WGS]]
        import numpy as np

        lons = np.array([p[0] for p in pts])
        lats = np.array([p[1] for p in pts])
        v_lon, v_lat = gcj2wgs_vec(lons, lats)
        for (sx, sy), vx, _vy in zip(pts, v_lon, v_lat, strict=True):
            scalar_x, scalar_y = gcj2wgs(sx, sy)
            assert abs(scalar_x - vx) < 1e-9


# ---------- convert 自动方向 ----------
class TestConvert:
    def test_to_gcj(self):
        gcj = convert(BEIJING_WGS, to_wgs=False)
        assert _shift_m(gcj, wgs2gcj(*BEIJING_WGS)) < 0.01

    def test_to_wgs(self):
        gcj = wgs2gcj(*BEIJING_WGS)
        back = convert(gcj, to_wgs=True)
        assert _shift_m(back, BEIJING_WGS) < 0.01

    def test_overseas_passthrough(self):
        """convert 对境外点原样返回,不调公式"""
        for p in [NEW_YORK_WGS, SYDNEY_WGS]:
            assert convert(p, to_wgs=True) == p
            assert convert(p, to_wgs=False) == p
