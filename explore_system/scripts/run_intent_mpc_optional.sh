#!/usr/bin/env bash
# Intent-MPC（Zhefan-Xu/Intent-MPC）：需在 catkin_ws/src 克隆并编译 autonomous_flight 包。
# 官方演示：roslaunch autonomous_flight intent_mpc_demo.launch
# 注意：该 launch 通常包含完整规划闭环，与当前栈里的 NavRL 节点会冲突，请二选一：
#   - 要么从 processes_config.json 中暂时去掉 navrl_rl_navigation 再设 EXPLORE_LAUNCH_INTENT_MPC=1
#   - 要么仅用官方 README 流程单独终端运行，不要用地面站一键启动同时拉两套规划器
# 参考：https://github.com/Zhefan-Xu/Intent-MPC
set -euo pipefail

source /opt/ros/noetic/setup.bash
if [[ -f "${CATKIN_WS:-$HOME/catkin_ws}/devel/setup.bash" ]]; then
  # shellcheck disable=SC1090
  source "${CATKIN_WS:-$HOME/catkin_ws}/devel/setup.bash"
fi

if ! command -v rospack &>/dev/null; then
  echo "[intent-mpc] rospack 不可用"
  exit 1
fi
if ! rospack find autonomous_flight &>/dev/null; then
  echo "[intent-mpc] 未找到 ROS 包 autonomous_flight。"
  echo "  cd ~/catkin_ws/src && git clone https://github.com/Zhefan-Xu/Intent-MPC.git && cd ~/catkin_ws && catkin_make"
  exit 1
fi

LAUNCH_FILE="${INTENT_MPC_LAUNCH:-intent_mpc_demo.launch}"
echo "[intent-mpc] roslaunch autonomous_flight ${LAUNCH_FILE}"
exec roslaunch autonomous_flight "${LAUNCH_FILE}"
