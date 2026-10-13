"""WP11 路名词表单源：roadsem 模块行为锁定。"""

from territory_ir.roadsem import (
    DIR_KEEP,
    RING_WORDS,
    core_candidates,
    is_ring_name,
    load_aliases,
    match_in_text,
    norm_name,
)


def test_norm_name_全形态归一():
    assert norm_name("G324 国道") == "g324国道"
    assert norm_name("上塘高架路") == "上塘高架路"
    assert norm_name("Shang Tang-高架") == "shangtang高架"


def test_core_candidates_后缀裁剪():
    cands = list(core_candidates("上塘高架路"))
    assert cands[0] == "上塘高架路"
    assert "上塘高架" in cands and "上塘" in cands
    assert all(len(c) >= 2 for c in cands)


def test_match_in_text_两侧仓语义():
    # SRAF llm._in_text 的原始用例
    assert match_in_text("上塘高架路", "西至「上塘高架」")
    assert match_in_text("G2504", "G2504以南")
    assert not match_in_text("中河高架", "只提上塘高架的地方")


def test_is_ring_name_关键词与编号():
    assert is_ring_name("杭州绕城高速")
    assert is_ring_name("华南快速路")
    assert is_ring_name("g2504")  # 编号大小写不敏感
    assert not is_ring_name("上塘高架路")  # 高架≠环类（保持 SRAF 原语义）


def test_dir_keep_方向反转表():
    assert DIR_KEEP["南"] == "north" and DIR_KEEP["北"] == "south"
    assert set(RING_WORDS) >= {"绕城", "高速"}


def test_load_aliases_跳说明键并归一(tmp_path):
    f = tmp_path / "aliases.json"
    f.write_text(
        '{"_说明":"x","G324":"广汕公路","华南快速干线":"华南快速"}', encoding="utf-8"
    )
    a = load_aliases(f)
    assert a == {"g324": "广汕公路", "华南快速干线": "华南快速"}
