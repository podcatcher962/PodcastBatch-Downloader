# XiaoYuZhou Podcast Downloader 小宇宙播客下载器 v1

> **⚠️ 免责声明：本工具仅供个人学习 Python 编程、tkinter GUI 开发、API 交互、网络爬虫技术研究使用。严禁用于任何商业用途或大规模批量下载。通过本工具下载的所有音频内容，其版权及知识产权归小宇宙平台及原作者所有。下载后请在 24 小时内删除，如需长期保留请通过小宇宙官方 App 购买正版或订阅。使用本工具即表示您同意承担全部法律责任。**

---

小宇宙播客批量下载器，纯 Python 标准库 + tkinter GUI。需手动获取 access token。

## 功能

- 自动获取播客节目列表（支持批量播客）
- 增量检测：已下载自动跳过
- 发现推荐页：内置 47 个精选中文播客
- 下载队列页：实时百分比进度
- 多线程并发下载
- ffmpeg M4A→MP3 转码（可选）
- 内含 token_helper.py 辅助获取认证令牌

## 运行

```bash
python xiaoyuzhou_watcher.py
```

**要求：Python 3.8+，ffmpeg（可选），需手动配置 access_token（见下方说明）**

## 获取 Access Token

1. 运行 `python token_helper.py` 尝试自动提取
2. 或手动：打开小宇宙网页版 → 开发者工具 → Network → 找到任意 API 请求 → 复制 Authorization header 值
3. 粘贴到 `settings.json` 的 `access_token` 字段

## 技术栈

`tkinter` / `urllib` / `re` / `threading` / `sqlite3` / `json` — 纯标准库，零第三方依赖

## 项目结构

```
├── xiaoyuzhou_watcher.py  # GUI 主程序
├── xyzcore.py             # 核心引擎 (API/下载/数据库)
├── token_helper.py        # Chrome CDP Token 提取器
├── settings.json          # 配置文件模板
├── 小宇宙播客ID.txt        # 播客 ID 列表
├── 启动.bat                # Windows 启动脚本
├── README.md
└── LICENSE
```

## License

MIT License — 详见 LICENSE 文件。
