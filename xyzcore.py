#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xyzcore —— 小宇宙播客下载器核心逻辑。

基于小宇宙 API（https://api.xiaoyuzhoufm.com/），
支持手机号+短信验证码登录、搜索播客、获取节目列表、下载音频。
"""

import os
import sys
import re
import json
import time
import uuid
import socket
import sqlite3
import subprocess
import datetime
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

socket.setdefaulttimeout(30)

# APP_DIR：PyInstaller 打包时用 exe 所在目录，否则用脚本目录
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "xiaoyuzhou.db")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "download_dir": os.path.join(APP_DIR, "downloads"),
    "cutoff_date": "2024-01-01",
    "threads": 3,
    "format": "mp3",
    "bitrate": "64k",
    "minimize_on_dl": False,
    "sound_notify": False,
    "phone": "",
    "access_token": "",
    "refresh_token": "",
    "device_id": "",
    "user_agent": "Xiaoyuzhou/2.99.1(android 28)",
}

_illegal = re.compile(r'[\\/:*?"<>|]')
_FFMPEG_PATH = None


def _find_ffmpeg():
    global _FFMPEG_PATH
    if _FFMPEG_PATH is not None:
        return _FFMPEG_PATH
    # PyInstaller 打包后资源在 sys._MEIPASS
    try:
        base = sys._MEIPASS
    except Exception:
        base = APP_DIR
    candidates = [
        os.path.join(base, "ffmpeg.exe"),
        os.path.join(APP_DIR, "ffmpeg.exe"),
    ]
    import shutil as _shutil
    for p in candidates:
        if os.path.isfile(p):
            _FFMPEG_PATH = p
            return p
    _FFMPEG_PATH = _shutil.which("ffmpeg") or ""
    return _FFMPEG_PATH or None


def safe_name(s):
    return _illegal.sub("_", str(s)).strip() or "untitled"


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if k in DEFAULT_SETTINGS:
                    s[k] = v
        except Exception:
            pass
    return s


def save_settings(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS downloaded (
        track_id TEXT PRIMARY KEY, podcast_id TEXT, title TEXT,
        src TEXT, created_at TEXT, downloaded_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS podcasts (
        pid TEXT PRIMARY KEY, title TEXT, author TEXT,
        image TEXT, added_at TEXT)""")
    return conn


# ---------------------------------------------------------------------------
def _api_headers(settings):
    """构建 API 请求头（含完整设备信息）"""
    now = datetime.datetime.now()
    local_time = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "+0800"
    
    if not settings.get("device_id"):
        settings["device_id"] = str(uuid.uuid4())
        save_settings(settings)
    
    h = {
        "Host": "api.xiaoyuzhoufm.com",
        "User-Agent": "okhttp/4.12.0",
        "Accept-Encoding": "gzip",
        "os": "android",
        "os-version": "32",
        "manufacturer": "vivo",
        "model": "V2366GA",
        "resolution": "1080x1920",
        "market": "update",
        "applicationid": "app.podcast.cosmos",
        "app-version": "2.91.0",
        "app-buildno": "1305",
        "webviewversion": "101.0.4951.61",
        "app-permissions": "100100",
        "wificonnected": "true",
        "timezone": "Asia/Shanghai",
        "Content-Type": "application/json;charset=utf-8",
        "local-time": local_time,
        "x-jike-device-id": settings["device_id"],
        "sentry-trace": "00000000000000000000000000000000-0000000000000000-0",
    }
    # device-properties
    props = json.dumps({
        "uuid": settings["device_id"],
        "android_id": uuid.uuid4().hex[:16],
        "oaid": "", "vaid": "", "aaid": ""
    }, separators=(',', ':'))
    h["x-jike-device-properties"] = props
    
    if settings.get("access_token"):
        h["x-jike-access-token"] = settings["access_token"]
    return h


def _read_json(r):
    """读取响应并自动处理 gzip"""
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        import gzip as _gzip
        raw = _gzip.decompress(raw)
    return json.loads(raw)


def _api_post(url, payload, settings, _retry=True):
    data = json.dumps(payload).encode("utf-8")
    try:
        req = Request(url, data=data, headers=_api_headers(settings))
        with urlopen(req, timeout=30) as r:
            return _read_json(r)
    except HTTPError as e:
        if _retry and e.code == 401 and _maybe_refresh(settings):
            return _api_post(url, payload, settings, _retry=False)
        try:
            body = _read_json(e) if e.headers.get("Content-Encoding") == "gzip" else json.loads(e.read())
            msg = body.get("toast", body.get("message", str(e)))
            raise RuntimeError(msg)
        except (json.JSONDecodeError, RuntimeError):
            raise RuntimeError(f"API {e.code}: {e.reason}")


def _api_get(url, settings, _retry=True):
    try:
        req = Request(url, headers=_api_headers(settings))
        with urlopen(req, timeout=30) as r:
            return _read_json(r)
    except HTTPError as e:
        if _retry and e.code == 401 and _maybe_refresh(settings):
            return _api_get(url, settings, _retry=False)
        try:
            body = _read_json(e) if e.headers.get("Content-Encoding") == "gzip" else json.loads(e.read())
            msg = body.get("toast", body.get("message", str(e)))
            raise RuntimeError(msg)
        except (json.JSONDecodeError, RuntimeError):
            raise RuntimeError(f"API {e.code}: {e.reason}")


# ---------------------------------------------------------------------------
def send_sms_code(phone, settings, area_code="+86"):
    """发送短信验证码"""
    url = "https://api.xiaoyuzhoufm.com/v1/auth/sendCode"
    # SMS 发送需要额外 device-properties 头
    h = _api_headers(settings)
    if settings.get("device_id"):
        props = json.dumps({"uuid": settings["device_id"], "android_id": uuid.uuid4().hex[:16],
                            "oaid": "", "vaid": "", "aaid": ""}, separators=(',', ':'))
        h["x-jike-device-properties"] = props
    data = json.dumps({"mobilePhoneNumber": phone, "areaCode": area_code}).encode("utf-8")
    req = Request(url, data=data, headers=h)
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
            raise RuntimeError(body.get("toast", body.get("message", str(body))))
        except (json.JSONDecodeError, RuntimeError) as ex:
            if isinstance(ex, RuntimeError): raise
            raise RuntimeError(f"API {e.code}: {body_text[:200]}")


def login_with_sms(phone, code, settings, area_code="+86"):
    """短信验证码登录，返回 access_token"""
    url = "https://api.xiaoyuzhoufm.com/v1/auth/loginOrSignUpWithSMS"
    h = _api_headers(settings)
    data = json.dumps({
        "areaCode": area_code,
        "verifyCode": code,
        "mobilePhoneNumber": phone
    }).encode("utf-8")

    req = Request(url, data=data, headers=h)
    with urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
        access_token = r.headers.get("x-jike-access-token", "")
    if not access_token:
        raise RuntimeError("登录失败：未获取到 token")
    settings["access_token"] = access_token
    settings["phone"] = phone
    save_settings(settings)
    uid = body.get("uid", body.get("data", {}).get("uid", "?"))
    return uid


def is_logged_in(settings):
    """检查是否已登录"""
    return bool(settings.get("access_token", ""))


def login_with_refresh_token(refresh_token, device_id, settings):
    """用 refresh_token 换取 access_token"""
    url = "https://api.xiaoyuzhoufm.com/app_auth_tokens.refresh"
    h = _api_headers(settings)
    h["x-jike-refresh-token"] = refresh_token
    h["x-jike-device-id"] = device_id or settings.get("device_id", "")
    settings["device_id"] = h["x-jike-device-id"]
    
    req = Request(url, headers=h)
    try:
        with urlopen(req, timeout=30) as r:
            access_token = r.headers.get("x-jike-access-token", "")
    except HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"Refresh failed ({e.code}): {body}")
    
    if not access_token:
        raise RuntimeError("未获取到 access_token，refresh_token 可能已过期")
    
    settings["access_token"] = access_token
    save_settings(settings)
    return access_token


def _maybe_refresh(settings):
    """access_token 过期时自动用 refresh_token 换新"""
    rt = settings.get("refresh_token", "")
    did = settings.get("device_id", "")
    if not rt or not did: return False
    try:
        login_with_refresh_token(rt, did, settings)
        return True
    except Exception: return False



# ---------------------------------------------------------------------------
def search_podcasts(keyword, settings):
    """搜索播客，返回 [{pid, title, author, image}, ...]"""
    import urllib.parse as _up
    url = f"https://api.xiaoyuzhoufm.com/v1/search?keyword={_up.quote(keyword)}&type=PODCAST&size=20"
    data = _api_get(url, settings)
    results = []
    for item in data.get("data", []):
        results.append({
            "pid": item.get("pid", ""),
            "title": item.get("title", ""),
            "author": item.get("author", item.get("podcaster", {}).get("nickname", "")),
            "image": item.get("image", {}).get("picUrl", "") if isinstance(item.get("image"), dict) else "",
        })
    return results


def get_episodes(pid, settings, limit=50):
    """获取播客节目列表。返回 [{eid, title, pid, audio, duration, pubDate}, ...]"""
    all_episodes = []
    load_key = None

    while len(all_episodes) < limit:
        if load_key:
            payload = {"pid": pid, "loadMoreKey": load_key, "order": "desc", "limit": min(25, limit - len(all_episodes))}
        else:
            payload = {"pid": pid, "limit": min(25, limit - len(all_episodes))}
        
        data = _api_post("https://api.xiaoyuzhoufm.com/v1/episode/list", payload, settings)
        episodes = data.get("data", [])
        if not episodes:
            break

        for ep in episodes:
            media = ep.get("media", {})
            source = media.get("source", {}) if isinstance(media, dict) else {}
            eid = ep.get("eid", "")
            all_episodes.append({
                "eid": eid,
                "pid": pid,
                "title": ep.get("title", ""),
                "audio": source.get("url", ""),
                "duration": media.get("duration", 0) if isinstance(media, dict) else 0,
                "pubDate": ep.get("pubDate", ep.get("pub_date", "")),
                "index": len(all_episodes) + 1,
            })

        load_key = data.get("loadMoreKey")
        if not load_key:
            break

    return all_episodes


def get_episode_audio(eid, settings):
    """获取单个节目的音频URL（免登录可获取公开节目）"""
    url = f"https://api.xiaoyuzhoufm.com/v1/episode/get?eid={eid}"
    data = _api_get(url, settings)
    ep = data.get("data", {})
    media = ep.get("media", {})
    source = media.get("source", {}) if isinstance(media, dict) else {}
    return source.get("url", "")


# ---------------------------------------------------------------------------
def convert_to_mp3(m4a_path, mp3_path, log_q, bitrate="64k"):
    """ffmpeg 转码"""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        log_q.put("[警告] 未找到 ffmpeg")
        return False
    cmd = [ffmpeg, "-y", "-i", m4a_path, "-codec:a", "libmp3lame",
           "-map_metadata", "0", "-nostdin", "-loglevel", "error"]
    if bitrate.upper() == "VBR":
        cmd += ["-q:a", "2"]
    else:
        cmd += ["-b:a", bitrate]
    cmd.append(mp3_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        return result.returncode == 0 and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0
    except Exception:
        return False


def download_track(track, settings, log_q, status_cb=None):
    """下载单条节目"""
    eid = track.get("eid", "")
    title = track.get("title", "") or f"ep_{eid}"
    pid = track.get("pid", "")
    src = track.get("audio") or ""

    if not src:
        # 尝试验证后获取音频URL
        try:
            src = get_episode_audio(eid, settings)
        except Exception:
            pass
    if not src:
        log_q.put(f"[跳过] {title}：无音频地址")
        return False

    want_mp3 = (settings.get("format", "mp3") == "mp3")
    final_ext = ".mp3" if want_mp3 else ".m4a"
    _use_pipe = want_mp3 and _find_ffmpeg()

    # 用播客名作为子目录
    try:
        conn = db_conn()
        row = conn.execute("SELECT title FROM podcasts WHERE pid=?", (pid,)).fetchone()
        conn.close()
        folder_name = safe_name(row[0]) if row else pid[:12]
    except Exception:
        folder_name = pid[:12]
    
    album_dir = os.path.join(settings["download_dir"], folder_name)
    os.makedirs(album_dir, exist_ok=True)
    idx = track.get("index", 0)
    base = f"{idx:03d}_{safe_name(title)}" if idx else safe_name(title)
    fpath = os.path.join(album_dir, base + final_ext)
    m4a_path = os.path.join(album_dir, base + ".m4a") if not _use_pipe else fpath

    def _try_once():
        h = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.xiaoyuzhoufm.com/"}
        req = Request(src, headers=h)

        if _use_pipe:
            ffmpeg = _find_ffmpeg()
            bitrate = settings.get("bitrate", "64k")
            ff_cmd = [ffmpeg, "-y", "-i", "pipe:0", "-codec:a", "libmp3lame",
                      "-map_metadata", "0", "-nostdin", "-loglevel", "error",
                      "-f", "mp3", fpath]
            if bitrate.upper() == "VBR":
                ff_cmd.insert(6, "-q:a"); ff_cmd.insert(7, "2")
            else:
                ff_cmd.insert(6, "-b:a"); ff_cmd.insert(7, bitrate)
            
            if status_cb: status_cb("downloading", 0)
            log_q.put(f"[下载+转码] {title}（流水线）开始…")
            ff_proc = subprocess.Popen(ff_cmd, stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            try:
                with urlopen(req, timeout=60) as r:
                    total = r.headers.get("Content-Length")
                    total = int(total) if total else 0
                    downloaded, last_t = 0, time.time()
                    last_pct = -1
                    while True:
                        chunk = r.read(65536)
                        if not chunk: break
                        ff_proc.stdin.write(chunk)
                        downloaded += len(chunk)
                        # 有Content-Length时算百分比，否则用MB数
                        if total > 0:
                            pct = int(downloaded/total*100)
                            if pct > last_pct and status_cb:
                                status_cb("downloading", pct)
                                last_pct = pct
                        else:
                            mb = downloaded//(1024*1024)
                            if mb > last_pct and status_cb:
                                status_cb("downloading", min(mb*2, 99))  # 估进度
                                last_pct = mb
                        if time.time() - last_t > 30:
                            ff_proc.kill()
                            raise socket.timeout(f"下载停滞")
                        last_t = time.time()
                ff_proc.stdin.close()
                if status_cb: status_cb("converting", 100)
                if ff_proc.wait(timeout=120) != 0 or not (os.path.exists(fpath) and os.path.getsize(fpath) > 0):
                    raise RuntimeError("转码失败")
                log_q.put(f"[完成] {title}（{os.path.getsize(fpath)/1024/1024:.1f}MB MP3）")
            except:
                ff_proc.kill()
                raise
        else:
            if status_cb: status_cb("downloading", 0)
            with urlopen(req, timeout=60) as r:
                total = r.headers.get("Content-Length")
                total = int(total) if total else 0
                downloaded = 0; last_t = time.time(); last_pct = -1
                with open(m4a_path, "wb") as f:
                    while True:
                        chunk = r.read(65536)
                        if not chunk: break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded/total*100)
                            if pct > last_pct and status_cb:
                                status_cb("downloading", pct)
                                last_pct = pct
                        else:
                            mb = downloaded//(1024*1024)
                            if mb > last_pct and status_cb:
                                status_cb("downloading", min(mb*2, 99))
                                last_pct = mb
                        if time.time() - last_t > 30:
                            raise socket.timeout("下载停滞")
                        last_t = time.time()

            if want_mp3:
                log_q.put(f"[转码] {title}…")
                if status_cb: status_cb("converting", 99)
                if convert_to_mp3(m4a_path, fpath, log_q, settings.get("bitrate", "64k")):
                    try: os.remove(m4a_path)
                    except: pass
                else:
                    try: os.rename(m4a_path, fpath.replace(".mp3", ".m4a"))
                    except: pass
            log_q.put(f"[完成] {title}（{os.path.getsize(fpath)/1024/1024:.1f}MB）")

        conn = db_conn()
        conn.execute("INSERT OR REPLACE INTO downloaded VALUES (?,?,?,?,?,?)",
                     (eid, pid, title, src, track.get("pubDate", ""),
                      datetime.datetime.now().isoformat()))
        conn.commit(); conn.close()
        if status_cb: status_cb("done")
        return True

    for attempt in range(3):
        try:
            ok = False
            # 硬超时看门狗
            result = {"ok": None, "err": None}
            def _wd():
                try: result["ok"] = _try_once()
                except Exception as e: result["err"] = e
            t = threading.Thread(target=_wd, daemon=True)
            t.start(); t.join(timeout=300)
            if result["ok"] is True:
                return True
            if result["err"]:
                raise result["err"]
            raise TimeoutError("下载超时")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 + attempt * 3)
                continue
            log_q.put(f"[错误] {title} 下载失败：{e}")
            if status_cb: status_cb("failed")
            return False
    return False
