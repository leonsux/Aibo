"""
游戏搭子 AI - 核心后端
功能：定时截图 → 阿里云百炼 Vision 分析 → 生成热情鼓励评论
支持：阿里云百炼 DashScope（OpenAI 兼容格式）
"""

import openai
import base64
import json
import time
import threading
import queue
import tempfile
import os
import io
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from PIL import ImageGrab, Image

# ─── 配置 ──────────────────────────────────────────────────
DASHSCOPE_API_KEY = ""           # 填入你的百炼 API Key，或在界面里填
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = "qwen-vl-max"  # 支持视觉的模型，可换 qwen-vl-plus 更省费用
SCREENSHOT_INTERVAL = 30         # 截图间隔（秒）
MAX_IMAGE_SIZE = (1280, 720)     # 压缩到此尺寸再发给模型（省 token）
PORT = 7788                      # 本地服务器端口

# ─── TTS 声音配置 ───────────────────────────────────────────
# 模型：cosyvoice-v3-flash（支持 Instruct 情感/场景控制）
# 音色：longanhuan 龙安欢 · 欢脱元气女 20~30岁
#
# 支持场景：闲聊对话、比赛解说、深夜电台广播、剧情解说
#           诗歌朗诵、科普知识推广、产品推广、脱口秀表演
# 支持情感：neutral、fearful、angry、sad、surprised、happy、disgusted
TTS_VOICE = "longanhuan"
TTS_MODEL = "cosyvoice-v3-flash"

# 评论类型 → (场景, 情感) 映射，让声音配合评论内容
_TYPE_INSTRUCT = {
    "鼓励": ("比赛解说",   "happy"),
    "调侃": ("脱口秀表演", "happy"),
    "分析": ("比赛解说",   "neutral"),
    "感叹": ("闲聊对话",   "surprised"),
}
# ──────────────────────────────────────────────────────────

# ─── TTS 语音朗读 ──────────────────────────────────────────
_speak_queue = queue.Queue()

def _tts_worker():
    while True:
        item = _speak_queue.get()
        if item is None:
            break
        text, api_key, voice, comment_type = item
        try:
            _do_speak_dashscope(text, api_key, voice, comment_type)
        except Exception as e:
            print(f"[TTS] 合成失败，降级到系统 TTS: {e}")
            _do_speak_system(text)
        finally:
            _speak_queue.task_done()


def _build_instruction(comment_type: str) -> str:
    """根据评论类型生成 Instruct 指令字符串"""
    scene, emotion = _TYPE_INSTRUCT.get(comment_type, ("闲聊对话", "happy"))
    return f"你正在进行{scene}，你说话的情感是{emotion}。"


def _do_speak_dashscope(text: str, api_key: str, voice: str = TTS_VOICE, comment_type: str = "鼓励"):
    """用 dashscope SDK + Instruct 合成有情感的语音"""
    import ssl
    import dashscope
    from dashscope.audio.tts_v2 import SpeechSynthesizer

    # 修复 macOS Python SSL 证书问题
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = ssl.create_default_context()
    ssl._create_default_https_context = lambda: ssl_ctx

    instruction = _build_instruction(comment_type)
    print(f"[TTS] {comment_type} | {instruction}")

    dashscope.api_key = api_key
    synthesizer = SpeechSynthesizer(
        model=TTS_MODEL,
        voice=voice,
        instruction=instruction,   # 控制情感/场景，不会被朗读出来
        speech_rate=1.05,
    )
    audio = synthesizer.call(text)

    if not audio:
        raise RuntimeError("TTS 返回空音频")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio)
        tmp_path = f.name
    try:
        _play_audio(tmp_path)
    finally:
        os.unlink(tmp_path)


def _play_audio(path: str):
    """用系统自带播放器播放音频文件"""
    import sys, subprocess
    platform = sys.platform
    if platform == "darwin":
        subprocess.run(["afplay", path], check=False)
    elif platform == "win32":
        # 用默认程序打开并等待（wmplayer 或系统关联程序）
        subprocess.run(["cmd", "/c", "start", "/wait", "", path], check=False)
    else:
        for player in ["mpg123", "ffplay", "aplay"]:
            if subprocess.run(["which", player], capture_output=True).returncode == 0:
                args = [player, "-nodisp", "-autoexit", path] if player == "ffplay" else [player, path]
                subprocess.run(args, check=False, capture_output=True)
                break


def _do_speak_system(text: str):
    """降级方案：系统 TTS（无需网络）"""
    import sys, subprocess
    platform = sys.platform
    if platform == "darwin":
        subprocess.run(["say", "-v", "Tingting", text], check=False)
    elif platform == "win32":
        escaped = text.replace("'", "\\'")
        script = (
            "Add-Type -AssemblyName System.Speech;"
            f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"$s.Speak('{escaped}');"
        )
        subprocess.run(["powershell", "-Command", script], check=False)
    else:
        subprocess.run(["espeak-ng", "-v", "zh", text], check=False)


_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


def speak(text: str, comment_type: str = "鼓励"):
    """把文本加入朗读队列（非阻塞）"""
    with state_lock:
        enabled = state.get("tts_enabled", True)
        api_key = state.get("api_key", "")
        voice   = state.get("tts_voice", TTS_VOICE)
    if enabled:
        _speak_queue.put((text, api_key, voice, comment_type))
# ──────────────────────────────────────────────────────────

# ─── 全局状态（线程间共享）─────────────────────────────────
state = {
    "running": False,
    "api_key": DASHSCOPE_API_KEY,
    "interval": SCREENSHOT_INTERVAL,
    "style": "热情鼓励",
    "tts_enabled": True,
    "tts_voice": TTS_VOICE,            # 音色，可在界面切换
    "comments": [],
    "current_game": None,
    "current_scene": None,
    "last_screenshot_b64": None,
    "status": "待机中",
    "error": None,
    "stats": {
        "total_comments": 0,
        "games_seen": set(),
        "session_start": None,
    }
}
state_lock = threading.Lock()
monitor_thread = None
# ──────────────────────────────────────────────────────────


# ─── 截图 ──────────────────────────────────────────────────
def take_screenshot() -> str:
    """截取全屏，压缩，返回 base64 字符串"""
    img: Image.Image = ImageGrab.grab()
    img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)
    if img.mode != "RGB":           # 修复：RGBA 不支持 JPEG
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


# ─── 百炼分析 ──────────────────────────────────────────────
STYLE_PROMPTS = {
    "热情鼓励": "你是一个超级热情的游戏应援团，你看着好朋友打游戏，对任何操作都能找到闪光点，疯狂鼓励，语气活泼可爱充满正能量，像在加油打气。",
    "损友调侃": "你是一个超爱损人的游戏好友，语气调侃幽默，夸张地批评玩家操作，但带着温暖的友情感。",
    "专业解说": "你是专业的电竞解说员，用专业术语分析游戏局势，客观评价当前战况和玩家的操作。",
    "毒舌评论": "你是毒舌游戏评论员，话语犀利辛辣，直接指出玩家的失误，语气不留情面但搞笑。",
    "甜蜜女友": "你是玩家的甜蜜女友，撒娇又体贴，用温柔爱意的语气夸奖他的每一个操作，偶尔撒个娇说好担心他输，充满粉红泡泡。",
}

ANALYZE_PROMPT_TEMPLATE = """
{style_desc}

请分析这张电脑桌面截图，完成：
1. 判断用户正在做什么（玩游戏/看视频/工作/其他）
2. 如果是游戏，识别游戏名称和当前场景
3. 用你的风格生成 1 条简短评论（20-40 字），口语化，像朋友说话
4. 评论注明类型：[鼓励] [调侃] [分析] [感叹] 之一

{recent_comments_section}

请严格返回 JSON，不要有其他文字：
{{
  "activity": "玩游戏",
  "game": "英雄联盟",
  "scene": "团战中，局势焦灼",
  "confidence": 88,
  "comments": [
    {{"text": "哇！这波操作也太帅了吧！继续冲！", "type": "鼓励"}}
  ]
}}
"""


def analyze_screenshot(b64_image: str, api_key: str, style: str, recent_comments: list = None) -> dict:
    """调用百炼 qwen-vl-max 分析截图，返回结构化结果"""
    client = openai.OpenAI(
        api_key=api_key,
        base_url=DASHSCOPE_BASE_URL,
    )
    style_desc = STYLE_PROMPTS.get(style, STYLE_PROMPTS["热情鼓励"])

    # 把最近 5 条评论注入 prompt，避免复读
    if recent_comments:
        lines = "\n".join(f"- {c['text']}" for c in recent_comments[:5])
        recent_section = f"【重要】你最近已经说过以下内容，本次必须说完全不同的话，换个角度或话题：\n{lines}"
    else:
        recent_section = ""

    prompt = ANALYZE_PROMPT_TEMPLATE.format(
        style_desc=style_desc,
        recent_comments_section=recent_section,
    )

    resp = client.chat.completions.create(
        model=DASHSCOPE_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}"
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=800,
    )

    raw = resp.choices[0].message.content.strip()
    # 提取 JSON（防止模型多说了废话）
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ─── 监控循环 ──────────────────────────────────────────────
def monitor_loop():
    """后台线程：定时截图 → 分析 → 写入 state"""
    with state_lock:
        state["stats"]["session_start"] = datetime.now().isoformat()

    while True:
        with state_lock:
            if not state["running"]:
                break
            api_key = state["api_key"]
            interval = state["interval"]
            style = state["style"]

        try:
            with state_lock:
                state["status"] = "截图中..."

            b64 = take_screenshot()

            with state_lock:
                state["last_screenshot_b64"] = b64
                state["status"] = "AI 分析中..."
                recent = list(state["comments"][:5])

            result = analyze_screenshot(b64, api_key, style, recent)

            now_str = datetime.now().strftime("%H:%M:%S")
            new_comments = []
            for c in result.get("comments", []):
                entry = {
                    "text": c["text"],
                    "type": c["type"],
                    "time": now_str,
                    "game": result.get("game", ""),
                    "scene": result.get("scene", ""),
                }
                new_comments.append(entry)

            with state_lock:
                state["current_game"] = result.get("game")
                state["current_scene"] = result.get("scene")
                state["comments"] = new_comments + state["comments"]
                state["comments"] = state["comments"][:50]
                state["stats"]["total_comments"] += len(new_comments)
                if result.get("game"):
                    state["stats"]["games_seen"].add(result["game"])
                state["status"] = f"监控中 · {now_str} 已更新"
                state["error"] = None

            # 逐条朗读新评论（在锁外执行，避免阻塞状态更新）
            for c in new_comments:
                speak(c["text"], c.get("type", "鼓励"))

        except Exception as e:
            with state_lock:
                state["error"] = str(e)
                state["status"] = "发生错误，等待重试"

        for _ in range(interval):
            with state_lock:
                if not state["running"]:
                    return
            time.sleep(1)


# ─── HTTP 服务器 ───────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/":
            self.serve_file("index.html", "text/html")
        elif self.path == "/api/state":
            self.serve_json(self.get_safe_state())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/start":
            self.handle_start(body)
        elif self.path == "/api/stop":
            self.handle_stop()
        elif self.path == "/api/analyze_now":
            self.handle_analyze_now()
        elif self.path == "/api/settings":
            self.handle_settings(body)
        elif self.path == "/api/clear":
            with state_lock:
                state["comments"] = []
            self.serve_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def handle_start(self, body):
        global monitor_thread
        with state_lock:
            if body.get("api_key"):
                state["api_key"] = body["api_key"]
            if body.get("interval"):
                state["interval"] = int(body["interval"])
            if body.get("style"):
                state["style"] = body["style"]
            if not state["api_key"]:
                self.serve_json({"ok": False, "error": "请先填写 API Key"})
                return
            if state["running"]:
                self.serve_json({"ok": True, "msg": "已在运行"})
                return
            state["running"] = True

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        self.serve_json({"ok": True})

    def handle_stop(self):
        with state_lock:
            state["running"] = False
            state["status"] = "已暂停"
        self.serve_json({"ok": True})

    def handle_analyze_now(self):
        with state_lock:
            api_key = state["api_key"]
            style = state["style"]
            if not api_key:
                self.serve_json({"ok": False, "error": "请先填写 API Key"})
                return

        try:
            b64 = take_screenshot()
            with state_lock:
                state["last_screenshot_b64"] = b64
                recent = list(state["comments"][:5])
            result = analyze_screenshot(b64, api_key, style, recent)
            now_str = datetime.now().strftime("%H:%M:%S")
            new_comments_now = []
            with state_lock:
                for c in result.get("comments", []):
                    entry = {
                        "text": c["text"],
                        "type": c["type"],
                        "time": now_str,
                        "game": result.get("game", ""),
                        "scene": result.get("scene", ""),
                    }
                    state["comments"].insert(0, entry)
                    new_comments_now.append(entry)
                state["current_game"] = result.get("game")
                state["current_scene"] = result.get("scene")
                state["stats"]["total_comments"] += len(result.get("comments", []))
            for c in new_comments_now:
                speak(c["text"], c.get("type", "鼓励"))
            self.serve_json({"ok": True, "result": result})
        except Exception as e:
            self.serve_json({"ok": False, "error": str(e)})

    def handle_settings(self, body):
        with state_lock:
            if "interval" in body:
                state["interval"] = int(body["interval"])
            if "style" in body:
                state["style"] = body["style"]
            if "api_key" in body:
                state["api_key"] = body["api_key"]
            if "tts_enabled" in body:
                state["tts_enabled"] = bool(body["tts_enabled"])
            if "tts_voice" in body:
                state["tts_voice"] = body["tts_voice"]
        self.serve_json({"ok": True})

    def get_safe_state(self):
        with state_lock:
            games_seen = list(state["stats"]["games_seen"])
            return {
                "running": state["running"],
                "status": state["status"],
                "error": state["error"],
                "current_game": state["current_game"],
                "current_scene": state["current_scene"],
                "style": state["style"],
                "interval": state["interval"],
                "tts_enabled": state["tts_enabled"],
                "comments": state["comments"][:20],
                "last_screenshot_b64": state["last_screenshot_b64"],
                "stats": {
                    "total_comments": state["stats"]["total_comments"],
                    "games_seen": games_seen,
                    "session_start": state["stats"]["session_start"],
                },
            }

    def serve_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, filename, content_type):
        import os
        path = os.path.join(os.path.dirname(__file__), filename)
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()


# ─── 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import webbrowser
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"""
╔══════════════════════════════════════╗
║       🎮  游戏搭子 AI  已启动        ║
╠══════════════════════════════════════╣
║  模型：{DASHSCOPE_MODEL:<30}║
║  打开浏览器访问：                    ║
║  👉  http://127.0.0.1:{PORT}          ║
╚══════════════════════════════════════╝
    """)
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出，下次再来！👋")