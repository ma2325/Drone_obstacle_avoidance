#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数和全局常量模块

提供路径工具函数、全局样式和进程模式常量
"""

import os
import sys
import json
import math

# =============================================================================
# 路径工具函数
# =============================================================================

def get_application_directory():
    """
    获取应用程序目录，兼容打包和非打包环境
    在打包环境下，返回可执行文件所在目录
    在开发环境下，返回脚本文件所在目录
    """
    if getattr(sys, 'frozen', False):
        # 打包环境：使用可执行文件所在目录
        application_path = os.path.dirname(sys.executable)
    else:
        # 开发环境：使用脚本文件所在目录
        application_path = os.path.dirname(os.path.abspath(__file__))

    return application_path

def get_data_directory(subdir_name):
    """
    获取数据目录（截图、日志等），确保在用户可写的位置
    优先使用程序目录，如果不可写则使用用户主目录
    """
    app_dir = get_application_directory()
    data_dir = os.path.join(app_dir, subdir_name)

    # 检查程序目录是否可写
    try:
        # 尝试在程序目录创建测试文件
        test_file = os.path.join(app_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)

        # 如果可写，使用程序目录
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        return data_dir

    except (OSError, PermissionError):
        # 如果程序目录不可写，使用用户主目录
        user_data_dir = os.path.expanduser(f"~/drone_search_system/{subdir_name}")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        print(f"程序目录不可写，使用用户目录: {user_data_dir}")
        return user_data_dir

def get_config_file_path(filename):
    """
    获取配置文件路径，优先使用程序目录，如果不存在则使用用户目录
    """
    app_dir = get_application_directory()
    config_path = os.path.join(app_dir, filename)

    if os.path.exists(config_path):
        return config_path

    # 如果程序目录没有配置文件，检查用户目录
    user_config_path = os.path.expanduser(f"~/drone_search_system/{filename}")
    if os.path.exists(user_config_path):
        return user_config_path

    # 如果都不存在，返回程序目录路径（用于创建新文件）
    return config_path


# =============================================================================
# 导航 hold goal：里程计 glitch 防护（Gazebo 碰撞/行人接触后 odom 偶发拉到原点等）
# =============================================================================


def hold_goal_odom_glitch_should_skip(
    pos,
    prev_xyz,
    max_xy_jump_m=9.0,
    max_z_jump_m=3.0,
    origin_snap_xy=0.12,
    min_prev_xy_norm_for_origin_snap=3.0,
    z_plunge_prev_min=0.55,
    z_plunge_new_max=0.18,
    z_plunge_min_drop_m=0.95,
    z_plunge_min_prev_xy_norm_m=1.25,
):
    """
    判断是否应跳过「把导航 goal 刷成当前里程计位」。

    prev_xyz: 上一次**已成功发布** hold goal 时的 (x,y,z)；首次为 None 时不跳过。
    返回 (skip: bool, reason: str|None)。reason 便于日志说明。
    """
    try:
        x = float(pos.get("x", 0.0))
        y = float(pos.get("y", 0.0))
        z = float(pos.get("z", 0.0))
    except (TypeError, ValueError):
        return True, "invalid_odom_position"

    if prev_xyz is None or len(prev_xyz) < 3:
        return False, None

    px, py, pz = float(prev_xyz[0]), float(prev_xyz[1]), float(prev_xyz[2])
    dxy = math.hypot(x - px, y - py)
    if dxy > float(max_xy_jump_m):
        return True, "xy_jump_%.1fm_gt_%.1f" % (dxy, float(max_xy_jump_m))

    dz = abs(z - pz)
    if dz > float(max_z_jump_m):
        return True, "z_jump_%.2fm_gt_%.1f" % (dz, float(max_z_jump_m))

    drop = pz - z
    # 介于「贴地」与 z_plunge 阈值之间：例如 0.92→0.25（dz 可能仍小于 max_z_jump_m）
    if (
        pz > 0.52
        and z < 0.38
        and drop > 0.48
        and dxy <= float(max_xy_jump_m)
    ):
        return True, "z_soft_plunge"
    # 里程计单帧「坠地」脏读：曾用 prev_xy 离原点足够远才启用 z_plunge，导致 spawn 在 (0,0) 时
    # 该检测被完全短路；同时 dz 常小于 max_z_jump_m(3)，误把 z≈0 刷成 NavRL goal → 机体被压穿地面。
    if (
        pz > float(z_plunge_prev_min)
        and z < float(z_plunge_new_max)
        and drop >= float(z_plunge_min_drop_m)
        and dxy <= float(max_xy_jump_m)
    ):
        return True, "z_plunge_glitch"

    # 上一帧在场地内、本帧突然贴近 map 原点：常见于插件/状态重置后的脏读
    if (
        abs(x) < float(origin_snap_xy)
        and abs(y) < float(origin_snap_xy)
        and math.hypot(px, py) > float(min_prev_xy_norm_for_origin_snap)
    ):
        return True, "origin_snap_xy"

    return False, None


# =============================================================================
# uav_simulator 机体网格（RViz Marker：无 rospack 时仍可用 file:// 加载）
# =============================================================================


def _quad_mesh_in_package_root(pkg_root, preferred_names):
    """在 uav_simulator 包根目录下查找四旋翼 Collada 网格，返回绝对路径或空串。"""
    if not pkg_root or not os.path.isdir(pkg_root):
        return ""
    meshes = os.path.join(pkg_root, "urdf", "quadcopter", "meshes")
    if os.path.isdir(meshes):
        for n in preferred_names:
            p = os.path.join(meshes, n)
            if os.path.isfile(p):
                return p
    try:
        for root, _dirs, files in os.walk(pkg_root):
            if os.path.basename(root) != "meshes":
                continue
            for n in preferred_names:
                p = os.path.join(root, n)
                if os.path.isfile(p):
                    return p
            for f in files:
                if f.lower().endswith(".dae"):
                    return os.path.join(root, f)
    except OSError:
        pass
    return ""


def find_uav_quadcopter_mesh_dae(catkin_workspace_hint=None):
    """
    查找 CERLAB_quadcopter.dae / quadcopter.dae 的绝对路径。
    供 RViz mesh_resource 使用 file:// URI，避免 package:// 未加入 ROS_PACKAGE_PATH 时一直退回球体。
    """
    preferred = ("CERLAB_quadcopter.dae", "quadcopter.dae")
    ws_list = []

    h = (catkin_workspace_hint or "").strip()
    if h:
        ws_list.append(os.path.expanduser(h))

    try:
        cfg_path = get_config_file_path("processes_config.json")
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cw = (cfg.get("catkin_workspace") or "").strip()
            if cw:
                ws_list.append(os.path.expanduser(cw))
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        pass

    env_ws = (os.environ.get("CATKIN_WS") or "").strip()
    if env_ws:
        ws_list.append(os.path.expanduser(env_ws))

    app_dir = get_application_directory()
    for rel in (
        os.path.join("..", "catkin_ws"),
        os.path.join("..", "catkin_ws_dyn"),
        os.path.join("..", "..", "catkin_ws"),
        os.path.join("..", "..", "catkin_ws_dyn"),
        os.path.join("..", "NavRL", "catkin_ws"),
    ):
        ws_list.append(os.path.normpath(os.path.join(app_dir, rel)))

    for u in ("~/catkin_ws_dyn", "~/catkin_ws", "~/GUET_UAV_Drone_v2"):
        ws_list.append(os.path.expanduser(u))

    seen = set()
    for ws in ws_list:
        ws = os.path.normpath((ws or "").strip())
        if not ws or not os.path.isdir(ws) or ws in seen:
            continue
        seen.add(ws)
        pkg = os.path.join(ws, "src", "uav_simulator")
        hit = _quad_mesh_in_package_root(pkg, preferred)
        if hit:
            return hit

    rpp = os.environ.get("ROS_PACKAGE_PATH", "")
    for part in rpp.split(os.pathsep):
        part = (part or "").strip()
        if not part:
            continue
        candidates = []
        if os.path.basename(part.rstrip(os.sep)) == "uav_simulator":
            candidates.append(part)
        else:
            candidates.append(os.path.join(part, "uav_simulator"))
        for pkg in candidates:
            hit = _quad_mesh_in_package_root(pkg, preferred)
            if hit:
                return hit

    return ""


# =============================================================================
# 进程配置加载
# =============================================================================

def load_processes_config():
    """
    从 JSON 配置文件加载进程配置
    返回配置字典，包含 catkin_workspace, log_directory, processes 列表
    """
    config_path = get_config_file_path("processes_config.json")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 按 order 排序进程列表
        if 'processes' in config:
            config['processes'] = sorted(config['processes'], key=lambda x: x.get('order', 999))
        
        print(f"已加载进程配置: {config_path}")
        return config
    except FileNotFoundError:
        print(f"警告: 进程配置文件不存在: {config_path}")
        return get_default_processes_config()
    except json.JSONDecodeError as e:
        print(f"警告: 进程配置文件解析错误: {e}")
        return get_default_processes_config()

def get_default_processes_config():
    """返回默认的进程配置（当配置文件不存在时使用）"""
    return {
        "catkin_workspace": "~/catkin_ws_dyn",
        "save_log": True,
        "log_directory": "log",
        "processes": [
            {
                "name": "px4ctrl",
                "display_name": "PX4 飞控控制器",
                "start_command": "roslaunch px4ctrl run_node.launch",
                "stop_pattern": "roslaunch px4ctrl run_node.launch",
                "wait_seconds": 5,
                "order": 1
            },
            {
                "name": "rqt_reconfigure",
                "display_name": "ROS 参数配置工具",
                "start_command": "rosrun rqt_reconfigure rqt_reconfigure",
                "stop_pattern": "rqt_reconfigure",
                "wait_seconds": 5,
                "order": 2
            },
            {
                "name": "dynamic_predictor",
                "display_name": "动态障碍物预测器",
                "start_command": "roslaunch dynamic_predictor predictor_with_fake_detector.launch",
                "stop_pattern": "roslaunch dynamic_predictor predictor_with_fake_detector.launch",
                "wait_seconds": 10,
                "order": 3
            },
            {
                "name": "ego_planner",
                "display_name": "EGO 路径规划器",
                "start_command": "roslaunch ego_planner single_run_in_gazebo.launch",
                "stop_pattern": "roslaunch ego_planner single_run_in_gazebo.launch",
                "wait_seconds": 2,
                "order": 4
            }
        ]
    }

def get_process_stop_patterns():
    """获取用于停止进程的模式列表（兼容旧代码）"""
    config = load_processes_config()
    return [p.get('stop_pattern', p.get('start_command', '')) for p in config.get('processes', [])]

# =============================================================================
# 全局常量
# =============================================================================

# 进程模式 - 用于停止无人机系统（兼容旧代码，建议使用 get_process_stop_patterns()）
PROCESS_PATTERNS = get_process_stop_patterns()


# 全局样式常量
GLOBAL_STYLES = {
    'main_window': """
        QWidget {
            background-color: #1E2330;
            color: #FFFFFF;
        }
        QMainWindow::title {
            height: 35px;
        }
        QToolBar {
            background-color: #1A202C;
            border: none;
            spacing: 10px;
            padding: 5px;
        }
        QStatusBar {
            background-color: #1A202C;
            color: #FFFFFF;
        }
    """,
    'button_primary': """
        QPushButton {{
            background-color: #2C3E50;
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            min-width: {min_width}px;
            min-height: {min_height}px;
        }}
        QPushButton:hover {{
            background-color: #3498DB;
        }}
        QPushButton:pressed {{
            background-color: #2980B9;
        }}
    """,
    'groupbox': """
        QGroupBox {
            color: #3498DB;
            font-weight: bold;
            border: 1px solid #3498DB;
            border-radius: 5px;
            padding: 10px;
            margin-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 5px;
        }
    """,
    'label': """
        QLabel {
            font-size: 12pt;
            font-weight: bold;
            padding: 5px;
        }
    """
}


# =============================================================================
# Qt / 字体（避免中文“乱码/方块”）
# =============================================================================

def apply_best_qt_font(point_size: int = 10) -> str:
    """
    为 Qt 应用选择一个“当前系统真实存在”的中文字体并设为全局默认。

    返回最终使用的字体 family（若 Qt 不可用或失败，返回空字符串）。
    """
    try:
        # python_qt_binding (ROS) 优先；否则回退 PyQt5
        try:
            from python_qt_binding.QtWidgets import QApplication
            from python_qt_binding.QtGui import QFont, QFontDatabase
        except Exception:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtGui import QFont, QFontDatabase

        app = QApplication.instance()
        if app is None:
            return ""

        # 候选字体：覆盖 Ubuntu/WSL 常见包名
        candidates = [
            "Noto Sans CJK SC",
            "Noto Sans CJK JP",
            "Noto Sans CJK TC",
            "Noto Sans CJK KR",
            "Source Han Sans SC",
            "Source Han Sans CN",
            "WenQuanYi Micro Hei",
            "WenQuanYi Zen Hei",
            "Microsoft YaHei",
            "SimHei",
            "PingFang SC",
        ]

        families = set(QFontDatabase().families())
        chosen = ""
        for name in candidates:
            if name in families:
                chosen = name
                break

        # 即使没命中候选，也不要强行指定一个不存在的 family
        if chosen:
            app.setFont(QFont(chosen, int(point_size)))
            return chosen

        # 仍然设置一下点大小（保持 UI 一致），family 用系统默认
        f = app.font()
        f.setPointSize(int(point_size))
        app.setFont(f)
        return f.family() or ""
    except Exception:
        return ""
