@echo off
chcp 65001 >nul
title 企微群会话分析 - 本地开发一键启动

echo ============================================
echo   启动后端 (FastAPI :8000) 和 前端 (Vite :5173)
echo ============================================

cd /d "%~dp0backend"
start "后端 :8000" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

cd /d "%~dp0frontend"
start "前端 :5173" cmd /k "npm run dev -- --host 127.0.0.1"

echo 等待服务启动...
timeout /t 4 >nul
start http://127.0.0.1:5173

echo.
echo 已在浏览器打开 http://127.0.0.1:5173
echo 关闭这两个弹出的黑窗口即可停止服务。
