#!/usr/bin/env bash
set -e
set -u
set -o pipefail

CATKIN_WS="${CATKIN_WS:-$HOME/catkin_ws}"
ROS_SETUP="/opt/ros/noetic/setup.bash"
CATKIN_SETUP="$CATKIN_WS/devel/setup.bash"

ok()   { echo "[ OK ] $*"; }
warn() { echo "[WARN] $*"; }
fail() { echo "[FAIL] $*"; }

if [[ ! -f "$ROS_SETUP" ]]; then
  fail "Missing $ROS_SETUP"
  exit 1
fi
if [[ ! -f "$CATKIN_SETUP" ]]; then
  fail "Missing $CATKIN_SETUP (build catkin_ws first)"
  exit 1
fi

source "$ROS_SETUP"
source "$CATKIN_SETUP"

echo "=== NavRL ROS1 Health Check ==="
echo "ROS_MASTER_URI=${ROS_MASTER_URI:-<unset>}"
echo "ROS_DISTRO=${ROS_DISTRO:-<unset>}"
echo

if rostopic list >/dev/null 2>&1; then
  ok "ROS master reachable"
else
  fail "ROS master not reachable"
  exit 2
fi

echo
echo "== Params =="
if rosparam get /rl/use_px4 >/dev/null 2>&1; then
  use_px4="$(rosparam get /rl/use_px4)"
  if [[ "$use_px4" == "false" ]]; then
    ok "/rl/use_px4 = false (non-PX4 mode)"
  else
    warn "/rl/use_px4 = $use_px4"
  fi
else
  warn "/rl/use_px4 not set (navigation defaults True -> may wait for /mavros/local_position/odom)"
fi

echo
echo "== Nodes =="
required_nodes=("/gazebo" "/gt_odom_throttle" "/occupancy_map_node" "/safe_action_node")
for n in "${required_nodes[@]}"; do
  if rosnode list | rg -x "$n" >/dev/null 2>&1; then
    ok "node $n"
  else
    warn "node $n missing"
  fi
done
if rosnode list | rg "fake_detector_node" >/dev/null 2>&1; then
  ok "node /fake_detector_node"
else
  warn "node /fake_detector_node missing (dynamic obstacle service may fail)"
fi

echo
echo "== Services =="
if rosservice list | rg "^/onboard_detector/get_dynamic_obstacles$" >/dev/null 2>&1; then
  ok "service /onboard_detector/get_dynamic_obstacles"
else
  warn "service /onboard_detector/get_dynamic_obstacles missing"
fi
for s in /rl_navigation/get_safe_action /occupancy_map/raycast; do
  if rosservice list | rg -x "$s" >/dev/null 2>&1; then
    ok "service $s"
  else
    warn "service $s missing"
  fi
done

echo
echo "== Topics =="
topics=("/CERLAB/quadcopter/odom" "/CERLAB/quadcopter/odom_raw" "/move_base_simple/goal" "/rl_navigation/raycast" "/rl_navigation/cmd")
for t in "${topics[@]}"; do
  if rostopic list | rg -x "$t" >/dev/null 2>&1; then
    ok "topic $t exists"
  else
    warn "topic $t missing"
  fi
done

echo
echo "Sampling rates (3s each)..."
timeout 3s rostopic hz /CERLAB/quadcopter/odom 2>/dev/null | rg "average rate|no new messages" || true
timeout 3s rostopic hz /CERLAB/quadcopter/odom_raw 2>/dev/null | rg "average rate|no new messages" || true
timeout 3s rostopic hz /clock 2>/dev/null | rg "average rate|no new messages" || true

echo
echo "Done. Resolve WARN/FAIL before demo."
