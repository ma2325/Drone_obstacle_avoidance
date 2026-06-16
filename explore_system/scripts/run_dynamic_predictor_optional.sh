#!/usr/bin/env bash
# 可选启动 dynamic_predictor（行人轨迹预测 → 供 NavRL / 局部规划做动态避障）。
# 需已在 catkin_ws 中编译该包；未安装时本脚本直接退出 0，不影响一键启动。
#
# 启用一键启动中的本步骤：
#   export EXPLORE_LAUNCH_DYNAMIC_PREDICTOR=1
#
# 可选指定 launch（默认 predictor_with_fake_detector.launch，与 utils 示例一致）：
#   export DYNAMIC_PREDICTOR_LAUNCH=your.launch
set -euo pipefail

source /opt/ros/noetic/setup.bash
CATKIN_WS="${CATKIN_WS:-$HOME/catkin_ws}"
if [[ -f "$CATKIN_WS/devel/setup.bash" ]]; then
  # shellcheck disable=SC1090
  source "$CATKIN_WS/devel/setup.bash"
fi

if ! command -v rospack &>/dev/null; then
  echo "[dynamic_predictor] rospack 不可用，跳过"
  exit 0
fi

if ! rospack find dynamic_predictor &>/dev/null; then
  echo "[dynamic_predictor] 未找到 ROS 包 dynamic_predictor，跳过（预测避障需自行安装并 catkin_make）"
  exit 0
fi

PKG="$(rospack find dynamic_predictor)"
LAUNCH="${DYNAMIC_PREDICTOR_LAUNCH:-predictor_with_fake_detector.launch}"
if [[ ! -f "$PKG/launch/$LAUNCH" ]]; then
  FIRST="$(ls -1 "$PKG"/launch/*.launch 2>/dev/null | head -1 || true)"
  if [[ -z "$FIRST" ]]; then
    echo "[dynamic_predictor] 包内无 launch 文件，跳过"
    exit 0
  fi
  LAUNCH="$(basename "$FIRST")"
  echo "[dynamic_predictor] 未找到 $DYNAMIC_PREDICTOR_LAUNCH，改用 $LAUNCH"
fi

echo "[dynamic_predictor] roslaunch dynamic_predictor $LAUNCH"
exec roslaunch dynamic_predictor "$LAUNCH"
