@echo off
chcp 65001 >nul
title 小宇宙播客下载器 v1
cd /d "%~dp0"
python xiaoyuzhou_watcher.py
pause
