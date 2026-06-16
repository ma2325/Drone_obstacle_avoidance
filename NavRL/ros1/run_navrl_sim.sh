#!/usr/bin/env bash
set -eo pipefail

# One-command launcher for NavRL ROS1 obstacle-avoidance simulation.
# It starts:
# 1) Gazebo simulator
# 2) Perception + safety stack
# 3) NavRL navigation node (Conda env: NavRL)
#
# Paths: uav_simulator is resolved via rospack (works for both
#   ~/catkin_ws/src/uav_simulator and ~/catkin_ws/src/ros1/uav_simulator).
# NavRL repo root is inferred from this script location (../.. from ros1/).

ROS1_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAVRL_ROOT="$(cd "$ROS1_DIR/.." && pwd)"
CATKIN_WS="${CATKIN_WS:-$HOME/catkin_ws}"
LOG_DIR="$ROS1_DIR/.run_logs"
mkdir -p "$LOG_DIR"

if [[ ! -d "$CATKIN_WS/devel" ]]; then
  echo "[run-navrl] Missing $CATKIN_WS/devel. Please build catkin_ws first."
  exit 1
fi

CONDA_SH=""
for _conda_base in "$HOME/miniconda3" "$HOME/mambaforge" "$HOME/anaconda3"; do
  if [[ -f "$_conda_base/etc/profile.d/conda.sh" ]]; then
    CONDA_SH="$_conda_base/etc/profile.d/conda.sh"
    break
  fi
done
if [[ -z "$CONDA_SH" ]]; then
  echo "[run-navrl] Missing Conda init (tried miniconda3, mambaforge, anaconda3)."
  exit 1
fi

source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"

if ! rospack find navigation_runner >/dev/null 2>&1; then
  echo "[run-navrl] ROS package navigation_runner not found."
  exit 1
fi
if ! rospack find uav_simulator >/dev/null 2>&1; then
  echo "[run-navrl] ROS package uav_simulator not found."
  exit 1
fi

UAV_SIM_DIR="$(rospack find uav_simulator)"
if [[ ! -f "$UAV_SIM_DIR/gazeboSetup.bash" ]]; then
  echo "[run-navrl] Missing gazeboSetup.bash under: $UAV_SIM_DIR"
  exit 1
fi

cleanup() {
  echo "[run-navrl] Stopping launched processes..."
  pkill -f "roslaunch uav_simulator start.launch" >/dev/null 2>&1 || true
  pkill -f "roslaunch navigation_runner safety_and_perception_sim.launch" >/dev/null 2>&1 || true
  pkill -f "rosrun navigation_runner navigation_node.py" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[run-navrl] uav_simulator -> $UAV_SIM_DIR"
echo "[run-navrl] NavRL root -> $NAVRL_ROOT"

echo "[run-navrl] Launching Gazebo simulator..."
nohup bash -lc "source /opt/ros/noetic/setup.bash; source '$CATKIN_WS/devel/setup.bash'; source '$UAV_SIM_DIR/gazeboSetup.bash'; roslaunch uav_simulator start.launch gui:=false" \
  > "$LOG_DIR/01_gazebo.log" 2>&1 &
sleep 6

echo "[run-navrl] Launching perception + safety stack..."
nohup bash -lc "source /opt/ros/noetic/setup.bash; source '$CATKIN_WS/devel/setup.bash'; roslaunch navigation_runner safety_and_perception_sim.launch rviz:=false" \
  > "$LOG_DIR/02_safety_perception.log" 2>&1 &
sleep 6

echo "[run-navrl] Launching NavRL navigation node..."
nohup bash -lc "source '$CONDA_SH'; conda activate NavRL; export PYTHONPATH='$NAVRL_ROOT/isaac-training/third_party/tensordict:$NAVRL_ROOT/isaac-training/third_party/rl':\$PYTHONPATH; export NAVRL_DISABLE_SAFETY_INPUT=1; source /opt/ros/noetic/setup.bash; source '$CATKIN_WS/devel/setup.bash'; rosrun navigation_runner navigation_node.py" \
  > "$LOG_DIR/03_navigation_node.log" 2>&1 &
sleep 4

echo "[run-navrl] All services requested."
echo "[run-navrl] Logs:"
echo "  - $LOG_DIR/01_gazebo.log"
echo "  - $LOG_DIR/02_safety_perception.log"
echo "  - $LOG_DIR/03_navigation_node.log"
echo "[run-navrl] Open RViz and use '2D Nav Goal' to send target."
echo "[run-navrl] Press Ctrl+C in this terminal to stop all."

while true; do
  sleep 2
done
