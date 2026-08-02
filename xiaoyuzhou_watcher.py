#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Little Universe Podcast Downloader
"""

import os, sys, re, queue, traceback, threading, datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from concurrent.futures import ThreadPoolExecutor

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# PyInstaller 打包时用 exe 目录
import sys as _sys
if getattr(_sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(_sys.executable)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from xyzcore import *
from xyzcore import _api_get, _api_post

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.log_q = queue.Queue()
        self.logfile = open(os.path.join(APP_DIR, "guilog.txt"), "a", encoding="utf-8")
        self.logfile.write("\n\n===== %s =====\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.logfile.flush()
        self.pending, self.checked, self.episode_map = {}, {}, {}
        self._check_epoch = 0
        self._downloading, self._sort_asc = False, True
        root.title("XiaoYuZhou DL")
        root.geometry("1050x660")
        root.configure(bg="#F0F0F0")
        self._build_menu()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_main_tab()
        self._build_settings_tab()
        self._build_recommend_tab()
        self._build_download_queue_tab()
        self._build_log_tab()
        self.root.after(150, self._poll_log)
        self.root.after(300, self._check_login)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    @staticmethod
    def _cbtn(parent, text, color, command, side=None, padx=0, pady=0, fill=None, expand=False):
        btn = tk.Button(parent, text=text, bg=color, fg="white",
                        font=("Microsoft YaHei UI", 9),
                        relief="flat", activebackground=color,
                        bd=0, padx=10, pady=2, cursor="hand2", command=command)
        if side is not None:
            btn.pack(side=side, padx=padx, pady=pady, fill=fill, expand=expand)
        elif fill or expand:
            btn.pack(padx=padx, pady=pady, fill=fill, expand=expand)
        return btn

    def _build_menu(self):
        menubar = tk.Menu(self.root); self.root.config(menu=menubar)
        hm = tk.Menu(menubar, tearoff=0)
        hm.add_command(label="使用说明", command=lambda: messagebox.showinfo("使用说明",
            "小宇宙播客下载器\n\n"
            "1. 设置页粘贴 Cookie Token → 登录\n"
            "2. 手机 App 分享播客链接 → 发到电脑\n"
            "3. 粘贴链接到输入框 → 点添加\n"
            "4. 左侧选播客 → 获取节目列表\n"
            "5. 勾选节目 → 下载选中\n\n"
            "起始日期：只下载该日期之后的节目\n"
            "播客ID备份到 小宇宙播客ID.txt/.md"))
        hm.add_command(label="免责声明", command=lambda: messagebox.showinfo("免责声明",
            "【免责声明】\n\n"
            "一、本软件为免费、开源的个人学习与研究工具，\n"
            "    不以任何形式收取费用，不提供商业服务。\n\n"
            "二、本软件通过小宇宙（xiaoyuzhoufm.com）\n"
            "    公开 API 接口获取播客节目信息，\n"
            "    所有音频文件的著作权、版权及相关知识产权\n"
            "    均归原作者及小宇宙平台所有。\n\n"
            "三、用户下载的音频内容仅限于个人学习、\n"
            "    研究或欣赏用途，不得用于商业目的，\n"
            "    不得向第三方传播、分发、转售。\n\n"
            "四、用户使用本软件即视为已阅读并同意：\n"
            "    (a) 自行承担使用本软件的全部法律责任；\n"
            "    (b) 遵守《中华人民共和国著作权法》\n"
            "        及相关法律法规；\n"
            "    (c) 尊重原作者的合法权益。\n\n"
            "五、本软件开发者不承担因用户违规使用\n"
            "    而产生的任何直接或间接责任。\n\n"
            "六、本软件不破解、不篡改、不逆向工程\n"
            "    小宇宙平台的任何加密或保护措施。\n\n"
            "    使用即表示您已同意以上全部条款。"))
        hm.add_command(label="关于", command=lambda: messagebox.showinfo("关于",
            "小宇宙播客下载器 v1.0\n\n"
            "基于小宇宙公开 API\n"
            "Python 3 + tkinter GUI\n"
            "纯本地运行，无数据上传\n\n"
            "仅供个人学习与测试使用\n"
            "请勿用于商业用途"))
        menubar.add_cascade(label="帮助", menu=hm)

    def _build_main_tab(self):
        f = ttk.Frame(self.notebook); self.notebook.add(f, text="下载中心")
        left = ttk.Frame(f); left.pack(side="left", fill="y", padx=4, pady=4)
        ttk.Label(left, text="播客清单", font=("", 10, "bold")).pack(anchor="w", padx=4)

        # 添加播客
        self.add_pid_var = tk.StringVar()
        add_f = ttk.Frame(left); add_f.pack(fill="x", pady=2)
        ttk.Entry(add_f, textvariable=self.add_pid_var, width=22).pack(side="left", fill="x", expand=True)
        self._cbtn(add_f, "添加", "#4CAF50", self._add_by_url, side="right", padx=2)

        # 操作按钮
        self._cbtn(left, "批量导入ID文件", "#FF9800", self._import_ids, fill="x", pady=2)
        self._cbtn(left, "一键检查所有更新", "#2196F3", self._check_all, fill="x", pady=2)
        self._cbtn(left, "删除选中", "#F44336", self._del_podcast, fill="x", pady=2)
        self._cbtn(left, "清除下载记录", "#9E9E9E", self._clear_history, fill="x", pady=2)
        self._cbtn(left, "导出下载历史CSV", "#607D8B", self._export_csv, fill="x", pady=2)

        pf = ttk.Frame(left); pf.pack(fill="both", expand=True, pady=4)
        self.pod_list = tk.Listbox(pf, width=30, height=18, bg="#F5F5F5", fg="#333",
                                    selectbackground="#BBDEFB", font=("Microsoft YaHei UI", 9))
        s1 = ttk.Scrollbar(pf, orient="vertical", command=self.pod_list.yview)
        self.pod_list.configure(yscrollcommand=s1.set)
        self.pod_list.pack(side="left", fill="both", expand=True); s1.pack(side="right", fill="y")
        self.pod_list.bind("<<ListboxSelect>>", self._on_pod_select)

        right = ttk.Frame(f); right.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.pod_title_var = tk.StringVar(value="（左侧选择播客）")
        ttk.Label(right, textvariable=self.pod_title_var, font=("", 11, "bold")).pack(anchor="w")
        bar = ttk.Frame(right); bar.pack(fill="x", pady=4)
        tk.Button(bar, text="获取节目列表", bg="#2196F3", fg="white", font=("Microsoft YaHei UI", 9),
                  relief="flat", bd=0, padx=10, pady=2, cursor="hand2", command=self._fetch_episodes).pack(side="left")
        ttk.Button(bar, text="全选", command=lambda: self._set_all(True)).pack(side="left", padx=4)
        ttk.Button(bar, text="全不选", command=lambda: self._set_all(False)).pack(side="left")
        self.btn_download = tk.Button(bar, text="下载选中", bg="#4CAF50", fg="white", font=("Microsoft YaHei UI", 9),
                                       relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                                       command=self._download_selected)
        self.btn_download.pack(side="left", padx=10)

        tf = ttk.Frame(right); tf.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(tf, columns=("sel", "date", "title", "stat"), show="headings", height=16)
        for c, w, a in [("sel", 36, "c"), ("date", 110, "c"), ("title", 560, "w"), ("stat", 50, "c")]:
            self.tree.heading(c, text={"sel": "选", "date": "日期", "title": "标题", "stat": "状态"}[c])
            self.tree.column(c, width=w, anchor="center" if a == "c" else "w")
        s2 = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=s2.set)
        self.tree.pack(side="left", fill="both", expand=True); s2.pack(side="right", fill="y")
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.heading("date", text="日期", command=self._sort_by_date)
        self.tree.tag_configure("odd", background="#E8E8E8")
        self.tree.tag_configure("even", background="#F0F0F0")

        self.status_var = tk.StringVar(value="就绪 — 请先登录设置页")
        ttk.Label(f, textvariable=self.status_var, anchor="w",
                  background="#E0E0E0").pack(side="bottom", fill="x", padx=4, pady=(6, 2))
        self._refresh_pod_list()

    def _build_settings_tab(self):
        f = ttk.Frame(self.notebook); self.notebook.add(f, text="设置")
        s = self.settings

        ttk.Label(f, text="Device ID：").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.did_var = tk.StringVar(value=s.get("device_id", ""))
        ttk.Entry(f, textvariable=self.did_var, width=36).grid(row=0, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Button(f, text="退出", command=self._do_logout).grid(row=0, column=3, padx=2)

        ttk.Label(f, text="Token：").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.rtoken_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.rtoken_var, width=32).grid(row=1, column=1, sticky="w", padx=6)
        def _paste_token():
            try: self.rtoken_var.set(f.clipboard_get())
            except: pass
        ttk.Button(f, text="粘贴", command=_paste_token).grid(row=1, column=2, sticky="w", padx=2)
        tk.Button(f, text="Token登录", bg="#2196F3", fg="white", font=("Microsoft YaHei UI", 9),
                  relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                  command=self._do_token_login).grid(row=1, column=3, padx=4)
        tk.Button(f, text="一键获取", bg="#FF9800", fg="white", font=("Microsoft YaHei UI", 9),
                  relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                  command=self._auto_get_token).grid(row=1, column=4, padx=2)

        self.login_status_var = tk.StringVar(value="已登录" if is_logged_in(s) else "未登录")
        ttk.Label(f, textvariable=self.login_status_var, foreground="#888").grid(row=1, column=5, sticky="w", padx=6)

        ttk.Label(f, text="下载目录：").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        self.dir_var = tk.StringVar(value=s["download_dir"])
        ttk.Entry(f, textvariable=self.dir_var, width=40).grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        ttk.Button(f, text="浏览", command=self._browse_dir).grid(row=2, column=3, padx=2)

        ttk.Label(f, text="起始日期：").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        self.cutoff_var = tk.StringVar(value=s.get("cutoff_date", "2024-01-01"))
        ttk.Entry(f, textvariable=self.cutoff_var, width=12).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(f, text="仅下载此日期之后的节目（格式 YYYY-MM-DD）", foreground="#888").grid(row=3, column=2, columnspan=3, sticky="w", padx=6)

        ttk.Label(f, text="下载并发数：").grid(row=4, column=0, sticky="e", padx=6, pady=6)
        self.threads_var = tk.IntVar(value=s["threads"])
        ttk.Spinbox(f, from_=1, to=8, increment=1, textvariable=self.threads_var, width=8).grid(row=4, column=1, sticky="w", padx=6)

        ttk.Label(f, text="下载格式：").grid(row=5, column=0, sticky="e", padx=6, pady=6)
        self.format_var = tk.StringVar(value=s.get("format", "mp3"))
        ttk.Combobox(f, textvariable=self.format_var, values=["mp3", "m4a"], state="readonly", width=8).grid(row=5, column=1, sticky="w", padx=6)

        ttk.Label(f, text="MP3 比特率：").grid(row=6, column=0, sticky="e", padx=6, pady=6)
        self.bitrate_var = tk.StringVar(value=s.get("bitrate", "64k"))
        ttk.Combobox(f, textvariable=self.bitrate_var, values=["64k", "96k", "128k", "160k", "192k", "VBR"], state="readonly", width=8).grid(row=6, column=1, sticky="w", padx=6)

        self.minimize_var = tk.BooleanVar(value=s.get("minimize_on_dl", False))
        tk.Checkbutton(f, text="下载时自动最小化", variable=self.minimize_var, bg="#F0F0F0", activebackground="#F0F0F0", command=self._auto_save).grid(row=7, column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.sound_var = tk.BooleanVar(value=s.get("sound_notify", False))
        tk.Checkbutton(f, text="下载完成声音提示", variable=self.sound_var, bg="#F0F0F0", activebackground="#F0F0F0", command=self._auto_save).grid(row=7, column=2, columnspan=2, sticky="w", padx=6, pady=2)

        ttk.Label(f, text="所有设置自动保存。", foreground="#888").grid(row=8, column=0, columnspan=3, sticky="w", padx=6)
        for v in (self.dir_var, self.cutoff_var, self.threads_var, self.format_var, self.bitrate_var):
            v.trace_add("write", lambda *a: self._auto_save())

    def _build_recommend_tab(self):
        f = ttk.Frame(self.notebook); self.notebook.add(f, text="发现推荐")
        
        # 已验证的真ID（47个，均通过小宇宙API+Apple Podcasts自动化验证）
        RECOMMENDED = [
            ("日谈公园","5e280faa418a84a0461f9ad8","文艺·生活",""),
            ("无聊斋","5e280fac418a84a0461fb129","文艺·生活",""),
            ("大内密谈","5e3bdf08418a84a046fb556c","音乐·影视",""),
            ("半拿铁","682c566cc7c5f17595635a2c","商业·投资",""),
            ("纵横四海","62694abdb221dd5908417d1e","商业·投资",""),
            ("乘风破浪","65350c9abfd0868f2b75e6ea","商业·投资",""),
            ("泡腾VC","5f445cdb9504bbdb77f092e9","商业·投资",""),
            ("商业WHY酱","61315abc73105e8f15080b8a","商业·投资",""),
            ("不止金钱","65a625966d045a7f5e0b5640","商业·投资",""),
            ("知行小酒馆","6013f9f58e2f7ee375cf4216","商业·投资",""),
            ("十字路口","60502e253c92d4f62c2a9577","商业·投资",""),
            ("听懂涨声","6543750424e7ad2107e8b0b5","商业·投资",""),
            ("截胡不截财","64268ef3fe1d67cb9daab4aa","商业·投资",""),
            ("梵高MoneyTalk","63af151c4ded9d81d0a11f02","商业·投资",""),
            ("出海进行时","60acde17875241dbd2068bf6","商业·投资",""),
            ("声东击西","5e2831ed418a84a046231c00","人文·社会",""),
            ("如此城市CityTells","632817c6953e23f946ae9896","人文·社会",""),
            ("涟漪效应","60c01ce32f4e95c951ae051f","人文·社会",""),
            ("时差in-betweenness","5eef4063418a84a0466f2e89","人文·社会",""),
            ("岩中花述","625635587bfca4e73e990703","人文·社会",""),
            ("天才捕手FM","5e77133b418a84a0469fc305","人文·社会",""),
            ("谍海轶闻","648add74e16019bcbcc845ef","人文·社会",""),
            ("文学中的人生进化课","615c576bc8c1d14e8336698b","人文·社会",""),
            ("银月山庄里的精神世界","62b54bb22f878ce6c8835426","人文·社会",""),
            ("非马非牛","652c966636a1383a6662920a","人文·社会",""),
            ("声动早咖啡","60de7c003dd577b40d5a40f3","科技·互联网",""),
            ("三五环","5e280fab418a84a0461faa3c","科技·互联网",""),
            ("晚点聊","61933ace1b4320461e91fd55","科技·互联网",""),
            ("反潮流俱乐部","5e284c37418a84a0462634a4","科技·互联网",""),
            ("组织进化论","606547c8e5c273d2a3689a3e","科技·互联网",""),
            ("数字游牧","677212d915a5fd520e9bf7c8","科技·互联网",""),
            ("迟早更新","5e280fab418a84a0461fac08","科技·互联网",""),
            ("面基","6388760f22567e8ea6ad070f","科技·互联网",""),
            ("Web3 101","62c2b6b3a61b9fd92a401b39","科技·互联网",""),
            ("信号与噪声","6819d5a7e37664602a344e0e","科技·互联网",""),
            ("无界有声","67330e2ff373fe5d4daa9f7b","科技·互联网",""),
            ("The Alphaist","690b589170e20ba3f0553778","科技·互联网",""),
            ("自爱练习生","63e865b3a1c9d26dec3fa438","女性成长",""),
            ("搞钱女孩","63d945ece725b5378a158d29","女性成长",""),
            ("贤者时间","5e285523418a84a04627767d","女性成长",""),
            ("Burning Questions","656ee209b4b5dd5510b92339","心理·情感",""),
            ("得意忘形","5e74543a418a84a046c4e50e","心理·情感",""),
            ("史蒂夫说","64379296ff8a107611a67208","心理·情感",""),
            ("进化人生","63e8d25ba1c9d26dec70e89c","心理·情感",""),
            ("吃喝玩乐了不起","644b94c494d78eb3f7ae8640","文艺·生活",""),
            ("破产书店","6552e23dd0028fb4cb3762cb","文艺·生活",""),
            ("学完这一课","66b9cea2db5e6d6bf9b1c8f9","文艺·生活",""),
        ]
        
        # 顶部过滤
        top = ttk.Frame(f); top.pack(fill="x", padx=10, pady=(8,4))
        ttk.Label(top, text="精选中文播客推荐  |  勾选后→一键加入左侧播客清单", font=("",10,"bold")).pack(side="left")
        ttk.Label(top, text="  分类：").pack(side="left", padx=(10,0))
        self.rec_cat_var = tk.StringVar(value="全部")
        sb = ttk.Combobox(top, textvariable=self.rec_cat_var,
                          values=["全部"]+sorted(set(r[2] for r in RECOMMENDED)),
                          state="readonly", width=12)
        sb.pack(side="left", padx=4)
        sb.bind("<<ComboboxSelected>>", lambda e: self._refresh_recommend(RECOMMENDED))
        ttk.Label(top, text="  搜索：").pack(side="left")
        self.rec_search_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.rec_search_var, width=16).pack(side="left", padx=4)
        ttk.Button(top, text="筛选", command=lambda: self._refresh_recommend(RECOMMENDED)).pack(side="left", padx=4)
        
        # 表格
        tf = ttk.Frame(f); tf.pack(fill="both", expand=True, padx=10, pady=4)
        self.rec_tree = ttk.Treeview(tf, columns=("sel","title","desc","cat"), show="headings", height=22)
        self.rec_tree.heading("sel", text="选"); self.rec_tree.column("sel", width=36, anchor="center")
        self.rec_tree.heading("title", text="播客名"); self.rec_tree.column("title", width=180)
        self.rec_tree.heading("desc", text="简介"); self.rec_tree.column("desc", width=420)
        self.rec_tree.heading("cat", text="分类"); self.rec_tree.column("cat", width=100)
        rs = ttk.Scrollbar(tf, orient="vertical", command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=rs.set)
        self.rec_tree.pack(side="left", fill="both", expand=True); rs.pack(side="right", fill="y")
        self.rec_tree.bind("<ButtonRelease-1>", self._on_rec_click)
        self.rec_checked = {}; self.rec_items = []
        
        self._refresh_recommend(RECOMMENDED)
        
        bf = ttk.Frame(f); bf.pack(pady=(6,8))
        ttk.Button(bf, text="全选", command=lambda: self._set_rec_all(True)).pack(side="left", padx=4)
        ttk.Button(bf, text="全不选", command=lambda: self._set_rec_all(False)).pack(side="left", padx=4)
        tk.Button(bf, text="▶ 添加到我的播客", bg="#4CAF50", fg="white", font=("Microsoft YaHei UI", 10),
                  relief="flat", bd=0, padx=16, pady=4, cursor="hand2",
                  command=lambda: self._add_recommended(RECOMMENDED)).pack(side="left", padx=10)

    def _refresh_recommend(self, data):
        cat = self.rec_cat_var.get(); kw = self.rec_search_var.get().strip().lower()
        self.rec_tree.delete(*self.rec_tree.get_children())
        self.rec_checked.clear(); self.rec_items.clear()
        for title, pid, cat_name, desc in data:
            if cat != "全部" and cat_name != cat: continue
            if kw and kw not in title.lower() and kw not in desc.lower(): continue
            iid = f"_{len(self.rec_items)}"
            self.rec_items.append((title, pid, cat_name, desc))
            self.rec_tree.insert("", "end", iid=iid, values=("☐", title, desc, cat_name))
            self.rec_checked[iid] = False

    def _on_rec_click(self, evt):
        iid = self.rec_tree.identify_row(evt.y)
        if iid and self.rec_tree.identify_column(evt.x) == "#1":
            self.rec_checked[iid] = not self.rec_checked.get(iid, False)
            self.rec_tree.set(iid, "sel", "☑" if self.rec_checked[iid] else "☐")

    def _set_rec_all(self, val):
        for iid in self.rec_tree.get_children():
            self.rec_checked[iid] = val
            self.rec_tree.set(iid, "sel", "☑" if val else "☐")

    def _add_recommended(self, data):
        if not is_logged_in(self.settings): messagebox.showwarning("提示", "请先在设置页登录"); return
        cnt = 0; errs = 0
        for iid, v in self.rec_checked.items():
            if not v: continue
            title, pid = self.rec_items[int(iid[1:])][0], self.rec_items[int(iid[1:])][1]
            try:
                url = f"https://api.xiaoyuzhoufm.com/v1/podcast/get?pid={pid}"
                info = _api_get(url, self.settings).get("data", {})
                author = info.get("author", "")
                conn = db_conn()
                conn.execute("CREATE TABLE IF NOT EXISTS podcasts (pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT, added_at TEXT)")
                conn.execute("INSERT OR REPLACE INTO podcasts VALUES(?,?,?,?,?)",
                            (pid, title, author, "", datetime.datetime.now().isoformat()))
                conn.commit(); conn.close(); cnt += 1
            except Exception as e:
                errs += 1; self.log_q.put(f"[推荐添加失败] {title}: {e}")
        
        self._refresh_pod_list(); self._sync_podcasts_file()
        self.log_q.put(f"[推荐] 添加 {cnt} 个播客, {errs} 失败")
        self.status_var.set(f"推荐添加: {cnt} 个播客已加入左侧清单")
        messagebox.showinfo("完成", f"成功添加 {cnt} 个播客，{errs} 个失败。\n切到「下载中心」查看。")

    def _build_log_tab(self):
        f = ttk.Frame(self.notebook); self.notebook.add(f, text="日志")
        self.log_box = scrolledtext.ScrolledText(f, wrap="word", state="disabled", bg="#F0F0F0", fg="#333", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, padx=6, pady=6)

    def _check_login(self):
        if is_logged_in(self.settings):
            self.status_var.set("已登录")
            self.login_status_var.set("已登录")

    def _do_token_login(self):
        raw = self.rtoken_var.get().strip(); did = self.did_var.get().strip()
        if not raw: messagebox.showwarning("提示", "请先粘贴Token"); return
        at = None; rt = None
        if "x-jike-refresh-token" in raw:
            m = re.search(r'x-jike-refresh-token=([^;]+)', raw); rt = m.group(1).strip() if m else None
            m2 = re.search(r'x-jike-access-token=([^;]+)', raw); at = m2.group(1).strip() if m2 else None
            m3 = re.search(r'x-jike-device-id=([^;]+)', raw)
            if m3: did = m3.group(1).strip()
        else:
            at = raw
        if not at and not rt:
            messagebox.showwarning("提示", "无法识别Token，请粘贴Cookie完整内容。"); return
        if rt:
            try:
                did = did or str(__import__('uuid').uuid4())[:36]
                at = login_with_refresh_token(rt, did, self.settings)
                self.log_q.put("[登录] refresh_token 换 access_token 成功")
            except Exception as e:
                self.log_q.put(f"[登录失败] {e}")
                messagebox.showerror("Token刷新失败", f"{e}\n请重新从浏览器获取Cookie。"); return
        if not at: messagebox.showwarning("提示", "无有效Token"); return
        if not did: did = str(__import__('uuid').uuid4())[:36]
        self.settings["access_token"] = at
        self.settings["device_id"] = did
        if rt: self.settings["refresh_token"] = rt
        save_settings(self.settings)
        self.did_var.set(did); self.login_status_var.set("已登录"); self.status_var.set("已登录")
        messagebox.showinfo("成功", "登录成功！")
        self._auto_save()

    def _auto_get_token(self):
        if is_logged_in(self.settings): messagebox.showinfo("提示", "已登录，无需重新获取。"); return
        js = "javascript:prompt('Copy ALL (Ctrl+A Ctrl+C):',document.cookie);"
        win = tk.Toplevel(self.root); win.title("Token 获取"); win.geometry("600x300"); win.transient(self.root)
        ttk.Label(win, text="Token 获取（已登录浏览器操作）", font=("", 11, "bold")).pack(pady=(10, 2))
        ttk.Label(win, text="1. 在浏览器打开 xiaoyuzhoufm.com（确保已登录）", font=("", 9)).pack(anchor="w", padx=10)
        ttk.Label(win, text="2. F12 -> Console 粘贴代码 -> 回车", font=("", 9)).pack(anchor="w", padx=10)
        ttk.Label(win, text="3. Ctrl+A 全选 -> Ctrl+C 复制弹窗内容", font=("", 9)).pack(anchor="w", padx=10)
        ttk.Label(win, text="4. 回设置页点「粘贴」-> 「Token登录」", font=("", 9)).pack(anchor="w", padx=10)
        tf = tk.Text(win, height=3, font=("Consolas", 9), wrap="word"); tf.pack(fill="both", expand=True, padx=10, pady=6)
        tf.insert("1.0", js); tf.configure(state="disabled")
        bf = ttk.Frame(win); bf.pack()
        def copy_js(): win.clipboard_clear(); win.clipboard_append(js); messagebox.showinfo("已复制", "代码已复制。去浏览器Console粘贴。")
        tk.Button(bf, text="复制代码", bg="#2196F3", fg="white", font=("", 9),
                  relief="flat", bd=0, padx=10, pady=3, cursor="hand2", command=copy_js).pack(side="left", padx=4)
        ttk.Button(bf, text="关闭", command=win.destroy).pack(side="left", padx=4)

    def _do_logout(self):
        self.settings["access_token"] = ""; self.settings["refresh_token"] = ""; save_settings(self.settings)
        self.rtoken_var.set(""); self.did_var.set("")
        self.login_status_var.set("未登录"); self.status_var.set("已退出登录"); self.log_q.put("[登出] 已清除")

    def _add_by_url(self):
        raw = self.add_pid_var.get().strip()
        if not raw: return
        m = re.search(r'([0-9a-f]{24})', raw)
        if not m: messagebox.showwarning("提示", "未识别播客ID。\n请粘贴链接或24位ID。"); return
        pid = m.group(1)
        if not is_logged_in(self.settings): messagebox.showwarning("提示", "请先登录"); return
        try:
            url = f"https://api.xiaoyuzhoufm.com/v1/podcast/get?pid={pid}"
            data = _api_get(url, self.settings)
            info = data.get("data", {})
            title = info.get("title", pid[:12])
            author = info.get("author", info.get("podcaster", {}).get("nickname", ""))
            conn = db_conn()
            conn.execute("CREATE TABLE IF NOT EXISTS podcasts (pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT, added_at TEXT)")
            conn.execute("INSERT OR REPLACE INTO podcasts VALUES(?,?,?,?,?)",
                        (pid, title, author, info.get("image", {}).get("picUrl", "") if isinstance(info.get("image"), dict) else "",
                         datetime.datetime.now().isoformat()))
            conn.commit(); conn.close()
            self._refresh_pod_list(); self._sync_podcasts_file()
            self.add_pid_var.set(""); self.log_q.put(f"[添加] {title} ({pid[:12]}...)"); self.status_var.set(f"已添加: {title}")
        except Exception as e:
            messagebox.showerror("添加失败", str(e))

    def _import_ids(self):
        # 弹文件选择，预置当前目录 .txt 和 .md
        src = filedialog.askopenfilename(
            initialdir=APP_DIR,
            filetypes=[("ID文件", "*.txt;*.md"), ("所有文件", "*.*")])
        if not src: return
        if not is_logged_in(self.settings): messagebox.showwarning("提示", "请先登录"); return
        cnt = 0; errs = 0
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                m = re.search(r'/podcast/([0-9a-f]{24})', line)
                if not m:
                    # fallback: any 24-char hex ID on its own
                    m = re.search(r'^([0-9a-f]{24})$', line)
                if not m: continue
                pid = m.group(1)
                try:
                    data = _api_get(f"https://api.xiaoyuzhoufm.com/v1/podcast/get?pid={pid}", self.settings)
                    info = data.get("data", {})
                    title = info.get("title", pid[:12]); author = info.get("author", "")
                    conn = db_conn()
                    conn.execute("CREATE TABLE IF NOT EXISTS podcasts (pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT, added_at TEXT)")
                    conn.execute("INSERT OR REPLACE INTO podcasts VALUES(?,?,?,?,?)",
                                (pid, title, author, "", datetime.datetime.now().isoformat()))
                    conn.commit(); conn.close(); cnt += 1
                except Exception as e:
                    errs += 1; self.log_q.put(f"[导入失败] {pid[:12]}: {e}")
        self._refresh_pod_list(); self._sync_podcasts_file()
        self.log_q.put(f"[导入] {cnt} 成功, {errs} 失败"); self.status_var.set(f"批量导入: {cnt} 个播客")
        messagebox.showinfo("导入完成", f"成功 {cnt} 个，失败 {errs} 个。")

    def _sync_podcasts_file(self):
        txt = os.path.join(APP_DIR, "小宇宙播客ID.txt")
        md  = os.path.join(APP_DIR, "小宇宙播客ID.md")
        try:
            conn = db_conn()
            rows = conn.execute("SELECT pid, title, author FROM podcasts").fetchall(); conn.close()
            with open(txt, "w", encoding="utf-8") as f:
                for pid, title, author in rows:
                    f.write(f"{pid}  # {title} - {author}\n")
            with open(md, "w", encoding="utf-8") as f:
                f.write("# 小宇宙播客ID\n\n")
                for pid, title, author in rows:
                    f.write(f"- [{title}](https://www.xiaoyuzhoufm.com/podcast/{pid}) — {author}\n")
        except: pass

    def _del_podcast(self):
        s = self.pod_list.curselection()
        if not s: return
        conn = db_conn()
        rows = conn.execute("SELECT pid FROM podcasts").fetchall()
        idx = s[0]
        if idx < len(rows):
            pid = rows[idx][0]
            conn.execute("DELETE FROM podcasts WHERE pid=?", (pid,))
            conn.execute("DELETE FROM downloaded WHERE podcast_id=?", (pid,))
            conn.commit()
        conn.close()
        self._refresh_pod_list(); self._sync_podcasts_file()

    def _on_pod_select(self, evt):
        s = self.pod_list.curselection()
        if not s: return
        # 从 DB 按索引取 pid（label 格式变了）
        conn = db_conn()
        rows = conn.execute("SELECT pid,title FROM podcasts").fetchall(); conn.close()
        idx = s[0]
        if idx < len(rows):
            pid, title = rows[idx]
            self._selected_pid = pid; self.pod_title_var.set(f"{title} ({pid[:12]}...)")

    def _fetch_episodes(self):
        pid = getattr(self, "_selected_pid", None)
        if not pid: messagebox.showwarning("提示", "请先选择播客"); return
        if not is_logged_in(self.settings): messagebox.showwarning("提示", "请先登录"); return
        self._check_epoch += 1; ep = self._check_epoch
        self.status_var.set("正在获取..."); threading.Thread(target=self._worker_fetch, args=(pid, ep), daemon=True).start()

    def _worker_fetch(self, pid, epoch):
        try: eps = get_episodes(pid, self.settings, limit=300)
        except Exception as e: self.log_q.put(f"[错误] {e}"); return
        if epoch != self._check_epoch: return
        self.pending[pid] = eps
        done = {r[0] for r in db_conn().execute("SELECT track_id FROM downloaded WHERE podcast_id=?", (pid,))}; db_conn().close()
        for ep in eps: ep["is_downloaded"] = ep["eid"] in done
        self.root.after(0, lambda: self._populate_tree(pid, eps))
        new = sum(1 for e in eps if not e.get("is_downloaded"))
        self.log_q.put(f"[节目] {len(eps)} 集, {new} 未下载"); self.root.after(0, lambda: self.status_var.set(f"共 {len(eps)} 集, {new} 未下载"))

    def _populate_tree(self, pid, eps):
        cutoff = self.settings.get("cutoff_date", "2024-01-01")
        # 标准化日期：2024-3-01 → 2024-03-01
        try:
            parts = cutoff.strip().split("-")
            cutoff = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except:
            cutoff = "2024-01-01"
        self.tree.delete(*self.tree.get_children()); self.checked.clear(); self.episode_map.clear(); self._current_pid = pid
        for i, ep in enumerate(eps):
            d = ep.get("pubDate", "?")[:10]; iid = str(i); dn = ep.get("is_downloaded", False)
            # 日期过滤：截止日期之前的跳过
            if d != "?" and d < cutoff and not dn:
                continue
            self.tree.insert("", "end", iid=iid,
                             values=("N" if dn else "Y", d, ep.get("title", ""), "✓" if dn else ""),
                             tags=("odd" if i % 2 == 0 else "even",))
            self.checked[iid] = not dn; self.episode_map[iid] = ep

    def _download_selected(self):
        pid = getattr(self, "_current_pid", None)
        if not pid or pid not in self.pending: return
        tr = [ep for i, ep in self.episode_map.items() if self.checked.get(i, False)]
        if not tr: messagebox.showinfo("提示", "没有勾选节目"); return
        tot = len(tr); self._update_progress(0, tot)
        for i in self.episode_map:
            if self.checked.get(i): self.tree.set(i, "stat", "...")
        self.status_var.set(f"下载中 0/{tot}"); self.log_q.put(f"[下载] {tot} 个...")
        # 加入下载队列
        album = self.pod_title_var.get().split(" (")[0] if self.pod_title_var.get() else pid[:12]
        for ep in tr:
            self._queue_add(album, ep.get("title", "")[:40], ep.get("eid", ""))
        if self.settings.get("minimize_on_dl", False): self.root.iconify()
        threading.Thread(target=self._worker_download, args=(pid, tr, tot), daemon=True).start()

    def _worker_download(self, pid, tracks, total):
        dc = [0]; lk = threading.Lock()
        def dl_one(track):
            eid = track.get("eid", "")
            def cb(s, pct=0):
                lb = {"downloading": "下载中", "converting": "转码中", "done": "✓", "failed": "✗"}.get(s, "...")
                self.root.after(0, lambda e=eid, l=lb, p=pct: self._queue_update(e, l, p))
                for i, ep in self.episode_map.items():
                    if ep.get("eid") == eid:
                        lb2 = {"downloading": "下载...", "converting": "转码...", "done": "OK", "failed": "X"}.get(s, "...")
                        self.root.after(0, lambda ii=i, l=lb2: self.tree.set(ii, "stat", l)); break
            r = download_track(track, self.settings, self.log_q, status_cb=cb)
            with lk: dc[0] += 1; n = dc[0]
            self.root.after(0, lambda c=n, t=total: (self._update_progress(c, t), self.status_var.set(f"下载中 {c}/{t}")))
            return r
        with ThreadPoolExecutor(max_workers=max(1, self.settings["threads"])) as ex:
            for f in [ex.submit(dl_one, t) for t in tracks]:
                try: f.result(timeout=600)
                except Exception as e: self.log_q.put(f"[错误] {e}")
        self.log_q.put(f"[完成] {total} 个"); self.root.after(0, lambda: self._set_dl_ui(False))
        self.root.after(0, lambda: self.status_var.set(f"下载完成 {total} 个"))
        self.root.after(0, self.root.deiconify)
        if self.settings.get("sound_notify", False):
            try: import winsound; self.root.after(200, lambda: winsound.MessageBeep(0x40))
            except: pass

    def _set_dl_ui(self, a):
        pass  # 允许多专辑同时下载，按钮不再禁用

    def _build_download_queue_tab(self):
        f = ttk.Frame(self.notebook); self.notebook.add(f, text="下载队列")
        self.queue_map = {}  # eid -> {"iid": iid, "album": album, "title": title, "path": None}
        self.queue_tree = ttk.Treeview(f, columns=("album","title","status"), show="headings", height=20)
        self.queue_tree.heading("album", text="专辑"); self.queue_tree.column("album", width=150)
        self.queue_tree.heading("title", text="节目"); self.queue_tree.column("title", width=420)
        self.queue_tree.heading("status", text="状态"); self.queue_tree.column("status", width=100, anchor="center")
        sq = ttk.Scrollbar(f, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=sq.set)
        self.queue_tree.pack(side="left", fill="both", expand=True, padx=6, pady=6); sq.pack(side="right", fill="y")
        # 右键菜单已移除
        bf = ttk.Frame(f); bf.pack(pady=(4,6))
        ttk.Button(bf, text="清空已完成", command=self._queue_clear_done).pack(side="left", padx=4)
        ttk.Button(bf, text="清空全部", command=self._queue_clear_all).pack(side="left", padx=4)

    def _queue_add(self, album, title, eid):
        iid = f"q_{eid}_{len(self.queue_map)}"
        self.queue_tree.insert("", 0, iid=iid, values=(album, title, "等待"))
        self.queue_map[eid] = {"iid": iid, "album": album, "title": title}

    def _queue_update(self, eid, status, pct=0):
        if eid in self.queue_map:
            entry = self.queue_map[eid]
            if status in ("下载中", "转码中") and pct >= 0:
                label = f"{status} {pct}%"
            else:
                label = status
            self.queue_tree.set(entry["iid"], "status", label)
            if label == "✓":
                self.queue_tree.item(entry["iid"], tags=("done",))
                self.queue_tree.tag_configure("done", foreground="#4CAF50")
                self._queue_find_path(eid, entry["album"], entry["title"])
            elif label == "✗":
                self.queue_tree.item(entry["iid"], tags=("fail",))
                self.queue_tree.tag_configure("fail", foreground="#F44336")

    def _queue_clear_done(self):
        for eid, entry in list(self.queue_map.items()):
            val = self.queue_tree.set(entry["iid"], "status")
            if val in ("✓", "✗"):
                self.queue_tree.delete(entry["iid"]); del self.queue_map[eid]

    def _queue_clear_all(self):
        self.queue_tree.delete(*self.queue_tree.get_children()); self.queue_map.clear()

    def _update_progress(self, d, t): pass  # 进度条已移除

    def _set_all(self, v):
        for i in self.tree.get_children():
            ep = self.episode_map.get(i, {})
            if not ep.get("is_downloaded", False) or v: self.checked[i] = v; self.tree.set(i, "sel", "Y" if v else "N")

    def _on_tree_click(self, e):
        i = self.tree.identify_row(e.y)
        if i and self.tree.identify_column(e.x) == "#1": self.checked[i] = not self.checked.get(i, False); self.tree.set(i, "sel", "Y" if self.checked[i] else "N")

    def _sort_by_date(self):
        self._sort_asc = not self._sort_asc
        self.tree.heading("date", text=f"日期 {'↑' if self._sort_asc else '↓'}")
        rows = [(self.tree.item(i, "values")[1], i) for i in self.tree.get_children()]
        rows.sort(key=lambda r: r[0], reverse=not self._sort_asc)
        for iid in self.tree.get_children():
            self.tree.detach(iid)
        for _, iid in rows:
            self.tree.move(iid, "", "end")

    def _browse_dir(self):
        d = filedialog.askdirectory()
        if d: self.dir_var.set(d)

    def _auto_save(self, *_):
        try:
            self.settings.update({
                "download_dir": self.dir_var.get(),
                "cutoff_date": self.cutoff_var.get(),
                "threads": self.threads_var.get(),
                "format": self.format_var.get(), "bitrate": self.bitrate_var.get(),
                "minimize_on_dl": self.minimize_var.get(), "sound_notify": self.sound_var.get(),
                "device_id": self.did_var.get(),
            })
            save_settings(self.settings)
        except: pass

    def _refresh_pod_list(self):
        self.pod_list.delete(0, tk.END)
        conn = db_conn()
        conn.execute("CREATE TABLE IF NOT EXISTS podcasts (pid TEXT PRIMARY KEY, title TEXT, author TEXT, image TEXT, added_at TEXT)")
        for pid, title, _ in conn.execute("SELECT pid,title,author FROM podcasts"):
            # 查询已下载数
            dl_count = conn.execute("SELECT COUNT(*) FROM downloaded WHERE podcast_id=?", (pid,)).fetchone()[0]
            if dl_count > 0:
                label = f"{title} (✓{dl_count})"
            else:
                label = f"{title}"
            self.pod_list.insert(tk.END, label)
        conn.close()

    def _check_all(self):
        """一键检查所有播客更新"""
        if not is_logged_in(self.settings): messagebox.showwarning("提示", "请先登录"); return
        pids = []
        conn = db_conn()
        for pid, _, _ in conn.execute("SELECT pid,title,author FROM podcasts"):
            pids.append(pid)
        conn.close()
        if not pids:
            messagebox.showinfo("提示", "暂无播客，请先添加。"); return
        
        self.status_var.set(f"正在检查 {len(pids)} 个播客...")
        self.log_q.put(f"[检查] 开始检查 {len(pids)} 个播客更新")
        
        # 选当前选中的先检查，其余后台
        sel_pid = getattr(self, "_selected_pid", None)
        if sel_pid and sel_pid in pids:
            self._fetch_episodes()
            pids.remove(sel_pid)
        
        # 后台检查其余
        for pid in pids:
            self.log_q.put(f"[检查] 正在获取 {pid[:12]}...")
            try:
                eps = get_episodes(pid, self.settings, limit=300)
                done = {r[0] for r in db_conn().execute("SELECT track_id FROM downloaded WHERE podcast_id=?", (pid,))}
                db_conn().close()
                new_cnt = sum(1 for e in eps if e["eid"] not in done)
                self.log_q.put(f"[检查] {pid[:12]}: {len(eps)} 集, {new_cnt} 未下载")
            except Exception as e:
                self.log_q.put(f"[检查] {pid[:12]} 失败: {e}")
        
        self._refresh_pod_list()
        self.status_var.set(f"检查完成：{len(pids)+1} 个播客")
        self.log_q.put(f"[检查] 全部完成")

    def _clear_history(self):
        """清除下载记录"""
        if not messagebox.askyesno("警告", "确定要清除所有下载记录吗？\n\n"
                                             "清除后所有节目将显示为「未下载」状态，\n"
                                             "但已下载的文件不会被删除。\n\n"
                                             "确认清除？"):
            return
        conn = db_conn()
        conn.execute("DELETE FROM downloaded")
        conn.commit(); conn.close()
        self.log_q.put("[记录] 已清除所有下载记录")
        self.status_var.set("下载记录已清除")
        # 刷新当前列表
        if hasattr(self, "_current_pid") and self._current_pid in self.pending:
            pid = self._current_pid
            eps = self.pending[pid]
            for ep in eps: ep["is_downloaded"] = False
            self._populate_tree(pid, eps)

    def _export_csv(self):
        """导出下载历史为 CSV"""
        import csv
        dst = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"xiaoyuzhou_downloads_{datetime.datetime.now():%Y%m%d}.csv"
        )
        if not dst: return
        conn = db_conn()
        rows = conn.execute("SELECT pid, track_id, title, podcast_id, downloaded_at FROM downloaded ORDER BY downloaded_at DESC").fetchall()
        conn.close()
        with open(dst, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["播客ID", "节目ID", "标题", "播客名", "下载时间"])
            for pid, tid, title, pod_id, dt in rows:
                # 查播客名
                c = db_conn(); pod_row = c.execute("SELECT title FROM podcasts WHERE pid=?", (pid,)).fetchone(); c.close()
                pod_name = pod_row[0] if pod_row else pid[:12]
                w.writerow([pid, tid, title, pod_name, dt])
        self.log_q.put(f"[导出] {len(rows)} 条记录 → {dst}")
        self.status_var.set(f"已导出 {len(rows)} 条到 CSV")
        messagebox.showinfo("导出完成", f"已导出 {len(rows)} 条下载记录。")

    def _poll_log(self):
        while not self.log_q.empty():
            try:
                m = self.log_q.get_nowait()
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.log_box.configure(state="normal"); self.log_box.insert("end", f"[{ts}] {m}\n"); self.log_box.see("end"); self.log_box.configure(state="disabled")
                self.logfile.write(f"[{ts}] {m}\n"); self.logfile.flush()
            except queue.Empty: break
        self.root.after(200, self._poll_log)

    def _on_close(self): self.logfile.close(); self.root.destroy()


if __name__ == "__main__":
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception as e:
        import traceback as _tb
        err = _tb.format_exc()
        print(err)
        try:
            with open(os.path.join(SCRIPT_DIR, "crash.log"), "w") as f: f.write(err)
        except: pass
