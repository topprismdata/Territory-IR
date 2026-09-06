"""合成数据集上的全管线测试（完全密闭，不依赖任何本地私有数据，可在任何机器与CI秒级运行）。"""

import pytest

from server import Copilot
from territory_ir.dataset import Dataset
from territory_ir.session import Session
from tests.synthetic_fixture import make_synthetic_dataset


@pytest.fixture
def syn_env(tmp_path):
    data_dir = make_synthetic_dataset(tmp_path)
    ds = Dataset(
        data_dir=str(data_dir),
        roadnet_path=str(data_dir / "roadnet.geojson"),
        streets_path=str(data_dir / "streets.geojson"),
        osm_path=str(data_dir / "osm.json"),
        name="synthetic",
    )
    sess_dir = tmp_path / "sessions"
    sess = Session(ds, persist_dir=str(sess_dir))
    return ds, sess, data_dir, sess_dir


def test_synthetic_session_import_and_describe(syn_env):
    ds, sess, _, _ = syn_env
    ring = [[113.1, 23.0], [113.2, 23.0], [113.2, 23.2], [113.1, 23.2], [113.1, 23.0]]
    fence = sess.import_ring("测试导入", ring)
    assert fence["name"] == "测试导入"
    assert fence["km2"] > 0
    assert len(fence["pieces"]) > 0


def test_synthetic_session_merge(syn_env):
    ds, sess, _, _ = syn_env
    # 导入两个相邻围栏
    ring1 = [[113.0, 23.0], [113.1, 23.0], [113.1, 23.2], [113.0, 23.2], [113.0, 23.0]]
    ring2 = [[113.1, 23.0], [113.2, 23.0], [113.2, 23.2], [113.1, 23.2], [113.1, 23.0]]
    sess.import_ring("左块", ring1)
    sess.import_ring("右块", ring2)
    assert len(sess.fences) == 2

    # 零副作用预览
    merged = sess.merge_preview(["左块", "右块"])
    assert "左块+右块" in merged["name"]
    assert len(sess.fences) == 2  # 未变

    # 提交合并
    sess.merge_commit()
    assert len(sess.fences) == 1
    assert "左块+右块" in sess.fences[0]["name"]


def test_synthetic_copilot_chat_and_api(syn_env, monkeypatch):
    ds, _, data_dir, sess_dir = syn_env
    # 模拟 Dataset.guangzhou 指向合成数据目录，验证 Copilot 真实对话分发
    monkeypatch.setattr(Dataset, "guangzhou", classmethod(lambda cls, data_dir: ds))
    cp = Copilot(data_dir=data_dir, persist_dir=sess_dir)
    ring = [[113.0, 23.0], [113.2, 23.0], [113.2, 23.2], [113.0, 23.2], [113.0, 23.0]]
    cp.sess.import_ring("总区", ring)

    # 验证描述指令
    r_desc = cp.chat("描述 总区")
    assert "总区" in r_desc["reply"]

    # 验证清空指令
    r_clear = cp.chat("清空全部")
    assert "已清空" in r_clear["reply"]
    assert len(cp.sess.fences) == 0
