"""llm.py 真 omlx 协议兼容测试 (第四轮: 必须用真 LLM)

通过测试驱动修复: 验证 llm.chat 能跟本地 omlx (OpenAI 兼容) 通信。
需要本地 omlx 服务跑在 127.0.0.1:1234, 模型 Qwen3.8-27B-MLX-4bit。
"""
import json
import socket
import time
import urllib.request

import pytest


# ---------- 系统代理 bypass ----------
@pytest.fixture(autouse=True)
def bypass_proxy(monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
             "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPHandler(),
    )
    urllib.request.install_opener(opener)
    yield


def _omlx_available(port=1234):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


OMLX_OK = _omlx_available()


@pytest.fixture(scope="module")
def omlx_config_path(tmp_path_factory):
    cfg = {
        "url": "http://127.0.0.1:1234/v1",
        "key": "12345678",
        "model": "Qwen3.8-27B-MLX-4bit",
        "api": "openai",
    }
    p = tmp_path_factory.mktemp("data") / "llm_config.json"
    p.write_text(json.dumps(cfg))
    return p


# ---------- omlx 探测 ----------
class TestOmixDiscovery:

    def test_list_models(self):
        if not OMLX_OK:
            pytest.skip("omlx 未运行")
        req = urllib.request.Request(
            "http://127.0.0.1:1234/v1/models",
            headers={"Authorization": "Bearer 12345678"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        models = [m["id"] for m in data["data"]]
        assert "Qwen3.8-27B-MLX-4bit" in models

    def test_chat_completions_endpoint_works(self):
        if not OMLX_OK:
            pytest.skip("omlx 未运行")
        req = urllib.request.Request(
            "http://127.0.0.1:1234/v1/chat/completions",
            data=json.dumps({
                "model": "Qwen3.8-27B-MLX-4bit",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 20
            }).encode(),
            headers={
                "Authorization": "Bearer 12345678",
                "Content-Type": "application/json",
            })
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        elapsed = time.time() - t0
        content = data["choices"][0]["message"]["content"]
        assert content
        print(f"\n[omlx 实测] {elapsed:.1f}s: {content[:80]}")


# ---------- llm.chat 走 omlx ----------
@pytest.mark.skipif(not OMLX_OK, reason="omlx 未运行")
class TestChatWithOmix:

    def test_chat_returns_string(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import chat
        t0 = time.time()
        resp = chat("用一句话介绍广州", data_dir="/nonexistent", timeout=60)
        elapsed = time.time() - t0
        assert isinstance(resp, str)
        assert len(resp) > 0
        print(f"\n[llm.chat omlx] {elapsed:.1f}s: {resp[:80]}")

    def test_chat_json_extractable(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import chat, extract_json
        prompt = (
            '请严格输出 JSON, 不要其他文字. '
            '格式: {"action": "describe", "target": "围栏A"}'
        )
        resp = chat(prompt, data_dir="/nonexistent", timeout=60)
        intent = extract_json(resp)
        assert intent["action"] == "describe"
        assert intent["target"] == "围栏A"
        print(f"\n[llm.chat omlx JSON] {intent}")

    def test_parse_intent_describe(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent("描述所有围栏", "/nonexistent",
                              ["围栏A", "围栏B"])
        assert intent["action"] == "describe", f"实际: {intent}"

    def test_parse_intent_clear(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent("删除围栏A", "/nonexistent", ["围栏A"])
        assert intent["action"] == "clear", f"实际: {intent}"

    def test_parse_intent_clear_all(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent("清空所有围栏", "/nonexistent", ["A"])
        assert intent["action"] == "clear", f"实际: {intent}"

    def test_parse_intent_merge(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent("合并 A 和 B", "/nonexistent", ["A", "B"])
        assert intent["action"] == "merge", f"实际: {intent}"
        targets = intent.get("targets", [])
        assert "A" in targets and "B" in targets

    def test_parse_intent_fence_from_text(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent(
            "联和街道全域, 北至广汕公路建一个围栏",
            "/nonexistent", [])
        assert intent["action"] == "fence_from_text", f"实际: {intent}"
        assert "联和街道" in intent.get("areas", [])

    def test_parse_intent_expand(self, omlx_config_path, monkeypatch):
        monkeypatch.setenv("TIR_LLM_CONFIG", str(omlx_config_path))
        from territory_ir.llm import parse_intent
        intent = parse_intent(
            "把围栏A向西扩展到华南快速", "/nonexistent", ["围栏A"])
        assert intent["action"] == "expand", f"实际: {intent}"
        assert intent["dir"] == "west"
        assert "华南快速" in intent.get("road", "")
