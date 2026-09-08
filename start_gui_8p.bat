@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title 自走棋 8人局

rem ---------- 选择 Python 解释器 ----------
set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

%PY% -c "import sys;sys.exit(0)" >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有可用的 Python，请先安装 Python 3.11 并勾选 Add to PATH
    pause
    exit /b 1
)

rem ---------- 检查图形界面依赖 ----------
%PY% -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo [提示] 首次运行，正在安装依赖 pygame-ce ...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动执行: %PY% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

rem ---------- 启动 8 人局（可追加参数，如 --seed 7 --scale 2） ----------
%PY% launcher.py gui --players 8 %*

if errorlevel 1 (
    echo.
    echo [提示] 游戏已退出，异常码 %errorlevel%
    pause
)
