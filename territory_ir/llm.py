"""TerritoryIR LLM 客户端：自然语言 → 结构化意图。

配置来源（优先级）：
1. 环境变量 TIR_LLM_CONFIG 指向的 JSON：{"url","key","model"}
2. 默认 <data_dir>/llm_config.json
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path


_DEFAULT_CONF = Path.home() / ".claude" / "settings.json"


def load_config(data_dir) -> dict:
    """配置优先级：$TIR_LLM_CONFIG → <data_dir>/llm_config.json → ~/.claude/settings.json"""
    p = os.environ.get("TIR_LLM_CONFIG")
    candidates = ([Path(p)] if p else
                  [_DEFAULT_CONF, Path(data_dir) / "llm_config.json"])
    for path in candidates:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if "env" in raw:
                env = raw["env"]
                return {"url": env["ANTHROPIC_BASE_URL"].rstrip("/"),
                        "key": env["ANTHROPIC_AUTH_TOKEN"],
                        "model": os.environ.get("TIR_LLM_MODEL", "MiniMax-M3")}
            return {"url": raw["url"].rstrip("/"),
                    "key": raw["key"], "model": raw["model"]}
    raise FileNotFoundError(f"LLM 配置不存在: {[str(c) for c in candidates]}")


def _open(req, timeout):
    """标准证书验证；失败（企业环境缺 CA）降级为不验证。"""
    import ssl
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def chat(prompt: str, data_dir, timeout: int = 90) -> str:
    cfg = load_config(data_dir)
    req = urllib.request.Request(
        cfg["url"] + "/v1/messages",
        data=json.dumps({"model": cfg["model"], "max_tokens": 2048,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json",
                 "x-api-key": cfg["key"],
                 "Authorization": "Bearer " + cfg["key"],
                 "anthropic-version": "2023-06-01"})
    r = json.load(_open(req, timeout))
    return "".join(b.get("text", "") for b in r.get("content", [])
                   if b.get("type") == "text").strip()


def extract_json(text: str) -> dict:
    m = re.search(r"\{", text)
    if not m:
        raise ValueError(f"LLM 未返回 JSON: {text[:120]}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[m.start():])
        return obj
    except json.JSONDecodeError:
        m2 = re.search(r"\{.*\}", text, re.S)
        if not m2:
            raise ValueError(f"LLM 未返回 JSON: {text[:120]}")
        return json.loads(m2.group(0))


def parse_intent(text: str, data_dir, fence_names: list) -> dict:
    """自然语言 → 动作意图。

    describe / fence_from_text / split / merge / unknown
    """
    text = text.replace("@", "")
    names = "\n".join(fence_names) or "（暂无）"
    prompt = (
        "你是领地围栏助手。把用户指令解析为 JSON，只输出 JSON。\n"
        '动作一 描述围栏: {"action":"describe","target":"围栏名子串"}\n'
        '动作二 文字建围栏: {"action":"fence_from_text","name":"简短围栏名",'
        '"areas":["街道名",...],"bounds":{"北":"路名","南":"路名"}}\n'
        "  - areas 只填城市里的**街道名**；bounds 键=方向界（北界=区域在路南），"
        "没有的方向不要编\n"
        '动作三 沿路切分: {"action":"split","target":"围栏名子串",'
        '"road":"路名","side":"west|east|south|north"}\n'
        "  - side=用户**说到的**那一侧；只说\"切成南北/东西两块\"没指定哪侧时填 \"north\"\n"
        "  - 国道编号（如 g324）如实填入 road\n"
        '动作四 合并: {"action":"merge","targets":["围栏A子串","围栏B子串"]}\n'
        '动作五 片条款建围栏: {"action":"fence_from_terms","name":"名","terms":["凤凰街道","新塘街道沿天顺路"]}\n'
        '动作六 扩展: {"action":"expand","target":"围栏名子串","dir":"west|east|south|north","road":"界路名"}\n'
        '动作七 走廊建围栏: {"action":"corridor","name":"名","roads":["广河高速","京港澳高速"],"km":3}\n'
        '动作八 三路围合: {"action":"enclosed","name":"名","roads":["路A","路B","路C"]}\n'
        "  - 用于「三条互相交叉的路围出一个区域」——roads 恰好 3 条\n"
        "  - 用于「沿X路、Y路（合成/围出）一个区域」——沿多条路沿线取走廊带\n"
        "  - 高速/国道/大道路名不是街道名，绝不要填进 areas\n"
        '  - 例：「把A向西扩展到华南快速」→ dir=west, road=华南快速\n'
        '动作五 删除: {"action":"clear","target":"围栏名子串或空(空=全部)"}\n'
        '无法判断: {"action":"unknown","reason":"一句话"}\n\n'
        f"当前围栏清单:\n{names}\n\n用户指令: {text}"
    )
    # 确定性直通：粘贴人话（| ; ； ｜ ／ 任一分隔）+ 生成围栏
    norm = text.replace("｜", "|").replace("；", ";").replace("／", "|")
    if "|" in norm or ";" in norm:
        norm = norm.replace(";", "|")
        terms = [x.strip() for x in norm.split("|") if x.strip()]
        name = "条款围栏"
        if terms and ("围栏" in terms[-1] or "生成" in terms[-1]):
            cleaned = terms[-1].replace("生成围栏", "").replace("生成", "").strip()
            terms = terms[:-1] + ([cleaned] if cleaned else [])
            name = "条款围栏"
        if terms:
            return {"action": "fence_from_terms", "name": name, "terms": terms}

    reply = ""
    for _ in range(2):  # LLM 空回复重试一次
        reply = chat(prompt, data_dir)
        if reply.strip():
            break
    intent = extract_json(reply)
    intent.setdefault("action", "unknown")
    return intent
