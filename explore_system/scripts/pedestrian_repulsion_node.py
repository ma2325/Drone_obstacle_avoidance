#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Gazebo Classic：行人防拖拽 +（可选）无人机卡死软恢复

【默认】对行人 SetModelState；对机体「侧让」默认关闭（与 CERLAB 插件抢位姿易导致穿地/陷入地面），
可在 config/pedestrian_repulsion.yaml 中开启 enable_drone_sidestep_from_pedestrian。

可选开启（ROS 参数，默认均为 false）：
  ~enable_drone_z_recovery       仅当机体明显埋地且附近有行人时小幅抬升
  ~enable_static_obstacle_nudge  仅当与静态体水平距极近（疑似已穿模）时轻推

无人机修正带 ~drone_pose_fix_min_interval_sec 冷却，且默认保留 model_states 中的 twist，
不再强行清零线速度（否则等价于每帧打断控制器）。
"""
from __future__ import print_function

import copy
import math
import time as time_mod

import rospy
from gazebo_msgs.msg import ModelState, ModelStates
from gazebo_msgs.srv import SetModelState
from geometry_msgs.msg import Twist


def _time_float():
    try:
        return rospy.Time.now().to_sec()
    except Exception:
        return time_mod.time()


class PedestrianRepulsor(object):
    def __init__(self):
        rospy.init_node("pedestrian_repulsion_myviz", anonymous=False)
        self._drone_subs = [
            s.lower()
            for s in rospy.get_param(
                "~drone_name_substrings",
                ["quadcopter", "cerlab", "iris", "uav", "drone_0"],
            )
        ]
        self._ped_subs = [
            s.lower()
            for s in rospy.get_param(
                "~pedestrian_name_substrings",
                ["person", "human", "actor", "walker", "ped", "walking"],
            )
        ]
        self._exclude = [
            s.lower()
            for s in rospy.get_param(
                "~exclude_name_substrings",
                [
                    "ground",
                    "plane",
                    "sky",
                    "sun",
                    "light",
                    "camera",
                    "wall",
                    "obstacle",
                    "pillar",
                    "column",
                    "box_",
                    "cylinder",
                    "building",
                    # demo_rich.world 里由 libobstaclePathPlugin 驱动的 demo_person_*，勿再 set_model_state
                    "demo_person",
                ],
            )
        ]
        self._static_nudge_subs = [
            s.lower()
            for s in rospy.get_param(
                "~static_obstacle_name_substrings",
                [
                    "pillar",
                    "column",
                    "cylinder",
                    "obstacle",
                    "wall",
                    "box_",
                    "pylon",
                    "post",
                    "pole",
                ],
            )
        ]
        # 更早、更强推离行人：硬接触后 Gazebo+CERLAB 常把四旋翼解算到异常位姿（原点贴地），
        # 优先在「未贴上」前把行人挪开；可用 ROS 参数按需调弱。
        self._d0 = float(rospy.get_param("~influence_distance_m", 7.5))
        self._gain = float(rospy.get_param("~repulsion_gain", 0.62))
        self._maxv = float(rospy.get_param("~max_linear_m_s", 0.68))
        self._rate_hz = float(rospy.get_param("~rate_hz", 15.0))

        self._use_pose_sep = bool(rospy.get_param("~use_pose_separation", True))
        self._em_trig_xy = float(rospy.get_param("~emergency_trigger_xy_m", 3.85))
        self._em_target_xy = float(rospy.get_param("~emergency_target_xy_m", 4.25))
        self._max_pose_step = float(rospy.get_param("~max_pose_step_m", 0.52))
        self._panic_xy = float(rospy.get_param("~panic_xy_m", 1.05))
        self._panic_step = float(rospy.get_param("~panic_pose_step_m", 0.58))
        # 水平距小于此值时强制大步径向推行人（在 pose 分离分支之前执行）
        self._pre_ring_xy = float(rospy.get_param("~pre_contact_ring_xy_m", 0.58))
        self._pre_ring_step = float(rospy.get_param("~pre_contact_ring_step_m", 0.78))

        # 默认关闭：曾对无人机高频改 pose + 清零 twist，易与控制律打架导致振荡/穿地
        self._enable_drone_z = bool(rospy.get_param("~enable_drone_z_recovery", False))
        self._min_safe_drone_z = float(rospy.get_param("~min_safe_drone_z_m", 0.32))
        self._drone_z_critical = float(
            rospy.get_param(
                "~drone_z_critical_below_m",
                0.22,
            )
        )
        self._drone_z_bump = float(rospy.get_param("~drone_z_bump_m", 0.08))
        self._drone_z_ceiling = float(rospy.get_param("~drone_z_recovery_max_z_m", 4.5))

        self._enable_static_nudge = bool(
            rospy.get_param("~enable_static_obstacle_nudge", False)
        )
        self._static_trig_xy = float(rospy.get_param("~static_nudge_trigger_xy_m", 0.22))
        self._static_step = float(rospy.get_param("~static_nudge_step_m", 0.08))

        self._drone_fix_cooldown = float(
            rospy.get_param("~drone_pose_fix_min_interval_sec", 1.5)
        )
        self._preserve_drone_twist = bool(
            rospy.get_param("~drone_fix_preserve_twist", True)
        )

        self._drone_idx = None
        self._last_wall = 0.0
        self._last_drone_fix_wall = 0.0

        # 默认关闭：对机体 SetModel_state 与 CERLAB 插件强耦合时极易穿地/陷入地面；需侧让时再在 yaml 里打开
        self._enable_sidestep = bool(
            rospy.get_param("~enable_drone_sidestep_from_pedestrian", False)
        )
        self._sidestep_trig = float(rospy.get_param("~drone_sidestep_trigger_xy_m", 0.78))
        self._sidestep_step = float(rospy.get_param("~drone_sidestep_step_m", 0.36))
        self._sidestep_z_bump = float(rospy.get_param("~drone_sidestep_z_bump_m", 0.11))
        self._sidestep_cd = float(rospy.get_param("~drone_sidestep_cooldown_sec", 1.75))
        self._last_sidestep_wall = 0.0

        rospy.loginfo("等待 Gazebo /gazebo/set_model_state …")
        try:
            rospy.wait_for_service(
                "/gazebo/set_model_state",
                timeout=float(rospy.get_param("~gazebo_wait_sec", 45.0)),
            )
        except rospy.ROSException:
            rospy.logwarn(
                "未等到 Gazebo 服务，行人防拖拽节点退出（真机或无 Gazebo 时可忽略）。"
            )
            raise SystemExit(0)

        self._set_state = rospy.ServiceProxy("/gazebo/set_model_state", SetModelState)
        rospy.Subscriber("/gazebo/model_states", ModelStates, self._on_models, queue_size=1)

        dz = "开" if self._enable_drone_z else "关（默认，防振荡）"
        st = "开" if self._enable_static_nudge else "关（默认，柱阵勿用宽阈值）"
        sd = "开" if self._enable_sidestep else "关"
        rospy.loginfo(
            "pedestrian_repulsion: 近距环<%.2fm | 紧急距<%.2fm | 机体侧让%s(<%.2fm) | 无人机Z恢复%s | 静态轻推%s",
            self._pre_ring_xy,
            self._em_trig_xy,
            sd,
            self._sidestep_trig,
            dz,
            st,
        )

    @staticmethod
    def _match(name, subs):
        n = name.lower()
        return any(s in n for s in subs)

    def _resolve_drone_index(self, names):
        if self._drone_idx is not None and self._drone_idx < len(names):
            n = names[self._drone_idx]
            if self._match(n, self._drone_subs) and not self._match(n, self._ped_subs):
                return self._drone_idx
        for i, n in enumerate(names):
            if self._match(n, self._drone_subs) and not self._match(n, self._ped_subs):
                self._drone_idx = i
                return i
        self._drone_idx = None
        return None

    def _is_static_nudge_target(self, name):
        n = name.lower()
        if self._match(n, self._ped_subs):
            return False
        if self._match(n, self._drone_subs) and not self._match(n, self._ped_subs):
            return False
        if any(x in n for x in ("ground", "plane", "sky", "sun", "light", "camera")):
            return False
        return self._match(n, self._static_nudge_subs)

    def _near_any_pedestrian_xy(self, names, poses, di, drone_pos, radius_m):
        for i, n in enumerate(names):
            if i == di:
                continue
            if not self._match(n, self._ped_subs):
                continue
            if self._match(n, self._exclude):
                continue
            pp = poses[i].position
            if math.hypot(pp.x - drone_pos.x, pp.y - drone_pos.y) <= radius_m:
                return True
        return False

    def _apply_state(self, name, pose, twist_zero=False, lin=None, twist_copy=None):
        st = ModelState()
        st.model_name = name
        st.pose = pose
        if twist_copy is not None:
            st.twist = copy.deepcopy(twist_copy)
        elif twist_zero or lin is None:
            st.twist.linear.x = 0.0
            st.twist.linear.y = 0.0
            st.twist.linear.z = 0.0
            st.twist.angular.x = 0.0
            st.twist.angular.y = 0.0
            st.twist.angular.z = 0.0
        else:
            st.twist.linear.x = lin[0]
            st.twist.linear.y = lin[1]
            st.twist.linear.z = 0.0
            st.twist.angular.x = 0.0
            st.twist.angular.y = 0.0
            st.twist.angular.z = 0.0
        st.reference_frame = "world"
        try:
            resp = self._set_state(model_state=st)
            if not resp.success:
                rospy.logwarn_throttle(
                    8.0, "set_model_state %s: %s", name, resp.status_message
                )
        except Exception as ex:
            rospy.logwarn_throttle(8.0, "set_model_state %s: %s", name, ex)

    def _maybe_sidestep_drone_from_pedestrian(self, names, poses, twists, di, now):
        """行人水平距过近时，把机体沿远离行人方向挪一点并微抬升，降低硬穿模概率。"""
        if not self._enable_sidestep or di is None or di >= len(names):
            return
        if now - self._last_sidestep_wall < self._sidestep_cd:
            return
        dp = poses[di].position
        best_d = 1e9
        best_pp = None
        for i, n in enumerate(names):
            if i == di:
                continue
            if self._match(n, self._exclude):
                continue
            if not self._match(n, self._ped_subs):
                continue
            pp = poses[i].position
            dxy = math.hypot(pp.x - dp.x, pp.y - dp.y)
            if dxy < best_d:
                best_d = dxy
                best_pp = pp
        if best_pp is None or best_d >= self._sidestep_trig:
            return
        vx = dp.x - best_pp.x
        vy = dp.y - best_pp.y
        norm = math.hypot(vx, vy)
        if norm < 0.05:
            return
        vx /= norm
        vy /= norm
        new_pose = copy.deepcopy(poses[di])
        new_pose.position.x = dp.x + vx * self._sidestep_step
        new_pose.position.y = dp.y + vy * self._sidestep_step
        new_pose.position.z = dp.z + min(0.22, max(0.0, float(self._sidestep_z_bump)))
        drone_name = names[di]
        tw = None
        if twists is not None and di < len(twists):
            tw = twists[di]
        # 无 twist 时仍侧让（短时清零速度），避免该分支永远不触发导致硬接触
        self._apply_state(
            drone_name,
            new_pose,
            twist_zero=(tw is None),
            twist_copy=tw,
        )
        self._last_sidestep_wall = now
        rospy.loginfo_throttle(
            5.0,
            "pedestrian_repulsion: 行人距 %.2fm，已对机体侧让 (step=%.2fm z+%.2fm)",
            best_d,
            self._sidestep_step,
            float(self._sidestep_z_bump),
        )

    def _recover_drone(self, names, poses, twists, di):
        if not self._enable_drone_z and not self._enable_static_nudge:
            return

        now = _time_float()
        if now - self._last_drone_fix_wall < self._drone_fix_cooldown:
            return

        if di is None or di >= len(names):
            return
        drone_name = names[di]
        pose = poses[di]
        p = pose.position
        new_pose = copy.deepcopy(pose)
        changed = False

        ped_radius = float(rospy.get_param("~drone_z_recovery_ped_proximity_xy_m", 1.4))
        require_ped = bool(rospy.get_param("~drone_z_recovery_require_near_ped", True))

        z_crit = p.z < self._drone_z_critical
        ped_ok = (not require_ped) or self._near_any_pedestrian_xy(
            names, poses, di, p, ped_radius
        )
        if self._enable_drone_z and z_crit and ped_ok:
            nz = max(
                p.z + self._drone_z_bump,
                self._min_safe_drone_z + 0.04,
            )
            nz = min(nz, self._drone_z_ceiling)
            new_pose.position.z = nz
            changed = True

        if self._enable_static_nudge:
            best_d = 1e9
            best_ox, best_oy = None, None
            for i, n in enumerate(names):
                if i == di:
                    continue
                if not self._is_static_nudge_target(n):
                    continue
                op = poses[i].position
                dxy = math.hypot(op.x - p.x, op.y - p.y)
                if dxy < best_d:
                    best_d = dxy
                    best_ox, best_oy = op.x, op.y
            if (
                best_ox is not None
                and best_d < self._static_trig_xy
                and best_d > 0.02
            ):
                dx = p.x - best_ox
                dy = p.y - best_oy
                dxy = math.hypot(dx, dy) + 1e-9
                step = min(self._static_step, max(0.03, best_d * 0.45))
                new_pose.position.x = new_pose.position.x + (dx / dxy) * step
                new_pose.position.y = new_pose.position.y + (dy / dxy) * step
                changed = True

        if changed:
            tw = None
            if twists is not None and di < len(twists):
                tw = twists[di]
            # 保留 twist 为真却无 twist 数据时勿 set 无人机，否则 _apply_state 会因 lin=None 走「清零 twist」分支
            if self._preserve_drone_twist and tw is None:
                return
            self._apply_state(
                drone_name,
                new_pose,
                twist_zero=(tw is None),
                twist_copy=tw,
            )
            self._last_drone_fix_wall = now

    def _on_models(self, msg):
        now = _time_float()
        dt = 1.0 / max(1.0, self._rate_hz)
        if now - self._last_wall < dt:
            return
        self._last_wall = now

        names = msg.name
        poses = msg.pose
        twists = msg.twist
        if not names or len(names) != len(poses):
            return
        if twists is None or len(twists) != len(poses):
            twists = None

        di = self._resolve_drone_index(names)
        if di is None:
            return

        dp = poses[di].position
        for i, n in enumerate(names):
            if i == di:
                continue
            if self._match(n, self._exclude):
                continue
            if not self._match(n, self._ped_subs):
                continue

            p = poses[i]
            pp = p.position
            dx = pp.x - dp.x
            dy = pp.y - dp.y
            d_xy = math.hypot(dx, dy) + 1e-9

            if d_xy >= self._d0:
                continue

            # 极近环：先于一般紧急分离，避免行人骨架已嵌入螺旋桨碰撞体再被求解器「弹飞」无人机
            if self._use_pose_sep and d_xy < self._pre_ring_xy:
                ux, uy = dx / d_xy, dy / d_xy
                new_pose = copy.deepcopy(p)
                stp = min(
                    1.08,
                    max(
                        self._pre_ring_step,
                        self._em_target_xy - d_xy + 0.22,
                    ),
                )
                new_pose.position.x = pp.x + ux * stp
                new_pose.position.y = pp.y + uy * stp
                new_pose.position.z = pp.z
                self._apply_state(n, new_pose, twist_zero=True)
                continue

            if self._use_pose_sep and d_xy < self._em_trig_xy:
                need = self._em_target_xy - d_xy
                if need <= 0.0:
                    self._apply_state(n, p, twist_zero=True)
                    continue
                if d_xy < self._panic_xy:
                    step = min(self._panic_step, need + 0.25)
                else:
                    step = min(self._max_pose_step, max(need * 0.92, 0.22))

                ux, uy = dx / d_xy, dy / d_xy
                new_pose = copy.deepcopy(p)
                new_pose.position.x = pp.x + ux * step
                new_pose.position.y = pp.y + uy * step
                new_pose.position.z = pp.z
                self._apply_state(n, new_pose, twist_zero=True)
                continue

            if d_xy >= self._d0:
                continue
            w = (1.0 / d_xy - 1.0 / self._d0)
            if w <= 0.0:
                continue
            mag = min(self._maxv, self._gain * w * d_xy)
            vx = (dx / d_xy) * mag
            vy = (dy / d_xy) * mag
            self._apply_state(n, p, twist_zero=False, lin=(vx, vy))

        self._maybe_sidestep_drone_from_pedestrian(names, poses, twists, di, now)
        self._recover_drone(names, poses, twists, di)


if __name__ == "__main__":
    try:
        PedestrianRepulsor()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
