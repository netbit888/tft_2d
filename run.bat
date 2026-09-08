@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
title 自走棋 1v1

rem ---------- 选择 Python 解释器 ----------
set "PY=python"
where py >nul 2>nul
if %errorlevel%==0 set "PY=py -3"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

echo 使用解释器: %PY%
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

rem ---------- 主菜单 ----------
:menu
cls
echo ============================================
echo            自走棋 1v1  控制台
echo ============================================
echo   [1] 启动游戏（图形界面）
echo   [2] 命令行对局（文字版）
echo   [3] 自动对局演示（双方由电脑操作）
echo   [4] 平衡统计 bench
echo   [5] 内核自检 mirror
echo   [0] 退出
echo ============================================
set "CH="
set /p "CH=请输入序号后回车: "

if "%CH%"=="1" %PY% app.py & goto menu
if "%CH%"=="2" %PY% play.py & goto menu
if "%CH%"=="3" %PY% play.py --auto & pause & goto menu
if "%CH%"=="4" %PY% tools\simulate.py --bench 3000 & pause & goto menu
if "%CH%"=="5" %PY% tools\simulate.py --mirror 3000 & pause & goto menu
if "%CH%"=="0" exit /b 0

echo 无效的选择，请重新输入
timeout /t 1 >nul
goto menu
