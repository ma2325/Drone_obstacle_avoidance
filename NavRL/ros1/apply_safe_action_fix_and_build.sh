#!/usr/bin/env bash
# Sync fixed safeAction.cpp from this NavRL tree into catkin_ws and rebuild navigation_runner.
set -euo pipefail

NAVRL_ROS1="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CATKIN_WS="${CATKIN_WS:-$HOME/catkin_ws}"
SRC_CPP="$NAVRL_ROS1/navigation_runner/include/navigation_runner/safeAction.cpp"
DST_CPP="$CATKIN_WS/src/navigation_runner/include/navigation_runner/safeAction.cpp"

if [[ ! -f "$SRC_CPP" ]]; then
  echo "[err] Missing $SRC_CPP"
  exit 1
fi
if [[ ! -f "$DST_CPP" ]]; then
  echo "[err] Missing $DST_CPP — is navigation_runner under $CATKIN_WS/src ?"
  exit 1
fi

cp -v "$SRC_CPP" "$DST_CPP"

source /opt/ros/noetic/setup.bash
cd "$CATKIN_WS"
catkin_make -DCMAKE_BUILD_TYPE=Release

echo ""
echo "[ok] Build finished. Next:"
echo "  source $CATKIN_WS/devel/setup.bash"
echo "  # Restart perception + safety (terminal where you had roslaunch ...): Ctrl+C then:"
echo "  roslaunch navigation_runner safety_and_perception_sim.launch"
echo "  # Confirm log shows: [SafeAction]: Safety distance is set to 0.3"
