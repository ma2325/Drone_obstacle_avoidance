#!/usr/bin/env bash
# 启动 NavRL 强化学习导航节点（需 Conda 环境 NavRL + catkin 中已编译 navigation_runner）
# 权重查找顺序见下方 resolve_ckpt。
# 重要：必须先 source ROS，再 conda activate，并把 $CONDA_PREFIX/bin 放到 PATH 最前，
# 否则 rosrun 可能用系统 /usr/bin/python3，出现 No module named 'torch'。
set -euo pipefail

EXPLORE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAVRL_ROOT="${NAVRL_ROOT:-${EXPLORE_ROOT}/../NavRL}"
if [[ ! -d "$NAVRL_ROOT/ros1/navigation_runner" ]]; then
  NAVRL_ROOT="${HOME}/projects/NavRL"
fi
CATKIN_WS="${CATKIN_WS:-${HOME}/catkin_ws}"
# 默认 0：启用 onboard_detector / 动态障碍等安全输入，否则无人机几乎不会主动绕行人。
# 若需纯策略飞（调试用）可 export NAVRL_DISABLE_SAFETY_INPUT=1
export NAVRL_DISABLE_SAFETY_INPUT="${NAVRL_DISABLE_SAFETY_INPUT:-0}"

if [[ ! -d "$CATKIN_WS/devel" ]]; then
  echo "[navrl-nav] 错误: 未找到 Catkin 工作空间 $CATKIN_WS/devel"
  exit 1
fi

source /opt/ros/noetic/setup.bash
source "$CATKIN_WS/devel/setup.bash"

if ! command -v rospack &>/dev/null; then
  echo "[navrl-nav] 错误: rospack 不可用"
  exit 1
fi
if ! rospack find navigation_runner &>/dev/null; then
  echo "[navrl-nav] 错误: ROS 包 navigation_runner 未找到"
  exit 1
fi

CKPT_DIR="$(rospack find navigation_runner)/scripts/ckpts"
DEFAULT_CKPT="$CKPT_DIR/navrl_checkpoint.pt"
QD_DIR="$NAVRL_ROOT/quick-demos/ckpts"

resolve_ckpt() {
  if [[ -n "${NAVRL_CHECKPOINT:-}" ]] && [[ -f "${NAVRL_CHECKPOINT}" ]]; then
    echo "${NAVRL_CHECKPOINT}"
    return 0
  fi
  if [[ -f "$DEFAULT_CKPT" ]]; then
    echo "$DEFAULT_CKPT"
    return 0
  fi
  if [[ -f "$NAVRL_ROOT/navrl_checkpoint.pt" ]]; then
    echo "$NAVRL_ROOT/navrl_checkpoint.pt"
    return 0
  fi
  if [[ -f "$QD_DIR/navrl_checkpoint.pt" ]]; then
    echo "$QD_DIR/navrl_checkpoint.pt"
    return 0
  fi
  if [[ -d "$QD_DIR" ]]; then
    local f
    f=$(ls -1 "$QD_DIR"/*.pt 2>/dev/null | head -1 || true)
    if [[ -n "$f" ]] && [[ -f "$f" ]]; then
      echo "$f"
      return 0
    fi
  fi
  return 1
}

CKPT_PATH=""
if ! CKPT_PATH="$(resolve_ckpt)"; then
  echo "[navrl-nav] 错误: 未找到 .pt 权重。请任选其一:"
  echo "  - $DEFAULT_CKPT"
  echo "  - $NAVRL_ROOT/navrl_checkpoint.pt"
  echo "  - $QD_DIR/navrl_checkpoint.pt（或该目录下任意 .pt）"
  echo "  - 或 export NAVRL_CHECKPOINT=/绝对路径/xxx.pt"
  exit 1
fi
export NAVRL_CHECKPOINT="$CKPT_PATH"
echo "[navrl-nav] 使用权重: $NAVRL_CHECKPOINT"

CONDA_SH=""
for _base in "$HOME/miniconda3" "$HOME/mambaforge" "$HOME/anaconda3" "$HOME/miniforge3"; do
  if [[ -f "$_base/etc/profile.d/conda.sh" ]]; then
    CONDA_SH="$_base/etc/profile.d/conda.sh"
    break
  fi
done
if [[ -z "$CONDA_SH" ]]; then
  echo "[navrl-nav] 错误: 未找到 conda"
  exit 1
fi

TP_TD="$NAVRL_ROOT/isaac-training/third_party/tensordict"
TP_RL="$NAVRL_ROOT/isaac-training/third_party/rl"
if [[ ! -d "$TP_RL" ]]; then
  echo "[navrl-nav] 错误: 未找到 $TP_RL"
  exit 1
fi

NAV_RUNNER_SCRIPTS="$(rospack find navigation_runner)/scripts"
if [[ ! -f "$NAV_RUNNER_SCRIPTS/navigation.py" ]]; then
  echo "[navrl-nav] 错误: 未找到 $NAV_RUNNER_SCRIPTS/navigation.py"
  exit 1
fi

# 将 NavRL 仓库内的 navigation.py 同步到 catkin（含 takeoff_pose 竞态修复）；设 NAVRL_SYNC_NAVIGATION_PY=0 可跳过
SRC_NAV="$NAVRL_ROOT/ros1/navigation_runner/scripts/navigation.py"
if [[ "${NAVRL_SYNC_NAVIGATION_PY:-1}" == "1" ]] && [[ -f "$SRC_NAV" ]]; then
  if ! cmp -s "$SRC_NAV" "$NAV_RUNNER_SCRIPTS/navigation.py" 2>/dev/null; then
    echo "[navrl-nav] 同步 navigation.py（NavRL 仓库 -> catkin_ws）..."
    cp -a "$SRC_NAV" "$NAV_RUNNER_SCRIPTS/navigation.py"
  fi
fi

source "$CONDA_SH"
set +u
conda activate NavRL
set -u
if [[ -z "${CONDA_PREFIX:-}" ]]; then
  echo "[navrl-nav] 错误: conda activate NavRL 后 CONDA_PREFIX 为空"
  exit 1
fi
export PATH="$CONDA_PREFIX/bin:$PATH"

PY="$CONDA_PREFIX/bin/python3"
if [[ ! -x "$PY" ]]; then
  echo "[navrl-nav] 错误: 未找到 $PY"
  exit 1
fi
echo "[navrl-nav] 使用解释器: $PY"
# Conda 的 python 需能 import rospy：把 Noetic 的 dist-packages 放在 PYTHONPATH 最前
ROS_PY="/opt/ros/noetic/lib/python3/dist-packages"
if [[ ! -d "$ROS_PY" ]]; then
  echo "[navrl-nav] 错误: 未找到 $ROS_PY"
  exit 1
fi
export PYTHONPATH="$ROS_PY:$NAV_RUNNER_SCRIPTS:$TP_TD:$TP_RL:${PYTHONPATH:-}"

"$PY" -c "import rospy, torch; print('[navrl-nav] rospy OK, torch', torch.__version__)" || {
  echo "[navrl-nav] 错误: Conda Python 无法同时 import rospy 与 torch，请检查 NavRL 环境与 ROS 路径"
  exit 1
}

# NumPy 2.x 常导致 torch/torchrl 报 \"Numpy is not available\" / raycast 里 tensor 转 numpy 失败
if ! "$PY" -c "import numpy as np; exit(0 if int(np.__version__.split('.')[0]) < 2 else 1)" 2>/dev/null; then
  echo "[navrl-nav] 检测到 NumPy>=2，正在安装 numpy<2 到当前 Conda 环境（避免导航节点崩溃）..."
  "$PY" -m pip install "numpy>=1.23,<2" -q || {
    echo "[navrl-nav] 错误: 请手动执行: conda activate NavRL && pip install 'numpy>=1.23,<2'"
    exit 1
  }
fi
"$PY" -c "import numpy as np; print('[navrl-nav] numpy', np.__version__)"

NODE_SCRIPT="$NAV_RUNNER_SCRIPTS/navigation_node.py"
echo "[navrl-nav] NavRL_ROOT=$NAVRL_ROOT"
echo "[navrl-nav] 启动: $PY $NODE_SCRIPT"
# 勿用 rosrun：devel 里入口脚本的 shebang 常为 /usr/bin/python3，会绕过 Conda 导致无 torch
exec "$PY" "$NODE_SCRIPT"
