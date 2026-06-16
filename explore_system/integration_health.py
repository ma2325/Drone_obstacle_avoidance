#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class HealthSummary:
    ok: bool
    short: str
    details: List[str]


def _read_tail(path: str, max_lines: int = 200) -> List[str]:
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.read().splitlines()
        return lines[-max_lines:]
    except Exception:
        return []


def find_latest_gazebo_server_log() -> Optional[str]:
    """
    Gazebo classic server log is typically under ~/.gazebo/server-*/default.log
    """
    home = os.path.expanduser("~")
    candidates = glob.glob(os.path.join(home, ".gazebo", "server-*", "default.log"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def parse_gazebo_missing_plugins(log_path: str, max_lines: int = 250) -> List[str]:
    lines = _read_tail(log_path, max_lines=max_lines)
    misses = []
    for ln in lines:
        if "Failed to load plugin" in ln and "cannot open shared object file" in ln:
            misses.append(ln.strip())
    return misses


def summarize_gazebo_plugins() -> HealthSummary:
    log_path = find_latest_gazebo_server_log()
    if not log_path:
        return HealthSummary(
            ok=False,
            short="未找到 Gazebo server 日志（~/.gazebo/server-*/default.log）",
            details=[],
        )
    misses = parse_gazebo_missing_plugins(log_path)
    if not misses:
        return HealthSummary(ok=True, short="Gazebo 插件加载未发现缺失", details=[f"log={log_path}"])
    # 只展示前几条，避免刷屏
    details = [f"log={log_path}"] + misses[:12]
    if len(misses) > 12:
        details.append(f"... 共 {len(misses)} 条缺失（仅展示前 12 条）")
    return HealthSummary(ok=False, short="Gazebo 关键插件缺失（会导致 PX4/MAVROS 无 telemetry）", details=details)


def summarize_ros_topics(rospy) -> HealthSummary:
    """
    仅做非常轻量的运行时检查：是否能连上 ROS master、是否能看到关键话题。
    """
    try:
        topics = rospy.get_published_topics()
    except Exception as e:
        return HealthSummary(ok=False, short="无法连接 ROS master", details=[str(e)])

    names = set(t[0] for t in topics)
    must = ["/clock", "/camera/color/image_raw", "/camera/depth/image_raw"]
    missing = [t for t in must if t not in names]
    if missing:
        # CERLAB + uav_simulator 常见组合：无 PX4 时钟/深度仍可能正常飞
        if "/CERLAB/quadcopter/odom" in names and "/camera/color/image_raw" in names:
            return HealthSummary(
                ok=True,
                short="ROS：CERLAB 仿真链路可用（未齐套 PX4 深度/clock 检查项）",
                details=[f"未检测到: {missing}", "已检测到 /CERLAB/quadcopter/odom 与彩色相机"],
            )
        return HealthSummary(ok=False, short="关键话题缺失（仿真可能未正常启动）", details=missing)
    return HealthSummary(ok=True, short="ROS 关键话题存在", details=[])


def summarize_mavros(rospy) -> HealthSummary:
    """
    不做“假成功”：要求 /mavros/state 能读到且 connected=True
    """
    try:
        from mavros_msgs.msg import State
    except Exception as e:
        return HealthSummary(ok=False, short="缺少 mavros_msgs（无法检查 MAVROS）", details=[str(e)])

    try:
        names = set(t[0] for t in rospy.get_published_topics())
    except Exception:
        names = set()
    if "/mavros/state" not in names:
        return HealthSummary(
            ok=False,
            short="未检测到 /mavros/state（纯 CERLAB 仿真时可忽略）",
            details=["无 MAVROS 时此项失败属正常"],
        )

    # 勿用长 timeout：健康检查在 Qt 主线程定时器里调用，会整窗卡顿
    try:
        st = rospy.wait_for_message("/mavros/state", State, timeout=0.2)
    except Exception as e:
        return HealthSummary(ok=False, short="未收到 /mavros/state（MAVROS 未运行或无数据）", details=[str(e)])

    if not getattr(st, "connected", False):
        return HealthSummary(ok=False, short="MAVROS connected=false（PX4↔仿真链路未建立）", details=[f"mode={getattr(st,'mode','')}", f"armed={getattr(st,'armed',False)}"])

    return HealthSummary(ok=True, short="MAVROS connected=true", details=[f"mode={getattr(st,'mode','')}", f"armed={getattr(st,'armed',False)}"])


def build_overall_summary(rospy) -> HealthSummary:
    parts: List[HealthSummary] = []
    parts.append(summarize_gazebo_plugins())
    parts.append(summarize_ros_topics(rospy))
    parts.append(summarize_mavros(rospy))

    ok = all(p.ok for p in parts)
    short = "系统健康" if ok else "系统未健康（请先修复缺失项）"
    details: List[str] = []
    for p in parts:
        prefix = "OK" if p.ok else "FAIL"
        details.append(f"[{prefix}] {p.short}")
        details.extend([f"  - {d}" for d in p.details])
    return HealthSummary(ok=ok, short=short, details=details)

