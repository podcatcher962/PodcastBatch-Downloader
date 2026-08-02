#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chrome DevTools Protocol token获取器
自动启动Chrome并捕获小宇宙的refresh_token
"""

import os
import json
import time
import socket
import struct
import base64
import hashlib
import threading
import subprocess
import urllib.request


def _generate_ws_key():
    """生成WebSocket握手key"""
    return base64.b64encode(os.urandom(16)).decode()


def _ws_connect(ws_url):
    """纯Python WebSocket连接"""
    from urllib.parse import urlparse
    parsed = urlparse(ws_url)
    host, port = parsed.hostname, parsed.port or 80
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((host, port))
    
    key = _generate_ws_key()
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(request.encode())
    
    # Read response
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = sock.recv(4096)
        if not chunk: raise Exception("WS handshake failed")
        response += chunk
    
    if b"101" not in response.split(b"\r\n")[0]:
        raise Exception(f"WS handshake failed: {response[:100]}")
    
    return sock


def _ws_recv(sock):
    """接收WebSocket帧"""
    hdr = sock.recv(2)
    if len(hdr) < 2: return None
    opcode = hdr[0] & 0x0F
    masked = hdr[1] & 0x80
    length = hdr[1] & 0x7F
    
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    
    masks = sock.recv(4) if masked else None
    data = b""
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk: break
        data += chunk
    
    if masked and masks:
        data = bytes(b ^ masks[i % 4] for i, b in enumerate(data))
    
    return json.loads(data) if opcode == 1 else data


def _ws_send(sock, data):
    """发送WebSocket帧"""
    msg = json.dumps(data).encode() if isinstance(data, dict) else data
    frame = bytearray([0x81])  # text frame
    if len(msg) < 126:
        frame.append(len(msg))
    elif len(msg) < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", len(msg)))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", len(msg)))
    frame.extend(msg)
    sock.sendall(bytes(frame))


def get_token_from_chrome():
    """
    启动Chrome with --remote-debugging-port=9222
    导航到xiaoyuzhoufm.com，等待用户登录，
    捕获网络请求中的refresh_token
    """
    # 不杀已有Chrome，使用临时profile独立启动
    pass  # skip killing
    
    # 找到浏览器路径：Edge 优先 > Chrome > 夸克
    browser_paths = [
        ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ("Edge", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ("Edge", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")),
        ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ("Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ("Chrome", os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
        ("Quark", os.path.expandvars(r"%LOCALAPPDATA%\Quark\Application\quark.exe")),
    ]
    browser = None; browser_name = None
    for name, path in browser_paths:
        if os.path.exists(path):
            browser = path; browser_name = name; break
    if not browser:
        return None, None, "未找到 Edge / Chrome / 夸克 浏览器"
    
    print(f"[Token] Stopping {browser_name} to enable debug mode...")
    # 关掉浏览器（用真实 profile 重启才能保留登录态）
    exe_name = "msedge.exe" if browser_name == "Edge" else "chrome.exe" if browser_name == "Chrome" else ""
    if exe_name:
        subprocess.run(f"taskkill /f /im {exe_name} 2>nul", shell=True)
        time.sleep(2)
    
    # 使用真实 profile 直接启动（不复制——复制会丢加密cookie）
    # Edge 的 profile 路径
    if browser_name == "Edge":
        profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data")
    elif browser_name == "Chrome":
        profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    else:
        profile_dir = None
    
    cmd = [browser, "--remote-debugging-port=9222", "--no-first-run"]
    if profile_dir and os.path.exists(profile_dir):
        cmd.append(f"--user-data-dir={profile_dir}")
    cmd.append("https://www.xiaoyuzhoufm.com/")
    
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    time.sleep(4)
    
    # 连接到CDP
    try:
        # 获取浏览器target
        resp = urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)
        targets = json.loads(resp.read())
        
        # 找到xiaoyuzhou页面
        ws_url = None
        for t in targets:
            if "xiaoyuzhou" in t.get("url", ""):
                ws_url = t.get("webSocketDebuggerUrl")
                break
        
        if not ws_url:
            targets2 = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5).read())
            for t in targets2:
                if "xiaoyuzhou" in t.get("url", ""):
                    ws_url = t.get("webSocketDebuggerUrl"); break
        
        if not ws_url:
            return None, None, "Please login to xiaoyuzhoufm.com in the opened browser"
        
        print(f"[Token] Connected to CDP, capturing auth from API calls...")
        ws = _ws_connect(ws_url)
        
        # 启用Network domain
        _ws_send(ws, {"id": 1, "method": "Network.enable"})
        # 也启用Page domain以注入JS触发API调用
        _ws_send(ws, {"id": 2, "method": "Page.enable"})
        
        # 注入JS触发一个API调用（页面已加载，API自动发出）
        # 我们只需要等待捕获
        token = None; device_id = None
        deadline = time.time() + 60
        
        while time.time() < deadline and not (token and device_id):
            msg = _ws_recv(ws)
            if not msg: time.sleep(0.3); continue
            
            # 检查 请求头（access_token / device_id 在请求里）
            if isinstance(msg, dict) and msg.get("method") == "Network.requestWillBeSent":
                params = msg.get("params", {})
                req = params.get("request", {})
                headers = req.get("headers", {})
                url = req.get("url", "")
                
                if "api.xiaoyuzhoufm.com" in url:
                    at = headers.get("x-jike-access-token") or headers.get("X-Jike-Access-Token")
                    did = headers.get("x-jike-device-id") or headers.get("X-Jike-Device-Id")
                    if at and not token:
                        token = at
                        print(f"[Token] access_token captured from request header")
                    if did and not device_id:
                        device_id = did
                        print(f"[Token] device_id captured from request header")
            
            # 也检查响应头（refresh_token可能在响应里）
            if isinstance(msg, dict) and msg.get("method") == "Network.responseReceived":
                params = msg.get("params", {})
                resp = params.get("response", {})
                headers = resp.get("headers", {})
                
                rt = headers.get("x-jike-refresh-token") or headers.get("X-Jike-Refresh-Token")
                did2 = headers.get("x-jike-device-id") or headers.get("X-Jike-Device-Id")
                if rt:
                    token = rt  # 优先用refresh_token
                    print(f"[Token] refresh_token captured from response header")
                if did2: device_id = did2
        
        ws.close()
        
        ws.close()
        
        if token:
            return token, device_id, None
        return None, None, "No token captured in 120s"
        
    except Exception as e:
        return None, None, str(e)
    finally:
        pass  # 不杀浏览器


if __name__ == "__main__":
    token, did, err = get_token_from_chrome()
    if token:
        print(f"Token: {token[:40]}...")
        print(f"Device ID: {did}")
    else:
        print(f"Failed: {err}")
