#!/usr/bin/env bash
# 在手动 roslaunch 前执行: source ~/projects/NavRL/ros1/source_navrl_gazebo_env.bash
# 自动用 rospack 找到 uav_simulator（无论包在 src/uav_simulator 还是 src/ros1/uav_simulator）。

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "请用 source 执行: source $(basename "$0")" >&2
  exit 1
fi

CATKIN_WS="${CATKIN_WS:-$HOME/catkin_ws}"

if [[ ! -f /opt/ros/noetic/setup.bash ]]; then
  echo "[navrl-env] 未找到 /opt/ros/noetic/setup.bash" >&2
  return 1 2>/dev/null || exit 1
fi
if [[ ! -f "$CATKIN_WS/devel/setup.bash" ]]; then
  echo "[navrl-env] 未找到 $CATKIN_WS/devel/setup.bash（先 catkin_make）" >&2
  return 1 2>/dev/null || exit 1
fi

source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"

_UAV_SIM_DIR="$(rospack find uav_simulator 2>/dev/null)" || true
if [[ -z "$_UAV_SIM_DIR" ]]; then
  echo "[navrl-env] rospack 找不到 uav_simulator" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=/dev/null
source "$_UAV_SIM_DIR/gazeboSetup.bash"
echo "[navrl-env] uav_simulator: $_UAV_SIM_DIR"

unset _UAV_SIM_DIR
