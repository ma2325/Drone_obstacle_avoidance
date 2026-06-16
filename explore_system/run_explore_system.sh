#!/usr/bin/env bash
# 在「已启动 roscore」的前提下运行地面站；务必使用系统 Python，避免 conda 缺少 rospkg。
set -e
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"

if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
  echo "[提示] 当前处于 conda 环境: $CONDA_DEFAULT_ENV"
  echo "       若启动报错缺少 rospkg，请先执行: conda deactivate"
fi

if [ ! -f /opt/ros/noetic/setup.bash ]; then
  echo "错误: 未找到 /opt/ros/noetic/setup.bash，请先安装 ROS Noetic。"
  exit 1
fi
# shellcheck source=/dev/null
source /opt/ros/noetic/setup.bash
# 与 start.py 子进程一致：避免 conda 的 python3 抢走 env，导致 xacro 缺 rospkg
export PATH="/usr/bin:/usr/local/bin:$PATH"

# 若你有规划栈工作空间，取消下一行注释或改成你的路径
# source "$HOME/catkin_ws_dyn/devel/setup.bash"

export ROS_MASTER_URI="${ROS_MASTER_URI:-http://127.0.0.1:11311}"
export ROS_HOSTNAME="${ROS_HOSTNAME:-127.0.0.1}"

exec /usr/bin/python3 ./start.py "$@"
