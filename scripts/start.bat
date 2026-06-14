@echo off
echo ============================
echo   Agent Maona 启动脚本
echo ============================

cd /d "%~dp0backend"
echo [1/2] 启动 Python 后端...
start "Maona-Backend" python main.py --no-browser

echo [2/2] 启动 Electron 前端...
cd /d "%~dp0"
call npm start

pause
