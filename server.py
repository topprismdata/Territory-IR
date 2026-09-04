#!/usr/bin/env python3
"""TerritoryIR Copilot 服务：左地图 + 右 LLM 对话。

    python3 server.py [--port 8802] [--data data/gz]

API:
  GET  /api/state                  → {fences:[...], pending: {...}|None}
  POST /api/import  {name, geojson}→ 导入围栏（编译+人话）
  POST /api/chat    {text}         → LLM 解析意图并执行/出预览
  POST /api/apply                  → 应用挂起的预览
  POST /api/discard                → 放弃挂起的预览
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from territory_ir.dataset import Dataset          # noqa: E402
from territory_ir import session as sess_mod      # noqa: E402
from territory_ir import llm as tir_llm           # noqa: E402

WEB = ROOT / "web"
DATA = Path(__file__).resolve().parent.parent / "sales-data" / "gz"


import re as _re

_DIR = {"东": "east", "西": "west", "南": "south", "北": "north"}


def _fast_intent(text: str):
    """常见句式的确定性解析（毫秒级）。返回 None = 交给 LLM。"""
    t = text.replace("@", " ").replace("｜", "|").replace("；", ";").replace("／", "|")

    # 条款直通（| 或 ; 分隔的条款串）
    if ("|" in t or ";" in t) and len(t.split("|")) + len(t.split(";")) > 4:
        terms = [x.strip() for x in _re.split(r"[|;]", t) if x.strip()]
        if terms:
            return {"action": "fence_from_terms", "name": "条款围栏", "terms": terms}

    # 描述
    m = _re.search(r"描述\s*(.*)", t)
    if m and ("描述" in t[:2]):
        return {"action": "describe", "target": m.group(1).strip()}

    # 合并
    m = _re.search(r"(?:把|将)?\s*(.+?)\s*(?:和|与|跟)\s*(.+?)\s*合并", t)
    if m:
        return {"action": "merge",
                "targets": [m.group(1).strip(), m.group(2).strip()]}

    # 删除/清空
    m = _re.search(r"(?:删除|清空)\s*(.*)", t)
    if m:
        return {"action": "clear",
                "target": "" if ("全部" in t or "所有" in t or not m.group(1).strip())
                else m.group(1).strip()}

    # 扩展
    m = _re.search(r"把\s*(.+?)向([东南西北])扩展到\s*(.+)", t)
    if m:
        return {"action": "expand", "target": m.group(1).strip(),
                "dir": _DIR[m.group(2)], "road": m.group(3).strip()}

    # 沿路切分：「A 沿着X切成南北2部分」「沿X分开 西半边」
    m = _re.search(r"(?:把\s*)?(.+?)沿[着]?\s*(.+?)(?:切成|分割为|分为|分成|分开|一分为二)\s*(.*)", t)
    if m:
        target = m.group(1).strip()
        road = m.group(2).strip()
        rest = m.group(3) or ""
        side = "north"
        for w, sd in _DIR.items():
            if w in rest or w in road:
                side = sd
                break
        return {"action": "split", "target": target, "road": road, "side": side}
    return None


class Copilot:
    def __init__(self, data_dir: Path):
        self.ds = Dataset.guangzhou(data_dir=str(data_dir))
        self.sess = sess_mod.Session(self.ds, persist_dir=str(ROOT / "sessions"))
        self.sess.load()
        self.pending = None   # {"kind":"split"|"merge", "result":[fence...], "removed":[...], "desc":str}

    # ---------- 动作 ----------
    def state(self):
        return {"fences": self.sess.public(), "pending": self._pending_public()}

    def _pending_public(self):
        if not self.pending:
            return None
        p = self.pending
        result = ([self.sess.pub(f) for f in p["result"]]
                  if p.get("result") else [])
        removed = ([f["name"] for f in p["removed"]]
                   if p.get("removed") and isinstance(p["removed"][0], dict)
                   else p.get("removed", []))
        return {"kind": p["kind"], "desc": p["desc"], "result": result,
                "removed": removed}

    def chat(self, text: str, emit=None) -> dict:
        step = (lambda msg: emit(msg)) if emit else (lambda msg: None)
        step(f"收到指令：「{text[:40]}{'…' if len(text) > 40 else ''}」")
        fast = _fast_intent(text)
        if fast is not None:
            step("⚡ 规则直通（跳过 LLM）")
            intent = fast
        else:
            step("🧠 LLM 解析意图…")
        if fast is None:
            intent = tir_llm.parse_intent(
                text, str(self.ds.data_dir),
                {"fence_names": [f["name"] for f in self.sess.fences]})
        act = intent["action"]
        step(f"📋 意图 = {act}")
        reply, focus, pending = "", None, None
        try:
            if act == "describe":
                step("📖 编译围栏 → 真值片 + 条款回放…")
                tgt = (intent.get("target") or "").strip()
                ALL = ("所有围栏", "全部", "所有", "all", "")
                if tgt and tgt not in ALL:
                    try:
                        targets = [self.sess.find(tgt)]
                    except ValueError:
                        targets = list(self.sess.fences)  # 目标对不上→描述全部
                else:
                    targets = list(self.sess.fences)
                if not targets:
                    reply = "当前没有围栏。先点「⇪ 导入围栏文件」或用文字建一个。"
                else:
                    for f in targets:
                        self.sess.compile(f)   # 刷新 terms/engine_terms
                    self.sess.save()
                    parts = []
                    for f in targets:
                        parts.append("**" + f["name"] + "**（" + str(f["km2"])
                                     + " km²，" + str(len(f["pieces"] or []))
                                     + " 片）  \n人话："
                                     + (" | ".join(f["terms"]) or "（无）")
                                     + "  \n复现条款（粘贴可重建围栏）："
                                     + " | ".join(f.get("engine_terms") or []))
                    reply = "\n\n".join(parts)
            elif act == "fence_from_text":
                step(f"🧩 语义构面：{intent.get('areas')} ∩ 方向界 → 片集合…")
                name = intent.get("name") or "新围栏"
                f = self.sess.fence_from_text(
                    name, intent.get("areas") or [], intent.get("bounds") or {})
                focus = f["id"]
                reply = (f"已按语义建围栏 **{f['name']}**（{f['km2']} km²，"
                         f"{len(f['pieces'])} 片）  \n人话：{' | '.join(f['terms'])}")
            elif act == "fence_from_terms":
                step(f"🧩 条款回放：{len(intent.get('terms') or [])} 条 → 片集合…")
                name = intent.get("name") or "条款围栏"
                f = self.sess.fence_from_terms(name, intent.get("terms") or [])
                focus = f["id"]
                skipped = f.pop("_skipped", [])
                reply = (f"已按条款建围栏 **{f['name']}**（{f['km2']} km²，"
                         f"{len(f['pieces'])} 片）  \n人话："
                         + (" | ".join(f["terms"]) or "（无）"))
                if skipped:
                    reply += f"  \n（界带条款已忽略：{'; '.join(skipped)}）"
            elif act == "corridor":
                step(f"🧩 沿路走廊带（{intent.get('km', 3)}km）→ 片集合…")
                f = self.sess.corridor(intent.get("roads") or [],
                                       float(intent.get("km", 3)),
                                       intent.get("name") or "走廊围栏")
                focus = f["id"]
                reply = (f"已沿「{'、'.join(intent.get('roads') or [])}」建围栏 "
                         f"**{f['name']}**（{f['km2']} km²，{f['pieces']} 片）  \n"
                         f"人话：{' | '.join(f['terms'])}")
            elif act == "enclosed":
                roads = intent.get("roads") or []
                step(f"🧩 三路围合：两两交点 → 围合多边形 → 片集合…")
                f, tri = self.sess.enclosed_region(roads, intent.get("name") or "三路围合")
                focus = f["id"]
                tri_pts = "、".join(f"({cx:.3f},{cy:.3f})" for cx, cy in tri.exterior.coords[:3])
                reply = (f"已按「{'、'.join(roads)}」围合建区域 **{f['name']}**"
                         f"（{f['km2']} km²，{f['pieces']} 片）  \n"
                         f"围合三角顶点：{tri_pts}")
            elif act == "expand":
                step(f"🧩 扩展相邻片（{intent.get('dir')}侧 → {intent.get('road')}）…")
                f, added = self.sess.expand(intent.get("target", ""),
                                            intent.get("dir", "west"),
                                            intent.get("road", ""))
                focus = f["id"]
                dir_cn = {"west": "西", "east": "东",
                          "south": "南", "north": "北"}[intent.get("dir", "west")]
                reply = (f"**{f['name']}** 已向{dir_cn}扩展到「{intent.get('road')}」"
                         f"：新增 {added} 片，现 {f['km2']} km² / "
                         f"{len(f['pieces'])} 片  \n人话：{' | '.join(f['terms'])}")
            elif act == "clear":
                step("🗑 移除围栏…")
                tgt = (intent.get("target") or "").strip()
                n = self.sess.clear(tgt or None)
                reply = (f"已删除「{tgt}」。" if tgt else f"已清空全部 {n} 个围栏。")
            elif act == "split":
                step(f"✂️ 沿「{intent.get('road')}」按片质心分堆（{intent.get('side')}侧）…")
                f1, f2 = self.sess.split(intent.get("target", ""),
                                         intent.get("road", ""),
                                         intent.get("side", "west"))
                self.pending = {"kind": "split", "result": [f1, f2],
                                "removed": [], "desc": intent.get("road", "")}
                pending = self._pending_public()
                focus = f1["id"]
                reply = (f"沿「{intent.get('road')}」切分预览："
                         f"**{f1['name']}** {f1['km2']} km² ＋ "
                         f"**{f2['name']}** {f2['km2']} km²。确认后点「应用」。")
            elif act == "merge":
                tg = intent.get("targets") or []
                step(f"🔗 片并集合并 {len(tg)} 个围栏…")
                fs = [self.sess.find(s) for s in tg]
                removed = [dict(name=f["name"], id=f["id"]) for f in fs]
                self.pending = {"kind": "merge", "result": None,
                                "removed": [f["name"] for f in fs],
                                "desc": "+".join(f["name"] for f in fs)}
                pending = self._pending_public()
                reply = (f"合并预览：{' ＋ '.join(f['name'] for f in fs)}"
                         f"（{len(fs)} 个围栏）。确认后点「应用」。")
            else:
                reply = ("没理解这个指令。可以试试：导入围栏、"
                         "「描述 @围栏」、「联和街道全域，北至广汕公路 建围栏」、"
                         "「沿花莞高速分开 西半边」、「把 A 和 B 合并」。")
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            reply = f"✗ {e}"
        return {"reply": reply, "focus": focus, "pending": pending,
                "state": self.state()}

    def apply(self):
        if not self.pending:
            return {"reply": "没有待应用的预览。"}
        p = self.pending
        if p["kind"] == "split":
            self.sess.fences += p["result"]
        else:
            merged = self.sess.merge(p["removed"])  # removed 存的是名字
            p["result"] = [merged]
        self.sess.save()
        names = "、".join(f["name"] for f in p["result"])
        self.pending = None
        return {"reply": f"已应用：{names}", "state": self.state()}

    def discard(self):
        self.pending = None
        return {"reply": "已放弃预览。", "state": self.state()}

    def import_geo(self, name, geo):
        fs = self.sess.import_geojson(name, geo)
        terms = " | ".join(fs[0]["terms"]) if fs and fs[0]["terms"] else "（库外区域，无片级描述）"
        return {"reply": (f"已导入 **{fs[0]['name']}**"
                          f"{'等 %d 个围栏' % len(fs) if len(fs) > 1 else ''}"
                          f"（{fs[0]['km2']} km²，{len(fs[0]['pieces'])} 片）"
                          f"  \n人话：{terms}"),
                "focus": fs[0]["id"] if fs else None, "state": self.state()}


def make_handler(cp: Copilot, index_html: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 静默
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = (json.dumps(body, ensure_ascii=False).encode()
                    if not isinstance(body, (str, bytes)) else
                    (body.encode() if isinstance(body, str) else body))
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, index_html, "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send(200, cp.state())
            elif self.path.startswith("/static/"):
                # web/ 目录静态文件（路径穿越防护）
                name = Path(self.path[len("/static/"):]).name
                f = WEB / name
                if f.exists():
                    ctype = ("application/javascript"
                             if f.suffix == ".js" else
                             "text/css" if f.suffix == ".css" else
                             "image/x-icon" if f.suffix == ".ico" else
                             "application/octet-stream")
                    self._send(200, f.read_bytes(), ctype)
                else:
                    self._send(404, "not found", "text/plain")
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else {}
            if self.path == "/api/chat":
                self._send(200, cp.chat(str(body.get("text", ""))))
            elif self.path == "/api/chat/stream":
                # SSE: 逐步推送处理过程，结束推 done
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                def emit(msg):
                    try:
                        self.wfile.write(f"data: {json.dumps({'type':'step','text':msg}, ensure_ascii=False)}\n\n".encode())
                        self.wfile.flush()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    r = cp.chat(str(body.get("text", "")), emit=emit)
                    self.wfile.write(f"data: {json.dumps({'type':'done', **r}, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                except Exception as e:  # noqa: BLE001
                    self.wfile.write(f"data: {json.dumps({'type':'done','reply':f'✗ {e}'}, ensure_ascii=False)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            elif self.path == "/api/import":
                try:
                    self._send(200, cp.import_geo(
                        str(body.get("name", "导入围栏")), body.get("geojson")))
                except Exception as e:  # noqa: BLE001
                    self._send(400, {"error": str(e)})
            elif self.path == "/api/apply":
                self._send(200, cp.apply())
            elif self.path == "/api/discard":
                self._send(200, cp.discard())
            elif self.path == "/api/clear":
                n = cp.sess.clear(None)
                self._send(200, {"reply": f"已清空全部 {n} 个围栏。",
                                 "state": cp.state()})
            else:
                self._send(404, {"error": "not found"})
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--data", default=str(ROOT.parent / "sales-data" / "gz"))
    a = ap.parse_args()
    data_dir = Path(a.data)
    if not data_dir.exists():
        alt = Path(__file__).resolve().parent.parent / "sales-resource-allocation-framework" / "data" / "gz"
        if alt.exists():
            data_dir = alt
    cp = Copilot(data_dir)
    index_html = (WEB / "index.html").read_text(encoding="utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(cp, index_html))
    print(f"TerritoryIR Copilot: http://127.0.0.1:{a.port}  "
          f"(data={data_dir}, fences={len(cp.sess.fences)})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
