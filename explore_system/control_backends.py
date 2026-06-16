#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

# (成功?, 说明)；None 表示未起 Gazebo 或未启用
GazeboTeleportResult = Optional[Tuple[bool, str]]


def _quat_xyzw_from_rpy(roll: float, pitch: float, yaw: float) -> Tuple[float, float, float, float]:
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return (qx, qy, qz, qw)


def gazebo_teleport_drone_to_spawn(rospy, cfg: dict) -> GazeboTeleportResult:
    """
    Gazebo Classic：暂停物理 → set_model_state 瞬移回出生位姿并清零 twist → 恢复物理。
    返回 (True, 说明) / (False, 错误说明)；None 表示未起 Gazebo 或未启用（可忽略）。
    """
    g = (cfg or {}).get("gazebo") or {}
    if not bool(g.get("enable_spawn_teleport", True)):
        return None
    try:
        from gazebo_msgs.msg import ModelState
        from gazebo_msgs.srv import SetModelState
        from geometry_msgs.msg import Point, Pose, Quaternion, Twist
        from std_srvs.srv import Empty
    except Exception:
        return None

    svc = str(g.get("set_model_state_service", "/gazebo/set_model_state"))
    pause_svc = str(g.get("pause_physics_service", "/gazebo/pause_physics"))
    unpause_svc = str(g.get("unpause_physics_service", "/gazebo/unpause_physics"))
    model_name = str(g.get("drone_model_name", "quadcopter"))
    xyz = g.get("spawn_xyz", [0.0, 0.0, 0.2])
    rpy = g.get("spawn_rpy", [0.0, 0.0, 0.0])

    try:
        rospy.wait_for_service(svc, timeout=0.45)
    except Exception:
        return None

    try:
        rospy.wait_for_service(pause_svc, timeout=0.25)
        rospy.ServiceProxy(pause_svc, Empty)()
    except Exception:
        pass

    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    rr, pp, yy = float(rpy[0]), float(rpy[1]), float(rpy[2])
    qx, qy, qz, qw = _quat_xyzw_from_rpy(rr, pp, yy)
    st = ModelState()
    st.model_name = model_name
    st.reference_frame = "world"
    st.pose = Pose(
        position=Point(x=x, y=y, z=z),
        orientation=Quaternion(x=qx, y=qy, z=qz, w=qw),
    )
    st.twist = Twist()
    try:
        resp = rospy.ServiceProxy(svc, SetModelState)(st)
        if not resp.success:
            return (
                False,
                f"Gazebo set_model_state 未成功: {getattr(resp, 'status_message', '')}",
            )
    except Exception as e:
        return (False, f"Gazebo set_model_state 异常: {e}")

    try:
        rospy.wait_for_service(unpause_svc, timeout=0.35)
        rospy.ServiceProxy(unpause_svc, Empty)()
    except Exception:
        pass

    try:
        rospy.sleep(0.06)
    except Exception:
        time.sleep(0.06)
    return (
        True,
        f"Gazebo 已将「{model_name}」瞬移回 ({x:.2f},{y:.2f},{z:.2f}) 并清零速度",
    )


def _merge_gazebo_rescue_msgs(parts: List[str], gr: GazeboTeleportResult) -> None:
    if gr is None:
        return
    ok, msg = gr
    if msg:
        parts.append(("" if ok else "【注意】") + msg)


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@dataclass
class ControlResult:
    ok: bool
    message: str


class BaseBackend:
    name: str = "base"

    def takeoff(self) -> ControlResult:
        return ControlResult(False, "takeoff not implemented")

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        return ControlResult(False, "nudge not implemented")

    def start_continuous(self, direction: str) -> ControlResult:
        return ControlResult(False, "continuous not implemented")

    def stop_continuous(self, direction: str) -> ControlResult:
        return ControlResult(False, "continuous not implemented")

    def self_rescue(self) -> ControlResult:
        """仿真翻机/贴地卡住时的复位再起飞；各后端自行实现或返回说明。"""
        return ControlResult(
            False,
            "当前控制后端未实现仿真复位再起飞；请检查 control_config 或在仿真器中手动重置模型。",
        )


class CerlabUavSimulatorBackend(BaseBackend):
    """
    uav_simulator（CERLAB）链路：直接发布 /CERLAB/quadcopter/* 话题控制 Gazebo 插件。
    这条链路不依赖 MAVROS/PX4，适合本仓库内置的 uav_simulator 仿真。
    """

    name = "cerlab_uav_simulator"

    def __init__(self, rospy, cfg: dict):
        self.rospy = rospy
        self.cfg = cfg or {}
        c = (self.cfg.get("cerlab") or {})
        self.takeoff_topic = c.get("takeoff_topic", "/CERLAB/quadcopter/takeoff")
        self.land_topic = c.get("land_topic", "/CERLAB/quadcopter/land")
        self.reset_topic = c.get("reset_topic", "/CERLAB/quadcopter/reset")
        self.cmd_vel_topic = c.get("cmd_vel_topic", "/CERLAB/quadcopter/cmd_vel")
        self.vel_mode_topic = c.get("vel_mode_topic", "/CERLAB/quadcopter/vel_mode")
        self.posctrl_topic = c.get("posctrl_topic", "/CERLAB/quadcopter/posctrl")

        self.speed = float(c.get("body_speed_mps", 1.0))
        self.rate_hz = float(c.get("control_rate_hz", 20))

        self._lock = threading.Lock()
        self._continuous = set()
        self._shutdown = False

        from geometry_msgs.msg import TwistStamped
        from std_msgs.msg import Bool, Empty

        self._TwistStamped = TwistStamped
        self._Empty = Empty
        self._pub_cmd_vel = rospy.Publisher(self.cmd_vel_topic, TwistStamped, queue_size=10)
        self._pub_takeoff = rospy.Publisher(self.takeoff_topic, Empty, queue_size=10)
        self._pub_vel_mode = rospy.Publisher(self.vel_mode_topic, Bool, queue_size=1)
        self._pub_reset = rospy.Publisher(self.reset_topic, Empty, queue_size=10)
        self._pub_posctrl = rospy.Publisher(self.posctrl_topic, Bool, queue_size=1)

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        # 进入速度模式（若插件订阅存在）
        try:
            self._pub_vel_mode.publish(Bool(data=True))
        except Exception:
            pass

    def takeoff(self) -> ControlResult:
        try:
            from std_msgs.msg import Bool
            self._pub_vel_mode.publish(Bool(data=True))
        except Exception:
            pass
        try:
            self._pub_takeoff.publish(self._Empty())
            return ControlResult(True, f"已发送 takeoff 到 {self.takeoff_topic}")
        except Exception as e:
            return ControlResult(False, f"起飞命令异常: {e}")

    def self_rescue(self) -> ControlResult:
        """Gazebo 瞬移（解穿插）+ 插件 reset + posctrl/takeoff。"""
        from std_msgs.msg import Bool

        parts: List[str] = []
        _merge_gazebo_rescue_msgs(parts, gazebo_teleport_drone_to_spawn(self.rospy, self.cfg))

        try:
            self._pub_reset.publish(self._Empty())
        except Exception as e:
            return ControlResult(False, f"复位指令异常: {e}")
        try:
            self.rospy.sleep(0.5)
        except Exception:
            time.sleep(0.5)
        try:
            self._pub_vel_mode.publish(Bool(data=False))
            self._pub_posctrl.publish(Bool(data=True))
        except Exception:
            pass
        try:
            self._pub_takeoff.publish(self._Empty())
        except Exception as e:
            return ControlResult(False, f"复位已发但起飞失败: {e}")
        try:
            self._pub_vel_mode.publish(Bool(data=True))
        except Exception:
            pass
        parts.append("已发送仿真复位并就绪起飞（reset→posctrl→takeoff→vel_mode），请在画面中确认姿态与高度")
        return ControlResult(True, "；".join([p for p in parts if p]))

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        ok = self.start_continuous(direction)
        if not ok.ok:
            return ok
        time.sleep(max(0.05, float(duration_sec)))
        self.stop_continuous(direction)
        return ControlResult(True, f"脉冲 {direction} {duration_sec:.2f}s")

    def start_continuous(self, direction: str) -> ControlResult:
        with self._lock:
            self._continuous.add(direction)
        return ControlResult(True, f"持续 {direction} 开")

    def stop_continuous(self, direction: str) -> ControlResult:
        with self._lock:
            self._continuous.discard(direction)
        return ControlResult(True, f"持续 {direction} 关")

    def _loop(self):
        period = 1.0 / max(5.0, float(self.rate_hz))
        while (not self._shutdown) and (not self.rospy.is_shutdown()):
            with self._lock:
                cmds = set(self._continuous)

            # TwistStamped：x前 y左 z上（这里按常见 ENU 约定）
            vx = vy = vz = 0.0
            s = self.speed
            if "forward" in cmds:
                vx += s
            if "backward" in cmds:
                vx -= s
            if "left" in cmds:
                vy += s
            if "right" in cmds:
                vy -= s
            if "up" in cmds:
                vz += s
            if "down" in cmds:
                vz -= s

            try:
                msg = self._TwistStamped()
                msg.header.stamp = self.rospy.Time.now()
                msg.header.frame_id = "base_link"
                msg.twist.linear.x = vx
                msg.twist.linear.y = vy
                msg.twist.linear.z = vz
                msg.twist.angular.x = 0.0
                msg.twist.angular.y = 0.0
                msg.twist.angular.z = 0.0
                self._pub_cmd_vel.publish(msg)
            except Exception:
                pass
            time.sleep(period)


class NavrlPassiveBackend(BaseBackend):
    """
    NavRL 的 navigation_node 会发布 /CERLAB/quadcopter/cmd_vel 等控制量。
    此前端后端不再循环发布速度，避免与强化学习策略抢占同一话题导致撞墙/抖动。
    仍可向 takeoff/land/reset 发空消息（是否生效取决于仿真插件）。
    """

    name = "navrl_passive"

    def __init__(self, rospy, cfg):
        self.rospy = rospy
        self.cfg = cfg or {}
        c = (self.cfg.get("cerlab") or {})
        self.takeoff_topic = c.get("takeoff_topic", "/CERLAB/quadcopter/takeoff")
        self.land_topic = c.get("land_topic", "/CERLAB/quadcopter/land")
        self.reset_topic = c.get("reset_topic", "/CERLAB/quadcopter/reset")
        self.vel_mode_topic = c.get("vel_mode_topic", "/CERLAB/quadcopter/vel_mode")
        self.posctrl_topic = c.get("posctrl_topic", "/CERLAB/quadcopter/posctrl")
        from std_msgs.msg import Bool, Empty

        self._Empty = Empty
        self._pub_takeoff = rospy.Publisher(self.takeoff_topic, Empty, queue_size=10)
        self._pub_land = rospy.Publisher(self.land_topic, Empty, queue_size=10)
        self._pub_reset = rospy.Publisher(self.reset_topic, Empty, queue_size=10)
        self._pub_vel_mode = rospy.Publisher(self.vel_mode_topic, Bool, queue_size=1)
        self._pub_posctrl = rospy.Publisher(self.posctrl_topic, Bool, queue_size=1)

    def takeoff(self) -> ControlResult:
        try:
            self._pub_takeoff.publish(self._Empty())
            return ControlResult(
                True,
                "已发送 takeoff；自主机动由 NavRL 节点负责，请用航点或 /move_base_simple/goal",
            )
        except Exception as e:
            return ControlResult(False, str(e))

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        return ControlResult(
            False,
            "NavRL 模式已禁用键盘速度（避免与 RL 抢 cmd_vel）；请用航点或 RViz 2D Nav Goal",
        )

    def start_continuous(self, direction: str) -> ControlResult:
        return self.nudge(direction, 0.0)

    def stop_continuous(self, direction: str) -> ControlResult:
        return ControlResult(True, "无连续速度发布")

    def self_rescue(self) -> ControlResult:
        from std_msgs.msg import Bool

        parts: List[str] = []
        _merge_gazebo_rescue_msgs(parts, gazebo_teleport_drone_to_spawn(self.rospy, self.cfg))

        try:
            self._pub_reset.publish(self._Empty())
        except Exception as e:
            return ControlResult(False, f"复位指令异常: {e}")
        try:
            self.rospy.sleep(0.55)
        except Exception:
            time.sleep(0.55)
        try:
            self._pub_vel_mode.publish(Bool(data=False))
            self._pub_posctrl.publish(Bool(data=True))
        except Exception:
            pass
        try:
            self._pub_takeoff.publish(self._Empty())
        except Exception as e:
            return ControlResult(False, f"复位已发但起飞失败: {e}")
        try:
            self._pub_vel_mode.publish(Bool(data=True))
        except Exception:
            pass
        parts.append("已发送仿真复位并就绪起飞；后续机动仍由 NavRL 节点接管，请观察姿态")
        return ControlResult(True, "；".join([p for p in parts if p]))


class Px4CtrlBackend(BaseBackend):
    name = "px4ctrl"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        px = (self.cfg.get("px4ctrl") or {})
        self.takeoff_land_topic = px.get("takeoff_land_topic", "/px4ctrl/takeoff_land")
        self.takeoff_land_msg_type = px.get("takeoff_land_msg_type", "quadrotor_msgs/TakeoffLand")
        self.move_topic = px.get("move_topic", "")  # unknown by default
        self.move_msg_type = px.get("move_msg_type", "")

    def takeoff(self) -> ControlResult:
        # 不做“真起飞”承诺：这里只保证命令发出，仿真是否动由健康检查/telemetry 证明
        cmd = f'rostopic pub -1 {self.takeoff_land_topic} {self.takeoff_land_msg_type} "takeoff_land_cmd: 1"'
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return ControlResult(True, f"已发送 takeoff_land_cmd=1 到 {self.takeoff_land_topic}")
            return ControlResult(False, f"起飞命令失败: {r.stderr.strip()[:400]}")
        except subprocess.TimeoutExpired:
            return ControlResult(False, "起飞命令超时")
        except Exception as e:
            return ControlResult(False, f"起飞命令异常: {e}")

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        if not self.move_topic or not self.move_msg_type:
            return ControlResult(False, "未配置 px4ctrl 的 move_topic/move_msg_type，无法移动（但起飞/降落可用）")
        return ControlResult(False, "px4ctrl 移动尚未在本工程配置（请在 control_config.json 填真实话题）")

    def start_continuous(self, direction: str) -> ControlResult:
        if not self.move_topic or not self.move_msg_type:
            return ControlResult(False, "未配置 px4ctrl 的 move_topic/move_msg_type，无法连续移动")
        return ControlResult(False, "px4ctrl 连续移动未实现（请用 hybrid 后端或配置 move_topic）")

    def stop_continuous(self, direction: str) -> ControlResult:
        return ControlResult(True, "px4ctrl 无连续移动可停")

    def self_rescue(self) -> ControlResult:
        return ControlResult(
            False,
            "px4ctrl 无仿真机体姿态复位；请在 Gazebo 中重置四旋翼模型或重启仿真。",
        )


class HybridPx4MavrosBackend(BaseBackend):
    """
    Intent-MPC / px4ctrl + MAVROS 同时存在时：起飞走 px4ctrl（TakeoffLand），
    手动方向键走 MAVROS OFFBOARD 速度（与 ego/仿真常见组合一致）。
    """

    name = "hybrid_px4ctrl_mavros"

    def __init__(self, rospy, cfg: dict):
        self._px = Px4CtrlBackend(cfg)
        self._mv = MavrosOffboardBackend(rospy, cfg)
        self._cerlab_rescue_pubs = None

    def takeoff(self) -> ControlResult:
        return self._px.takeoff()

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        return self._mv.nudge(direction, duration_sec)

    def start_continuous(self, direction: str) -> ControlResult:
        return self._mv.start_continuous(direction)

    def stop_continuous(self, direction: str) -> ControlResult:
        return self._mv.stop_continuous(direction)

    def _ensure_cerlab_rescue_pubs(self):
        if self._cerlab_rescue_pubs is not None:
            return
        from std_msgs.msg import Bool, Empty

        c = (self._mv.cfg.get("cerlab") or {})
        r = self._mv.rospy
        self._cerlab_rescue_pubs = {
            "reset": r.Publisher(
                c.get("reset_topic", "/CERLAB/quadcopter/reset"), Empty, queue_size=10
            ),
            "takeoff": r.Publisher(
                c.get("takeoff_topic", "/CERLAB/quadcopter/takeoff"), Empty, queue_size=10
            ),
            "vel": r.Publisher(
                c.get("vel_mode_topic", "/CERLAB/quadcopter/vel_mode"), Bool, queue_size=1
            ),
            "pos": r.Publisher(
                c.get("posctrl_topic", "/CERLAB/quadcopter/posctrl"), Bool, queue_size=1
            ),
        }
        try:
            r.sleep(0.08)
        except Exception:
            time.sleep(0.08)

    def self_rescue(self) -> ControlResult:
        """混合链路常见场景：Gazebo 仍走 CERLAB 插件，可尝试与纯 CERLAB 相同的复位序列。"""
        from std_msgs.msg import Bool, Empty

        parts: List[str] = []
        _merge_gazebo_rescue_msgs(
            parts, gazebo_teleport_drone_to_spawn(self._mv.rospy, self._mv.cfg)
        )

        try:
            self._ensure_cerlab_rescue_pubs()
            p = self._cerlab_rescue_pubs
            p["reset"].publish(Empty())
            self._mv.rospy.sleep(0.5)
            p["vel"].publish(Bool(data=False))
            p["pos"].publish(Bool(data=True))
            p["takeoff"].publish(Empty())
            p["vel"].publish(Bool(data=True))
            parts.append("已向 CERLAB 仿真发送复位再起飞；若机体仍异常，请在 Gazebo 中重置模型。")
            return ControlResult(True, "；".join([p for p in parts if p]))
        except Exception as e:
            return ControlResult(False, f"混合模式尝试仿真复位失败: {e}")


class MavrosOffboardBackend(BaseBackend):
    name = "mavros_offboard"

    def __init__(self, rospy, cfg: dict):
        self.rospy = rospy
        self.cfg = cfg or {}
        mv = (self.cfg.get("mavros") or {})
        self.state_topic = mv.get("state_topic", "/mavros/state")
        self.setpoint_topic = mv.get("setpoint_topic", "/mavros/setpoint_raw/target_local")
        self.arming_srv = mv.get("arming_service", "/mavros/cmd/arming")
        self.set_mode_srv = mv.get("set_mode_service", "/mavros/set_mode")
        self.alt_m = float(mv.get("takeoff_altitude_m", 1.5))
        self.speed = float(mv.get("body_speed_mps", 1.0))
        self.rate_hz = float(mv.get("control_rate_hz", 20))

        self._lock = threading.Lock()
        self._continuous = set()
        self._shutdown = False

        from geometry_msgs.msg import Point, Vector3
        from mavros_msgs.msg import PositionTarget

        self._Point = Point
        self._Vector3 = Vector3
        self._PositionTarget = PositionTarget
        self._pub = rospy.Publisher(self.setpoint_topic, PositionTarget, queue_size=10)

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _make_target(self, vx: float, vy: float, vz: float):
        PositionTarget = self._PositionTarget
        m = PositionTarget()
        m.header.stamp = self.rospy.Time.now()
        m.coordinate_frame = PositionTarget.FRAME_BODY_NED
        m.type_mask = (
            PositionTarget.IGNORE_PX
            | PositionTarget.IGNORE_PY
            | PositionTarget.IGNORE_PZ
            | PositionTarget.IGNORE_AFX
            | PositionTarget.IGNORE_AFY
            | PositionTarget.IGNORE_AFZ
            | PositionTarget.IGNORE_YAW
            | PositionTarget.IGNORE_YAW_RATE
        )
        m.position = self._Point()
        m.velocity = self._Vector3(vx, vy, vz)
        m.acceleration_or_force = self._Vector3()
        m.yaw = 0.0
        m.yaw_rate = 0.0
        return m

    def _loop(self):
        period = 1.0 / max(5.0, float(self.rate_hz))
        while (not self.rospy.is_shutdown()) and (not self._shutdown):
            with self._lock:
                cmds = set(self._continuous)
            vx = vy = vz = 0.0
            s = self.speed
            # BODY_NED: x前 y右 z下
            if "forward" in cmds:
                vx += s
            if "backward" in cmds:
                vx -= s
            if "left" in cmds:
                vy -= s
            if "right" in cmds:
                vy += s
            if "up" in cmds:
                vz -= s
            if "down" in cmds:
                vz += s
            try:
                self._pub.publish(self._make_target(vx, vy, vz))
            except Exception:
                pass
            time.sleep(period)

    def _wait_state(self, timeout: float = 2.0):
        from mavros_msgs.msg import State
        return self.rospy.wait_for_message(self.state_topic, State, timeout=timeout)

    def _ensure_offboard_and_arm(self, timeout: float = 8.0) -> ControlResult:
        from mavros_msgs.srv import CommandBool, SetMode

        try:
            self.rospy.wait_for_service(self.set_mode_srv, timeout=2.0)
            self.rospy.wait_for_service(self.arming_srv, timeout=2.0)
        except Exception as e:
            return ControlResult(False, f"等待 MAVROS 服务失败: {e}")

        set_mode = self.rospy.ServiceProxy(self.set_mode_srv, SetMode)
        arming = self.rospy.ServiceProxy(self.arming_srv, CommandBool)

        # 预热 setpoint 流 2 秒，否则 PX4 常拒绝 OFFBOARD
        t_end = time.time() + 2.0
        while time.time() < t_end and not self.rospy.is_shutdown():
            self._pub.publish(self._make_target(0.0, 0.0, 0.0))
            time.sleep(1.0 / max(10.0, self.rate_hz))

        # arm
        try:
            ar = arming(True)
            if not getattr(ar, "success", False):
                return ControlResult(False, f"解锁失败: result={getattr(ar,'result',None)}")
        except Exception as e:
            return ControlResult(False, f"解锁异常: {e}")

        # offboard 必须确认 state.mode==OFFBOARD
        deadline = time.time() + float(timeout)
        last_mode = None
        while time.time() < deadline and not self.rospy.is_shutdown():
            try:
                set_mode(0, "OFFBOARD")
            except Exception:
                pass
            try:
                st = self._wait_state(timeout=0.5)
                last_mode = getattr(st, "mode", "")
                if getattr(st, "mode", "") == "OFFBOARD" and getattr(st, "armed", False):
                    return ControlResult(True, "已进入 OFFBOARD 且已解锁")
            except Exception:
                pass
            time.sleep(0.2)
        return ControlResult(False, f"OFFBOARD 未确认（last_mode={last_mode}）")

    def takeoff(self) -> ControlResult:
        # 不调用 /cmd/takeoff（无GPS常失败），直接 OFFBOARD 上升
        ok = self._ensure_offboard_and_arm()
        if not ok.ok:
            return ok
        t_end = time.time() + max(2.5, min(6.0, self.alt_m / 0.6 + 1.0))
        while time.time() < t_end and not self.rospy.is_shutdown():
            self._pub.publish(self._make_target(0.0, 0.0, -0.8))
            time.sleep(1.0 / max(10.0, self.rate_hz))
        self._pub.publish(self._make_target(0.0, 0.0, 0.0))
        return ControlResult(True, "已发送 OFFBOARD 上升设定点（请用 odom/画面验证真实运动）")

    def self_rescue(self) -> ControlResult:
        return ControlResult(
            False,
            "纯 MAVROS 未接入仿真机体 reset；翻机时请使用 QGC/仿真器侧复位，或换用 CERLAB/混合后端。",
        )

    def start_continuous(self, direction: str) -> ControlResult:
        ok = self._ensure_offboard_and_arm(timeout=4.0)
        if not ok.ok:
            return ok
        with self._lock:
            self._continuous.add(direction)
        return ControlResult(True, f"持续 {direction} 开")

    def stop_continuous(self, direction: str) -> ControlResult:
        with self._lock:
            self._continuous.discard(direction)
        return ControlResult(True, f"持续 {direction} 关")

    def nudge(self, direction: str, duration_sec: float = 0.5) -> ControlResult:
        ok = self.start_continuous(direction)
        if not ok.ok:
            return ok
        time.sleep(max(0.05, float(duration_sec)))
        self.stop_continuous(direction)
        return ControlResult(True, f"脉冲 {direction} {duration_sec:.2f}s")


def create_backend(rospy, config_path: str) -> Tuple[Optional[BaseBackend], str]:
    cfg = _load_json(config_path)
    backend = (cfg.get("backend") or "auto").strip().lower()

    def _has_topic(name: str) -> bool:
        try:
            topics = rospy.get_published_topics()
            return any(t[0] == name for t in topics)
        except Exception:
            return False

    use_hybrid = bool((cfg.get("mavros") or {}).get("use_hybrid_with_px4ctrl", True))

    if backend == "hybrid":
        if _has_topic("/px4ctrl/takeoff_land") and _has_topic("/mavros/state"):
            return HybridPx4MavrosBackend(rospy, cfg), "hybrid(explicit)"
        if _has_topic("/mavros/state"):
            return MavrosOffboardBackend(rospy, cfg), "mavros_only(hybrid requested)"
        return Px4CtrlBackend(cfg), "px4ctrl_only(hybrid requested)"

    if backend == "px4ctrl":
        return Px4CtrlBackend(cfg), "px4ctrl"
    if backend == "mavros":
        return MavrosOffboardBackend(rospy, cfg), "mavros_offboard"
    if backend == "cerlab":
        return CerlabUavSimulatorBackend(rospy, cfg), "cerlab_uav_simulator"
    if backend == "navrl_passive":
        return NavrlPassiveBackend(rospy, cfg), "navrl_passive"

    # auto
    has_px = _has_topic("/px4ctrl/takeoff_land")
    has_mv = _has_topic("/mavros/state")
    has_cerlab = _has_topic("/CERLAB/quadcopter/cmd_vel") and _has_topic("/CERLAB/quadcopter/takeoff")
    has_navrl = _has_topic("/rollout_traj") or _has_topic("/rl_navigation/raycast")
    if has_cerlab and has_navrl:
        return NavrlPassiveBackend(rospy, cfg), "navrl_passive(auto:检测到 NavRL 话题)"
    if has_cerlab:
        return CerlabUavSimulatorBackend(rospy, cfg), "cerlab_uav_simulator(auto)"
    if has_px and has_mv and use_hybrid:
        return HybridPx4MavrosBackend(rospy, cfg), "hybrid_px4ctrl+mavros(auto)"
    if has_px:
        return Px4CtrlBackend(cfg), "px4ctrl(auto)"
    if has_mv:
        return MavrosOffboardBackend(rospy, cfg), "mavros_offboard(auto)"

    return None, "no-backend"

