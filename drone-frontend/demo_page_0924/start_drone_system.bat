@echo off
echo ========================================
echo   F410无人机地面站启动脚本
echo ========================================
echo.

echo [提示] 请确保：
echo   1. 无人机已开机
echo   2. 数传已连接
echo   3. 数传端口是 UDP 8080
echo.
pause

echo.
echo [步骤1] 启动MAVProxy数据分流...
start "MAVProxy" cmd /k "conda activate drone_f410 && python -m MAVProxy.mavproxy --master=udp:0.0.0.0:8080 --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551"
timeout /t 5 /nobreak

echo.
echo [步骤2] 启动Python WebSocket桥接服务...
start "Python桥接" cmd /k "conda activate drone_f410 && cd /d D:\大创-无人机\demo_page_0924 && python drone_bridge.py"
timeout /t 3 /nobreak

echo.
echo [步骤3] 启动Vue前端开发服务器...
start "Vue前端" cmd /k "cd /d D:\大创-无人机\demo_page_0924 && npm run dev"

echo.
echo ========================================
echo   ✅ 所有服务已启动！
echo ========================================
echo.
echo 📱 等待15秒后，浏览器访问：
echo    http://localhost:5173/drone-test
echo.
echo ⚠️  如需停止，请关闭所有弹出的窗口
echo ========================================
pause

