#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 标准库导入
import sys
import time
import os
import json
import math
import subprocess
import threading
import html
import copy
from collections import defaultdict

# ROS相关导入
import roslib; roslib.load_manifest('rviz_python_tutorial')
import rospy
from geometry_msgs.msg import PoseStamped

# 第三方库导入
import numpy as np
import cv2

# 进程管理库
try:
    import psutil
except ImportError:
    print("警告: 未能导入psutil库，进程管理功能将受限")
    try:
        subprocess.call([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil
        print("已成功安装psutil库")
    except:
        print("自动安装psutil失败，请手动安装: pip install psutil")

# 自定义模块导入
try:
    from topics_subscriber import TopicsSubscriber
except ImportError:
    print("无法导入topics_subscriber模块")
    TopicsSubscriber = None

try:
    from dashboard import UIButton, SlidingControlCenter
except ImportError:
    print("无法导入dashboard模块")
    UIButton = None
    SlidingControlCenter = None

try:
    from topic_logger import TopicLogger
except ImportError:
    print("无法导入topic_logger模块")
    TopicLogger = None

try:
    from waypoint_dialog import WaypointDialog
except ImportError:
    print("无法导入waypoint_dialog模块")
    WaypointDialog = None

try:
    from manual_controller import get_manual_controller, initialize_manual_controller
except ImportError:
    print("无法导入manual_controller模块")
    get_manual_controller = None
    initialize_manual_controller = None

try:
    from integration_health import build_overall_summary
except ImportError:
    build_overall_summary = None

try:
    from control_backends import create_backend
except ImportError:
    create_backend = None
try:
    from control_backends import gazebo_teleport_drone_to_spawn
except ImportError:
    gazebo_teleport_drone_to_spawn = None

# Qt相关导入
from python_qt_binding.QtGui import *
from python_qt_binding.QtCore import *
try:
    from python_qt_binding.QtWidgets import *
except ImportError:
    pass

# 尝试导入QTextCodec，如果失败则忽略
try:
    from python_qt_binding.QtCore import QTextCodec
except ImportError:
    QTextCodec = None
    print("警告: QTextCodec不可用，跳过编码设置")

from python_qt_binding.QtCore import QTimer, QPropertyAnimation, QEasingCurve
try:
    from python_qt_binding.QtCore import pyqtSignal
except ImportError:
    try:
        from PyQt5.QtCore import pyqtSignal
    except ImportError:
        try:
            from PyQt4.QtCore import pyqtSignal
        except ImportError:
            print("警告: 无法导入pyqtSignal，某些功能可能不可用")
            pyqtSignal = None

# 资源文件导入
try:
    import images_rc
except ImportError:
    print("警告: 无法导入images_rc资源文件，请确保已使用pyrcc5编译资源文件")

# RViz导入
from rviz import bindings as rviz

# 导入工具函数和常量
from utils import (
    get_application_directory, 
    get_data_directory, 
    get_config_file_path,
    load_processes_config,
    PROCESS_PATTERNS,
    GLOBAL_STYLES,
    apply_best_qt_font,
    hold_goal_odom_glitch_should_skip,
)

try:
    from ui_notify import notify, notify_error, confirm
except ImportError:
    def notify(anchor, title, body, level="info", duration_ms=None):
        QMessageBox.information(anchor, title or "提示", body)

    def notify_error(anchor, title, body):
        QMessageBox.critical(anchor, title, body)

    def confirm(anchor, action_id, title, text, default_no=True):
        d = QMessageBox.No if default_no else QMessageBox.Yes
        return QMessageBox.question(
            anchor, title, text, QMessageBox.Yes | QMessageBox.No, d
        ) == QMessageBox.Yes


def _processes_need_uav_simulator(config):
    """进程列表里是否包含 uav_simulator 的 roslaunch（需选对 Catkin 工作空间）。"""
    for p in (config or {}).get("processes", []):
        if "uav_simulator" in (p.get("start_command") or ""):
            return True
    return False


def _find_uav_simulator_mesh_dir(catkin_ws):
    """
    解析 uav_simulator 机体网格目录，供 mesh_prefix 与 GAZEBO_RESOURCE_PATH。
    优先 urdf/quadcopter/meshes；否则在包内查找含网格文件的 meshes/ 目录。
    """
    pkg = os.path.join(catkin_ws, "src", "uav_simulator")
    if not os.path.isdir(pkg):
        return ""
    primary = os.path.join(pkg, "urdf", "quadcopter", "meshes")
    if os.path.isdir(primary):
        return os.path.normpath(primary)
    try:
        for root, _dirs, files in os.walk(pkg):
            if os.path.basename(root) != "meshes":
                continue
            for f in files:
                low = f.lower()
                if low.endswith((".dae", ".stl", ".obj", ".mtl")):
                    return os.path.normpath(root)
    except OSError:
        pass
    return ""


class MyViz(QMainWindow):
    """无人机自主导航系统主窗口类"""

    # 定义信号，用于线程安全的UI更新（如果pyqtSignal可用）
    if pyqtSignal is not None:
        # 图像更新信号
        image_update_signal = pyqtSignal()

        # 数据更新信号 - 传递数据字典
        battery_update_signal = pyqtSignal(dict)
        position_update_signal = pyqtSignal(dict)
        velocity_update_signal = pyqtSignal(dict)
        status_update_signal = pyqtSignal(dict)
        rc_update_signal = pyqtSignal(dict)
        camera_update_signal = pyqtSignal(dict)
        depth_update_signal = pyqtSignal(dict)
        attitude_update_signal = pyqtSignal(dict)
        obstacle_update_signal = pyqtSignal(dict)

    def __init__(self):
        super(MyViz, self).__init__()

        # 初始化基本属性
        self._init_basic_attributes()

        # 初始化UI
        self._init_ui()

        # 初始化RViz
        self._init_rviz()

        # 创建布局
        self._create_layouts()

        # 初始化定时器（合并多个定时器）
        self._init_timers()

        # 连接信号到槽函数（如果信号可用）
        if pyqtSignal is not None and hasattr(self, 'image_update_signal'):
            # 图像更新信号
            self.image_update_signal.connect(self.updateImageDisplay)

            # 数据更新信号
            self.battery_update_signal.connect(self.updateBatteryStatus)
            self.position_update_signal.connect(self.updatePositionDisplay)
            self.velocity_update_signal.connect(self.updateVelocityDisplay)
            self.status_update_signal.connect(self.updateStatusDisplay)
            self.rc_update_signal.connect(self.updateRCDisplay)
            self.camera_update_signal.connect(self.updateCameraImage)
            self.depth_update_signal.connect(self.updateDepthImage)
            self.depth_update_signal.connect(self._throttled_obstacle_warn_from_depth)
            self.attitude_update_signal.connect(self.updateAttitudeDisplay)
            self.obstacle_update_signal.connect(self.updateObstacleAvoidanceWarning)

        # 延迟初始化话题订阅器
        QTimer.singleShot(2000, self.setupTopicSubscriber)

        # 延迟初始化手动控制器
        QTimer.singleShot(3000, self.setupManualController)

    # 线程安全的回调函数 - 通过信号发送数据而不直接操作GUI
    def _thread_safe_battery_callback(self, battery_data):
        """线程安全的电池状态回调"""
        if pyqtSignal is not None and hasattr(self, 'battery_update_signal'):
            self.battery_update_signal.emit(battery_data)
        else:
            # 如果信号不可用，使用QTimer在主线程中执行
            QTimer.singleShot(0, lambda: self.updateBatteryStatus(battery_data))

    def _thread_safe_position_callback(self, position_data):
        """线程安全的位置回调"""
        if pyqtSignal is not None and hasattr(self, 'position_update_signal'):
            self.position_update_signal.emit(position_data)
        else:
            QTimer.singleShot(0, lambda: self.updatePositionDisplay(position_data))

    def _thread_safe_velocity_callback(self, velocity_data):
        """线程安全的速度回调"""
        if pyqtSignal is not None and hasattr(self, 'velocity_update_signal'):
            self.velocity_update_signal.emit(velocity_data)
        else:
            QTimer.singleShot(0, lambda: self.updateVelocityDisplay(velocity_data))

    def _thread_safe_status_callback(self, status_data):
        """线程安全的状态回调"""
        if pyqtSignal is not None and hasattr(self, 'status_update_signal'):
            self.status_update_signal.emit(status_data)
        else:
            QTimer.singleShot(0, lambda: self.updateStatusDisplay(status_data))

    def _thread_safe_rc_callback(self, rc_data):
        """线程安全的遥控器回调"""
        if pyqtSignal is not None and hasattr(self, 'rc_update_signal'):
            self.rc_update_signal.emit(rc_data)
        else:
            QTimer.singleShot(0, lambda: self.updateRCDisplay(rc_data))

    def _thread_safe_camera_callback(self, camera_data):
        """线程安全的摄像头回调"""
        if pyqtSignal is not None and hasattr(self, 'camera_update_signal'):
            self.camera_update_signal.emit(camera_data)
        else:
            QTimer.singleShot(0, lambda: self.updateCameraImage(camera_data))

    def _thread_safe_depth_callback(self, depth_data):
        """线程安全的深度图像回调"""
        if pyqtSignal is not None and hasattr(self, 'depth_update_signal'):
            self.depth_update_signal.emit(depth_data)
        else:
            QTimer.singleShot(0, lambda: self.updateDepthImage(depth_data))
            QTimer.singleShot(0, lambda d=depth_data: self._throttled_obstacle_warn_from_depth(d))

    def _throttled_obstacle_warn_from_depth(self, _depth_data=None):
        """深度帧驱动避障摘要刷新（节流），补 GT 检测不到行人等情况。"""
        try:
            now = time.monotonic()
            if now - self._last_obstacle_warn_wall < 0.42:
                return
            self._last_obstacle_warn_wall = now
            self.updateObstacleAvoidanceWarning()
        except Exception:
            pass

    def _thread_safe_attitude_callback(self, attitude_data):
        """线程安全的姿态回调"""
        if pyqtSignal is not None and hasattr(self, 'attitude_update_signal'):
            self.attitude_update_signal.emit(attitude_data)
        else:
            QTimer.singleShot(0, lambda: self.updateAttitudeDisplay(attitude_data))
    
    def _thread_safe_obstacle_callback(self, obstacle_data):
        """线程安全的障碍物状态回调"""
        if pyqtSignal is not None and hasattr(self, 'obstacle_update_signal'):
            self.obstacle_update_signal.emit(obstacle_data)
        else:
            QTimer.singleShot(0, lambda d=obstacle_data: self.updateObstacleAvoidanceWarning(d))


    def _init_basic_attributes(self):
        """初始化基本属性"""
        # 获取屏幕信息
        self.desktop = QDesktopWidget()
        self.screen_geometry = self.desktop.availableGeometry(self.desktop.primaryScreen())
        self.screen_width = self.screen_geometry.width()
        self.screen_height = self.screen_geometry.height()
        print(f"检测到屏幕分辨率: {self.screen_width}x{self.screen_height}")

        # 计算自适应尺寸
        self.calculateAdaptiveSizes()

        # 数据变量
        self.battery_percentage = 100.0
        self.battery_voltage = 12.0
        self.camera_image = None
        self.depth_image = None
        self.bird_view_image = None
        self.pitch = 0
        self.roll = 0
        self.speed = 0
        self.linear_speed = 0
        self.angular_speed = 0

        # 左侧「起飞状态 / 当前状态」与避障摘要用缓存
        self._last_altitude_m = None
        self._last_mavros_status = {}
        # 当前任务阶段（用于「当前状态」卡片，面向操作员）
        self._mission_phase = "idle"  # idle | launching | returning | waypoint | stopped
        self._manual_control_page = False

        # 状态变量
        self.topics_with_data = defaultdict(bool)
        self.current_image_mode = "rgb"

        # UI状态变量 - 启动时左右侧栏都是隐藏且未锁定状态
        self.sidebar_expanded = False  # 左侧栏开始隐藏
        self.right_sidebar_expanded = False  # 右侧栏开始隐藏
        self.left_sidebar_pinned = False
        self.right_sidebar_pinned = False
        self.enable_sidebar_hover = False

        # 进程管理
        self.processes = {}
        self.log_files = {}
        # 待机/启动时 hold goal 用持久 Publisher（勿在定时器里反复 new Publisher，否则 NavRL 常收不到）
        self._hold_goal_publishers = None

        # 返航 FSM 滞回（与航点导航一致，避免刚发目标就误判到达）
        self._return_home_saw_exec = False
        self._return_home_start_time = 0.0
        self._return_home_fsm_exec = 4
        self._return_home_fsm_wait = 1
        self._return_home_dist_thresh = 0.35
        self._return_home_min_sec = 2.5
        self._return_home_navrl = None
        self._navrl_return_goal_pubs = None
        # 返航到达判定（与 navigation_config waypoint_advance 一致，默认 3D）
        self._return_home_dist_mode = "3d"
        self._return_home_xy_thresh = 0.65
        self._return_home_z_thresh = 0.85
        self._return_home_navrl_grace_sec = 2.0
        # 返航原点：避免首帧里程计 (0,0,0) 误锁；一键启动结束后再快照真实起飞位
        self._home_position = None
        self._home_position_locked = False
        self._home_frame_id = ""

        self.last_frame_time = time.time()
        # 右侧图像/鸟瞰图刷新上限，减轻 OpenCV→QPixmap 与主线程压力
        self._right_panel_image_min_dt = float(os.environ.get("MYVIZ_IMAGE_UI_MIN_DT", "0.09"))
        self._last_right_rgb_emit = 0.0
        self._last_right_depth_emit = 0.0
        self._last_obstacle_warn_wall = 0.0
        self._last_bird_emit = 0.0
        self._topic_status_cycle = 0
        self._main_ui_phase = 0
        self._rviz_view_mode = "free"
        self._last_ros_time_label_wall = 0.0
        self._fps_ui_ticks = 0

        # 话题订阅器
        self.topic_subscriber = None
        self.log_window = None

        # 截图目录 - 使用新的路径工具函数
        self.screenshots_dir = get_data_directory("screenshots")

    def _init_ui(self):
        """初始化UI设置"""
        # 设置字体（优先系统已安装的中文字体，避免 WSL/X 下“方块/乱码”）
        chosen_family = apply_best_qt_font(10)
        if not chosen_family:
            print(
                "[字体] 未能设置中文字体。\n"
                "若你看到中文显示为方块/乱码，建议安装字体包：\n"
                "  sudo apt update && sudo apt install -y fonts-noto-cjk fonts-wqy-zenhei fonts-wqy-microhei"
            )

        # 设置图标和标题
        self.setWindowIcon(QIcon("logo.png"))
        self.setWindowTitle("无人机自主导航系统")

        # 创建中央控件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # 设置全局样式
        self.setStyleSheet(GLOBAL_STYLES['main_window'])

        # 设置窗口最小尺寸
        min_width = self.adaptive_left_width + self.adaptive_right_width + 500
        min_height = 600
        self.setMinimumSize(min_width, min_height)

        # 绑定事件
        self.resizeEvent = self.onResize
    def _init_rviz(self):
        """初始化RViz组件"""
        # 设置RViz显示
        self.frame = rviz.VisualizationFrame()
        self.frame.setSplashPath("")
        self.frame.initialize()

        # 同步完成 readFile/load：曾用 QTimer 延后加载，易在首帧 resize/OpenGL 未稳定时调用
        # frame.load()，在部分环境（WSL + D3D12 等）下触发 librviz 段错误。
        try:
            reader = rviz.YamlConfigReader()
            config = rviz.Config()
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_config.rviz")
            reader.readFile(config, cfg_path)
            self.frame.load(config)
        except Exception as e:
            print(f"加载RViz配置文件失败: {e}")

        # 禁用菜单栏、状态栏和"隐藏停靠"按钮
        self.frame.setMenuBar(None)
        self.frame.setStatusBar(None)
        self.frame.setHideButtonVisibility(True)

        self.manager = self.frame.getManager()
        # 与 topics_subscriber 发布的 Path/Marker frame 对齐（见 /myviz/_live_odom_frame、rviz_fixed_frame）
        QTimer.singleShot(300, self._apply_rviz_fixed_frame)
        QTimer.singleShot(2000, self._apply_rviz_fixed_frame)
        QTimer.singleShot(4500, self._apply_rviz_fixed_frame)

    def _apply_rviz_fixed_frame(self):
        """将嵌入 RViz 的 Fixed Frame 与里程计坐标系对齐，否则 Marker 因无 TF 不渲染。"""
        try:
            if not getattr(self, "manager", None) or not hasattr(self.manager, "setFixedFrame"):
                return
            explicit = str(rospy.get_param("/myviz/rviz_fixed_frame", "") or "").strip()
            live = str(rospy.get_param("/myviz/_live_odom_frame", "") or "").strip()
            target = explicit or live
            if not target:
                target = str(rospy.get_param("/myviz/flight_path_frame", "map") or "map").strip()
            self.manager.setFixedFrame(target)
        except Exception as e:
            print(f"设置 RViz Fixed Frame 失败（可忽略）: {e}")

    def _init_timers(self):
        """初始化定时器（合并多个定时器以减少资源占用）"""
        # 主更新定时器 - 合并多个高频更新
        self.main_update_timer = QTimer(self)
        self.main_update_timer.timeout.connect(self._main_update_cycle)
        # ~8Hz：略提高状态栏/FPS 显示流畅度；仍低于相机全速以减轻与 RViz 争用
        self.main_update_timer.start(125)

        # 图像更新检查定时器 - 确保图像能够及时更新
        self.image_update_timer = QTimer(self)
        self.image_update_timer.timeout.connect(self._check_image_update)
        self.image_update_timer.start(125)

        # 一键启动后「同步 goal 到当前位」用单次定时器，用户点「开始导航」时必须取消，否则会覆盖航点目标导致 NavRL 卡住
        self._goal_sync_timer = QTimer(self)
        self._goal_sync_timer.setSingleShot(True)
        self._goal_sync_timer.timeout.connect(self._on_stack_start_goal_sync)

        # 待机期间周期性把导航目标刷到当前位，防止 NavRL 等仍追旧 goal 导致「显示待机却乱飞」
        self._idle_hold_timer = QTimer(self)
        self._idle_hold_timer.timeout.connect(self._idle_refresh_navigation_goal)

        # 鼠标跟踪定时器
        self.sidebar_hover_timer = QTimer(self)
        self.sidebar_hover_timer.timeout.connect(self.checkMousePosition)
        self.sidebar_hover_timer.start(100)  # 降低频率到100ms

        # 延迟初始化定时器
        QTimer.singleShot(1000, self.setupAllOverlaysAndOpenSidebars)  # 修改为打开侧栏的方法
        QTimer.singleShot(1000, self.updateImageSizes)

        # 对接健康检查（低频、可在无仿真时静默失败）
        self.integration_health_timer = QTimer(self)
        self.integration_health_timer.timeout.connect(self.updateIntegrationHealth)
        self.integration_health_timer.start(4000)  # 健康检查含 rospy 调用，低频避免主线程尖刺
        self._last_health_short = "未检查"
        self._last_health_details = []

    def _format_comm_monitor_html(self, hs):
        """面向操作员：无路径、无日志腔，突出正常/异常。"""
        try:
            ok = bool(getattr(hs, "ok", False))
            head = "链路正常" if ok else "需要关注"
            head_color = "#2ECC71" if ok else "#F39C12"
            parts = [
                f"<p style='margin:0 0 10px 0;padding:6px 8px;border-radius:6px;"
                f"background:rgba(52,152,219,0.15);font-size:15px;font-weight:bold;color:{head_color};'>"
                f"{html.escape(head)}</p>"
            ]
            for line in getattr(hs, "details", []) or []:
                s = (line or "").strip()
                if not s:
                    continue
                if s.startswith("log=") or s.startswith("- log="):
                    continue
                if s.startswith("  - ") and (
                    "/home/" in s or "/." in s or "log=" in s or len(s) > 120
                ):
                    continue
                if "无 MAVROS 时此项失败" in s or "纯 CERLAB 仿真时可忽略" in s:
                    continue
                if s.startswith("[OK]"):
                    msg = html.escape(s.replace("[OK]", "").strip())
                    parts.append(
                        f"<p style='margin:4px 0;color:#A9DFBF;font-size:13px;line-height:1.45;'>"
                        f"✓ {msg}</p>"
                    )
                elif s.startswith("[FAIL]"):
                    raw = s.replace("[FAIL]", "").strip()
                    if "mavros" in raw.lower() or "MAVROS" in raw:
                        raw = "飞控链路未连接（纯仿真时通常可忽略）"
                    msg = html.escape(raw)
                    parts.append(
                        f"<p style='margin:4px 0;color:#F5B7B1;font-size:13px;line-height:1.45;'>"
                        f"! {msg}</p>"
                    )
                elif s.startswith("  - "):
                    continue
                else:
                    parts.append(
                        f"<p style='margin:2px 0;color:#D5D8DC;font-size:12px;'>{html.escape(s)}</p>"
                    )
            return "".join(parts) if len(parts) > 1 else parts[0]
        except Exception:
            return "<p style='color:#BDC3C7;'>通信状态暂不可用</p>"

    def updateIntegrationHealth(self):
        """对接健康检查：技术细节进连接状态悬停；监控区仅展示友好摘要。"""
        try:
            if build_overall_summary is None:
                self._last_health_short = "未检查"
                self._last_health_details = []
                if hasattr(self, "comm_monitor_text") and self.comm_monitor_text:
                    self.comm_monitor_text.setHtml(
                        "<p style='color:#BDC3C7;font-size:13px;line-height:1.5;'>"
                        "通信自检暂不可用。详细技术信息请将鼠标悬停在左侧「连接状态」上查看。</p>"
                    )
            else:
                hs = build_overall_summary(rospy)
                self._last_health_short = hs.short
                self._last_health_details = hs.details

                if hasattr(self, "connection_label") and self.connection_label:
                    tip = "\n".join(self._last_health_details[:28])
                    if len(self._last_health_details) > 28:
                        tip += "\n..."
                    self.connection_label.setToolTip(tip)

                if hasattr(self, "comm_monitor_text") and self.comm_monitor_text:
                    self.comm_monitor_text.setHtml(self._format_comm_monitor_html(hs))
        except Exception:
            pass

        try:
            if hasattr(self, "updateObstacleAvoidanceWarning"):
                self.updateObstacleAvoidanceWarning()
        except Exception:
            pass

    def _main_update_cycle(self):
        """主更新循环 - 合并多个更新操作"""
        try:
            # 更新状态栏
            self.updateStatusBar()

            ph = self._main_ui_phase
            self._main_ui_phase = ph + 1

            # 悬浮数据/位置与主循环相位绑定
            if ph % 3 == 0:
                self._update_compass_data()
                self._update_attitude_widget_data()

            if ph % 2 == 0:
                if hasattr(self, 'frame') and self.frame and self.frame.isVisible():
                    if hasattr(self, 'rviz_overlay') and hasattr(self, 'updateOverlayPosition'):
                        self.updateOverlayPosition()
                    if hasattr(self, 'compass') and hasattr(self, 'updateCompassPosition'):
                        self.updateCompassPosition()
                    if hasattr(self, 'attitude_widget') and hasattr(self, 'updateAttitudeWidgetPosition'):
                        self.updateAttitudeWidgetPosition()
                    # 悬浮条 H/D 与侧栏数值同步（避免仅一侧更新）
                    if ph % 6 == 0 and hasattr(self, "updateOverlayData"):
                        self.updateOverlayData()

            self._fps_ui_ticks += 1

            # 待机时应保持 idle_hold 定时器运行（防止异常停表后不再刷 hold goal）
            if ph % 40 == 0:
                self._ensure_idle_hold_timer_running()

        except Exception as e:
            print(f"主更新循环错误: {e}")

    def _check_image_update(self):
        """检查并更新图像显示 - 确保图像能够及时更新"""
        try:
            # 检查是否有图像标签
            if not hasattr(self, 'image_label') or not self.image_label:
                return

            # 根据当前模式检查是否有新的图像数据需要显示
            should_update = False

            if self.current_image_mode == "rgb" and self.camera_image is not None:
                # 检查RGB图像是否需要更新
                should_update = True
            elif self.current_image_mode == "depth" and self.depth_image is not None:
                # 检查深度图像是否需要更新
                should_update = True

            # 如果需要更新且当前显示的是占位符文本，则强制更新
            if should_update:
                current_pixmap = self.image_label.pixmap()
                if current_pixmap is None or current_pixmap.isNull():
                    # 当前没有显示图像，强制更新
                    self.updateImageDisplay()

        except Exception as e:
            # 静默处理错误，避免干扰主程序
            pass

    def _update_compass_data(self):
        """更新指南针数据"""
        try:
            if hasattr(self, 'topic_subscriber') and self.topic_subscriber and hasattr(self, 'compass') and self.compass:
                # 检查姿态话题是否活跃
                if self.topic_subscriber.is_topic_active("attitude"):
                    # 尝试从姿态数据获取航向信息
                    attitude_data = self.topic_subscriber.get_latest_data("attitude")
                    if attitude_data and "yaw" in attitude_data:
                        # 获取原始yaw值
                        yaw_value = attitude_data.get("yaw", 0)
                        if isinstance(yaw_value, list):
                            if len(yaw_value) > 0:
                                yaw_value = yaw_value[0]  # 取列表的第一个元素
                            else:
                                yaw_value = 0  # 空列表时使用默认值

                        # 限制在360度范围内
                        if yaw_value > 360:
                            yaw_value = yaw_value % 360
                        elif yaw_value < -360:
                            yaw_value = yaw_value % 360

                        # 直接使用yaw值作为指南针角度
                        self.compass.set_heading(-yaw_value)

        except Exception as e:
            print(f"更新指南针数据时出错: {str(e)}")

    def _update_attitude_widget_data(self):
        """更新姿态指示器数据"""
        try:
            if hasattr(self, 'topic_subscriber') and self.topic_subscriber and hasattr(self, 'attitude_widget') and self.attitude_widget:
                # 检查姿态话题是否活跃
                if self.topic_subscriber.is_topic_active("attitude"):
                    # 从姿态数据获取俯仰和滚转角度
                    attitude_data = self.topic_subscriber.get_latest_data("attitude")
                    if attitude_data:
                        # 获取俯仰角并检查是否为列表
                        pitch_value = attitude_data.get("pitch", 0)
                        if isinstance(pitch_value, list):
                            if len(pitch_value) > 0:
                                pitch_value = pitch_value[0]
                            else:
                                pitch_value = 0

                        # 获取滚转角并检查是否为列表
                        roll_value = attitude_data.get("roll", 0)
                        if isinstance(roll_value, list):
                            if len(roll_value) > 0:
                                roll_value = roll_value[0]
                            else:
                                roll_value = 0

                        # 更新姿态指示器
                        self.attitude_widget.update_attitude(pitch_value, roll_value)

        except Exception as e:
            print(f"更新姿态指示器数据时出错: {str(e)}")

    def _update_overlay_positions(self):
        """立即更新所有悬浮窗口位置"""
        try:
            # 确保RViz框架已经完成布局更新
            if hasattr(self, 'frame') and self.frame:
                # 强制更新RViz框架的几何信息
                self.frame.update()
                QApplication.processEvents()

            # 更新各个悬浮窗口位置
            if hasattr(self, 'updateOverlayPosition'):
                self.updateOverlayPosition()
            if hasattr(self, 'updateCompassPosition'):
                self.updateCompassPosition()
            if hasattr(self, 'updateAttitudeWidgetPosition'):
                self.updateAttitudeWidgetPosition()
        except Exception as e:
            print(f"更新悬浮窗口位置时出错: {e}")

    def _create_styled_button(self, text, style_type="primary", min_width=120, min_height=30):
        """创建带样式的按钮，减少重复代码"""
        button = QPushButton(text)

        if style_type == "primary":
            style = GLOBAL_STYLES['button_primary'].format(
                min_width=min_width,
                min_height=min_height
            )
        else:
            # 可以扩展其他样式类型
            style = GLOBAL_STYLES['button_primary'].format(
                min_width=min_width,
                min_height=min_height
            )

        button.setStyleSheet(style)
        return button

    def _safe_execute(self, func, error_msg="操作执行失败", *args, **kwargs):
        """安全执行函数，统一错误处理"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"{error_msg}: {str(e)}")
            return None

    def _update_label_safely(self, label, text, default_text="数据获取失败"):
        """安全更新标签文本"""
        try:
            if hasattr(self, label) and getattr(self, label):
                getattr(self, label).setText(text)
        except Exception as e:
            print(f"更新标签 {label} 失败: {e}")
            if hasattr(self, label) and getattr(self, label):
                getattr(self, label).setText(default_text)

    def _scale_and_set_pixmap(self, label_name, pixmap, width=None, height=None):
        """统一的图像缩放和设置函数"""
        if not hasattr(self, label_name) or not getattr(self, label_name):
            return False

        try:
            label = getattr(self, label_name)
            if width is None:
                width = self.adaptive_image_width
            if height is None:
                height = self.adaptive_image_height

            scaled_pixmap = pixmap.scaled(
                width, height,
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
            label.setPixmap(scaled_pixmap)
            return True
        except Exception as e:
            print(f"设置图像到 {label_name} 失败: {e}")
            return False

    def _cleanup_resources(self):
        """清理资源，减少内存泄漏"""
        try:
            # 停止所有定时器
            if hasattr(self, 'main_update_timer'):
                self.main_update_timer.stop()
            if hasattr(self, 'image_update_timer'):
                self.image_update_timer.stop()
            if hasattr(self, 'sidebar_hover_timer'):
                self.sidebar_hover_timer.stop()

            # 清理图像数据
            self.camera_image = None
            self.depth_image = None
            self.bird_view_image = None

            # 清理话题订阅器
            if self.topic_subscriber:
                self.topic_subscriber = None

            # 清理动画对象
            if hasattr(self, 'sidebar_animation'):
                try:
                    self.sidebar_animation.finished.disconnect()
                    self.sidebar_animation.valueChanged.disconnect()
                    self.sidebar_animation.stop()
                    self.sidebar_animation.deleteLater()
                except:
                    pass

            if hasattr(self, 'right_sidebar_animation'):
                try:
                    self.right_sidebar_animation.finished.disconnect()
                    self.right_sidebar_animation.valueChanged.disconnect()
                    self.right_sidebar_animation.stop()
                    self.right_sidebar_animation.deleteLater()
                except:
                    pass

            print("资源清理完成")
        except Exception as e:
            print(f"资源清理时出错: {e}")

    def closeEvent(self, event):
        """窗口关闭事件处理 - 优化版本"""
        try:
            print("正在关闭应用程序...")

            # 清理资源
            self._cleanup_resources()

            # 关闭悬浮窗口
            if hasattr(self, 'overlay_widget') and self.overlay_widget:
                self.overlay_widget.close()
            if hasattr(self, 'compass') and self.compass:
                self.compass.close()
            if hasattr(self, 'attitude_widget') and self.attitude_widget:
                self.attitude_widget.close()
            if hasattr(self, 'log_window') and self.log_window:
                self.log_window.close()

            # 终止进程
            self._safe_execute(self.silentStopDroneSystem, "停止进程失败")

            # 接受关闭事件
            event.accept()

        except Exception as e:
            print(f"关闭事件处理失败: {e}")
            event.accept()  # 即使出错也要关闭

    def _create_layouts(self):
        """创建主要布局"""
        ## 创建主布局
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(10, 15, 10, 10)  # 增加上边距
        main_layout.setSpacing(10)  # 增加组件间距

        ## 创建标题和工具栏区域
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #1A202C; border-radius: 5px;")
        header_widget.setMaximumHeight(120)  # 提高标题栏最大高度
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(5, 5, 5, 5)
        header_layout.setSpacing(2)
        
        # 创建标题标签
        title_label = QLabel("无人机自主导航系统")
        title_label.setStyleSheet("font-size: 24pt; color: #3498DB; padding: 10px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setMinimumWidth(500)  # 设置最小宽度
        title_label.setMaximumHeight(60)  # 增加标题标签高度
        header_layout.addWidget(title_label)
        
        # 创建工具栏
        toolbar_widget = QWidget()
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(5, 0, 5, 0)
        toolbar_layout.setSpacing(10)
        
        # 左侧功能按钮
        function_layout = QHBoxLayout()
        function_layout.setSpacing(8)  # 减少按钮间距
        
        # # 启动程序按钮
        # start_button = QPushButton("启动程序")
        # start_button.setIcon(QIcon(":/images/icons/start.svg"))
        # start_button.setIconSize(QSize(24, 24))
        # start_button.setStyleSheet("background-color: #27AE60; text-align: center; padding-left: 5px;")
        # start_button.setMinimumWidth(120)
        # start_button.setMaximumHeight(36)
        # function_layout.addWidget(start_button)
        
        # # 操控无人机按钮
        # control_button = QPushButton("操控无人机")
        # control_button.setIcon(QIcon(":/images/icons/joystick.png"))
        # control_button.setIconSize(QSize(24, 24))
        # control_button.setMinimumWidth(120)
        # control_button.setMaximumHeight(36)
        # function_layout.addWidget(control_button)
        
        # # 设置按钮，用于显示/隐藏Display面板
        # self.settings_button = QPushButton("设置")
        # self.settings_button.setIcon(QIcon(":/images/setting.png"))
        # self.settings_button.setIconSize(QSize(24, 24))
        # self.settings_button.setMinimumWidth(120)
        # self.settings_button.setMaximumHeight(36)
        # self.settings_button.clicked.connect(self.toggleRVizDisplayPanel)
        # function_layout.addWidget(self.settings_button)
        
        toolbar_layout.addLayout(function_layout)
        toolbar_layout.addStretch(1)  # 添加弹性空间
        
        # 添加日志按钮
        self.log_button = QPushButton("日志显示")
        self.log_button.setIcon(QIcon(":/images/icons/log.svg"))
        self.log_button.setIconSize(QSize(24, 24))
        self.log_button.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                min-width: 120px;
                min-height: 36px;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #3498DB;
            }
            QPushButton:pressed {
                background-color: #2980B9;
            }
            QPushButton:checked {
                background-color: #2980B9;
                border: 1px solid #1ABC9C;
            }
        """)
        self.log_button.setCheckable(True)  # 可以切换选中状态
        self.log_button.clicked.connect(self.toggleLogWindow)
        function_layout.addWidget(self.log_button)
        
        # 添加间隔
        function_layout.addSpacing(15)
        
        # 右侧状态显示
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)  # 减少状态组件间距
        
        # 电池状态显示
        self.battery_icon_label = QLabel()
        self.battery_icon_label.setPixmap(QPixmap(":/images/icons/battery_100.svg").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.battery_icon_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.battery_icon_label)
        
        # 电压图标
        voltage_icon_label = QLabel()
        voltage_icon_label.setPixmap(QPixmap(":/images/icons/voltage.svg").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        voltage_icon_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(voltage_icon_label)
        
        # 电压数值显示
        self.voltage_label = QLabel("0.0 V")
        self.voltage_label.setStyleSheet("color: #3498DB; font-weight: bold;")
        self.voltage_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_layout.addWidget(self.voltage_label)
        
        # 添加右侧状态栏
        toolbar_layout.addLayout(status_layout)
        
        header_layout.addWidget(toolbar_widget)
        main_layout.addWidget(header_widget)
        
        # 创建中间的大型分割器，包含左侧边栏和RViz显示区域
        self.main_splitter = QSplitter(Qt.Horizontal)
        
        # 创建左侧边栏，用于显示速度表盘和其他信息
        self.left_sidebar = QWidget()
        # 初始状态设置为隐藏（宽度为0）
        self.left_sidebar.setFixedWidth(0)
        self.left_sidebar.setVisible(False)
        # 使用QSizePolicy允许垂直方向缩放
        self.left_sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        left_sidebar_layout = QVBoxLayout(self.left_sidebar)
        left_sidebar_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        left_sidebar_layout.setSpacing(10)  # 减小组件间距
        
        # 添加无人机状态组件 - 现代化卡片设计
        status_group = QGroupBox("🚁 无人机状态")
        status_group.setStyleSheet("""
            QGroupBox {
                color: #3498DB;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #3498DB;
                border-radius: 12px;
                padding: 15px;
                margin-top: 20px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(52, 152, 219, 0.1),
                    stop:1 rgba(26, 32, 44, 0.8));
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
                background-color: #1E2330;
                border-radius: 6px;
            }
        """)
        status_group_layout = QVBoxLayout(status_group)
        status_group_layout.setContentsMargins(0, 0, 0, 0)  # 进一步减少内边距
        status_group_layout.setSpacing(4)  # 进一步减少组件间距

        # 创建无人机状态信息容器，使用现代化卡片布局
        info_container = QWidget()
        info_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        info_container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(44, 62, 80, 0.9),
                    stop:1 rgba(26, 32, 44, 0.9));
                border-radius: 10px;
                border: 1px solid rgba(52, 152, 219, 0.3);
            }
        """)
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(3, 3, 3, 3)  # 进一步减少内边距
        info_layout.setSpacing(3)  # 进一步减少组件间距
        
        # 创建状态卡片容器
        self.createStatusCards(info_layout)
        QTimer.singleShot(0, self._update_mission_status_label)

        status_group_layout.addWidget(info_container, 1)  # 使用拉伸系数1
        
        # 添加状态组到左侧边栏，增加拉伸系数给状态组更多空间
        left_sidebar_layout.addWidget(status_group, 3)  # 增加拉伸系数，给状态组更多空间

        # 添加功能区域组件（与状态区分离）
        function_group = QGroupBox("🎮 控制中心")
        function_group.setStyleSheet("""
            QGroupBox {
                color: #3498DB;
                font-size: 16pt;
                font-weight: bold;
                border: 2px solid #3498DB;
                border-radius: 12px;
                padding: 15px;
                margin-top: 20px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(52, 152, 219, 0.1),
                    stop:1 rgba(26, 32, 44, 0.8));
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 10px;
                background-color: #1E2330;
                border-radius: 6px;
            }
        """)
        function_group.setObjectName("function_group")  # 设置对象名，方便后续查找
        self.function_group = function_group  # 保存引用
        function_group_layout = QVBoxLayout(function_group)
        function_group_layout.setContentsMargins(0, 0, 0, 0)  # 移除所有内边距
        function_group_layout.setSpacing(0)  # 移除间距
        
        # 添加功能按钮区域
        function_area = QFrame()
        function_area.setFrameShape(QFrame.StyledPanel)
        function_area.setStyleSheet("""
            QFrame {
                background-color: #1A202C; 
                border-radius: 10px; 
                border: 1px solid #3498DB;
            }
        """)
        # 移除高度限制，允许拉伸填充
        function_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 创建垂直布局来放置功能按钮
        function_container = QVBoxLayout(function_area)
        function_container.setContentsMargins(5, 5, 5, 5)  # 减小内边距
        function_container.setSpacing(0)  # 减小组件间距
        
        # 创建滑动控制中心组件
        if SlidingControlCenter:
            self.sliding_control_center = SlidingControlCenter(self)
            # 根据屏幕尺寸调整控件大小
            if self.screen_width <= 1366:  # 小屏幕
                min_size = 300
                max_size = 450
            elif self.screen_width <= 1920:  # 中等屏幕
                min_size = 350
                max_size = 550
            else:  # 大屏幕
                min_size = 400
                max_size = 650

            self.sliding_control_center.setMinimumSize(min_size, min_size)
            self.sliding_control_center.setMaximumSize(max_size, max_size)

            # 连接自主飞行页面的信号
            self.sliding_control_center.centerClicked.connect(self.startDroneSystem)  # 一键启动
            self.sliding_control_center.leftClicked.connect(self.publishNavigationGoal)  # 前往目标
            self.sliding_control_center.rightClicked.connect(self.stopDroneSystem)    # 停止程序
            self.sliding_control_center.topClicked.connect(self.returnToHome)         # 一键返航
            self.sliding_control_center.bottomClicked.connect(self.importPointCloud)  # 导入点云（待实现）

            # 连接手动控制页面的信号
            self.sliding_control_center.manualStartClicked.connect(self.onManualStart)
            self.sliding_control_center.manualTakeoffClicked.connect(self.onManualTakeoff)
            self.sliding_control_center.manualSelfRescueClicked.connect(self.onManualSelfRescue)
            self.sliding_control_center.manualUpClicked.connect(self.onManualUp)
            self.sliding_control_center.manualDownClicked.connect(self.onManualDown)
            self.sliding_control_center.manualLeftClicked.connect(self.onManualLeft)
            self.sliding_control_center.manualRightClicked.connect(self.onManualRight)

            # 连接持续控制信号（按下和释放）
            self.sliding_control_center.manualUpPressed.connect(self.onManualUpPressed)
            self.sliding_control_center.manualUpReleased.connect(self.onManualUpReleased)
            self.sliding_control_center.manualDownPressed.connect(self.onManualDownPressed)
            self.sliding_control_center.manualDownReleased.connect(self.onManualDownReleased)
            self.sliding_control_center.manualLeftPressed.connect(self.onManualLeftPressed)
            self.sliding_control_center.manualLeftReleased.connect(self.onManualLeftReleased)
            self.sliding_control_center.manualRightPressed.connect(self.onManualRightPressed)
            self.sliding_control_center.manualRightReleased.connect(self.onManualRightReleased)
            try:
                self.sliding_control_center.pageChanged.connect(self._on_control_center_page_changed)
            except Exception:
                pass

            # 添加到功能区域，居中对齐
            function_container.addWidget(self.sliding_control_center, 0, Qt.AlignCenter)
        elif UIButton:
            # 如果SlidingControlCenter不可用，回退到原来的UIButton
            self.ui_button = UIButton()
            # 根据屏幕尺寸调整控件大小，小屏幕使用更小的尺寸
            if self.screen_width <= 1366:  # 小屏幕
                min_size = 250
                max_size = 400
            elif self.screen_width <= 1920:  # 中等屏幕
                min_size = 300
                max_size = 500
            else:  # 大屏幕
                min_size = 350
                max_size = 600

            self.ui_button.setMinimumSize(min_size, min_size)
            self.ui_button.setMaximumSize(max_size, max_size)
            # 连接信号到对应的槽函数
            self.ui_button.centerClicked.connect(self.startDroneSystem)  # 中间按钮 - 一键启动
            # self.ui_button.topClicked.connect(self.onTopButtonClick)     # 顶部按钮 - 一键返航
            self.ui_button.leftClicked.connect(self.publishNavigationGoal)  # 左侧按钮 - 开始导航
            self.ui_button.rightClicked.connect(self.stopDroneSystem)    # 右侧按钮 - 停止程序
            # 底部按钮暂时不连接功能

            # 添加到功能区域，居中对齐
            function_container.addWidget(self.ui_button, 0, Qt.AlignCenter)
        else:
            # 如果UIButton不可用，使用原来的按钮布局
            # 使用GridLayout进行布局，方便按钮的定位
            function_grid = QWidget()
            function_layout = QGridLayout(function_grid)
            function_layout.setContentsMargins(5, 2, 5, 2)  # 减小内边距
            function_layout.setSpacing(3)  # 进一步减小组件间距
            
            # 创建上方按钮 - 一键返航
            return_home_btn = QPushButton("一键返航")
            return_home_btn.setCursor(Qt.PointingHandCursor)  # 设置鼠标悬停时的光标为手型
            return_home_btn.setStyleSheet("""
                QPushButton {
                    background-color: #8E44AD;
                    color: white;
                    border-radius: 8px;
                    font-size: 12pt;
                    font-weight: bold;
                    padding: 8px;
                    min-height: 40px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #9B59B6;
                }
                QPushButton:pressed {
                    background-color: #7D3C98;
                }
            """)
            # 添加阴影效果
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setColor(QColor(0, 0, 0, 60))
            shadow.setOffset(2, 2)
            return_home_btn.setGraphicsEffect(shadow)
            return_home_btn.clicked.connect(self.onTopButtonClick)
            
            function_layout.addWidget(return_home_btn, 0, 1)
            
            # 创建左侧按钮 - 开始导航 - 文字竖向排列
            explore_btn = QPushButton()
            explore_btn.setCursor(Qt.PointingHandCursor)  # 设置鼠标悬停时的光标为手型
            explore_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27AE60;
                    color: white;
                    border-radius: 8px;
                    font-size: 12pt;
                    font-weight: bold;
                    padding: 20px 5px;
                    min-width: 40px;
                    min-height: 100px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #2ECC71;
                }
                QPushButton:pressed {
                    background-color: #229954;
                }
            """)
            # 添加阴影效果
            shadow2 = QGraphicsDropShadowEffect()
            shadow2.setBlurRadius(10)
            shadow2.setColor(QColor(0, 0, 0, 60))
            shadow2.setOffset(2, 2)
            explore_btn.setGraphicsEffect(shadow2)
            # 创建竖向文字标签
            explore_label = QLabel("开\n始\n探\n索")
            explore_label.setAlignment(Qt.AlignCenter)
            explore_label.setStyleSheet("color: white; background-color: transparent; font-size: 12pt; font-weight: bold;")
            # 添加标签到按钮
            explore_layout = QVBoxLayout(explore_btn)
            explore_layout.setContentsMargins(5, 5, 5, 5)
            explore_layout.addWidget(explore_label, 0, Qt.AlignCenter)
            
            # 连接开始导航按钮的点击事件
            explore_btn.clicked.connect(self.publishNavigationGoal)
            
            function_layout.addWidget(explore_btn, 1, 0)
            
            # 创建中间按钮 - 一键启动（无背景色）
            start_btn = QPushButton()
            start_btn.setCursor(Qt.PointingHandCursor)  # 设置鼠标悬停时的光标为手型
            start_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: white;
                    border-radius: 50px;  /* 完全圆形 */
                    font-size: 14pt;
                    font-weight: bold;
                    min-width: 100px;
                    min-height: 100px;
                    max-width: 100px;
                    max-height: 100px;
                    border: none;  /* 无边框 */
                }
                QPushButton:hover {
                    background-color: rgba(39, 174, 96, 30);  /* 绿色半透明悬停效果 */
                }
                QPushButton:pressed {
                    background-color: rgba(39, 174, 96, 50);  /* 绿色半透明按下效果 */
                }
            """)
            # 添加阴影效果
            shadow3 = QGraphicsDropShadowEffect()
            shadow3.setBlurRadius(15)
            shadow3.setColor(QColor(39, 174, 96, 80))  # 使用绿色阴影
            shadow3.setOffset(0, 0)
            start_btn.setGraphicsEffect(shadow3)
            
            # 创建垂直布局来排列图标和文字
            start_layout = QVBoxLayout(start_btn)
            start_layout.setContentsMargins(5, 5, 5, 5)  # 减小内边距
            start_layout.setSpacing(2)  # 减小组件间距
            
            # 添加图标
            start_icon_label = QLabel()
            # 创建一个绿色滤镜，将图标颜色转换为绿色
            icon_pixmap = QPixmap(":/images/icons/start.svg").scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # 创建一个绿色滤镜效果
            icon_painter = QPainter(icon_pixmap)
            icon_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            icon_painter.fillRect(icon_pixmap.rect(), QColor("#27AE60"))  # 绿色
            icon_painter.end()
            
            start_icon_label.setPixmap(icon_pixmap)
            start_icon_label.setAlignment(Qt.AlignCenter)
            start_layout.addWidget(start_icon_label, 0, Qt.AlignCenter)
            
            # 添加文字标签
            start_text_label = QLabel("一键启动")
            start_text_label.setStyleSheet("color: #27AE60; background-color: transparent; font-size: 14pt; font-weight: bold; border: none;")
            start_text_label.setAlignment(Qt.AlignCenter)
            start_layout.addWidget(start_text_label, 0, Qt.AlignCenter)
            
            # 连接一键启动按钮的点击事件
            start_btn.clicked.connect(self.startDroneSystem)
            
            function_layout.addWidget(start_btn, 1, 1)
            
            # 创建右侧按钮 - 停止程序 - 文字竖向排列
            future_btn_right = QPushButton()
            future_btn_right.setCursor(Qt.PointingHandCursor)  # 设置鼠标悬停时的光标为手型
            future_btn_right.setStyleSheet("""
                QPushButton {
                    background-color: #E74C3C;  /* 红色背景 */
                    color: white;
                    border-radius: 8px;
                    font-size: 12pt;
                    font-weight: bold;
                    padding: 20px 5px;
                    min-width: 40px;
                    min-height: 100px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #C0392B;  /* 深红色悬停效果 */
                }
                QPushButton:pressed {
                    background-color: #A93226;  /* 更深红色按下效果 */
                }
            """)
            # 添加阴影效果
            shadow4 = QGraphicsDropShadowEffect()
            shadow4.setBlurRadius(10)
            shadow4.setColor(QColor(0, 0, 0, 60))
            shadow4.setOffset(2, 2)
            future_btn_right.setGraphicsEffect(shadow4)
            # 创建竖向文字标签
            future_label = QLabel("停\n止\n程\n序")
            future_label.setAlignment(Qt.AlignCenter)
            future_label.setStyleSheet("color: white; background-color: transparent; font-size: 12pt; font-weight: bold;")
            # 添加标签到按钮
            future_layout = QVBoxLayout(future_btn_right)
            future_layout.setContentsMargins(5, 5, 5, 5)
            future_layout.addWidget(future_label, 0, Qt.AlignCenter)
            
            # 连接停止按钮的点击事件
            future_btn_right.clicked.connect(self.stopDroneSystem)
            
            function_layout.addWidget(future_btn_right, 1, 2)
            
            # 设置列和行的拉伸因子，使布局更合理
            function_layout.setColumnStretch(0, 1)  # 左列
            function_layout.setColumnStretch(1, 4)  # 中列
            function_layout.setColumnStretch(2, 1)  # 右列
            function_layout.setRowStretch(0, 1)     # 上行
            function_layout.setRowStretch(1, 4)     # 中行
            function_layout.setRowStretch(2, 1)     # 下行
            
            # 设置按钮之间的对齐方式和间距
            function_layout.setAlignment(return_home_btn, Qt.AlignCenter)
            function_layout.setAlignment(explore_btn, Qt.AlignCenter)
            function_layout.setAlignment(start_btn, Qt.AlignCenter)
            function_layout.setAlignment(future_btn_right, Qt.AlignCenter)
            
            # 将网格布局添加到容器中
            function_container.addWidget(function_grid)
        
        # 添加功能区到功能组
        function_group_layout.addWidget(function_area)
        
        # 添加功能组到左侧边栏，减少拉伸系数给状态组更多空间
        left_sidebar_layout.addWidget(function_group, 2)  # 减少拉伸系数，让状态组有更多空间
        
        # 添加左侧边栏和RViz显示区域到分割器
        self.main_splitter.addWidget(self.left_sidebar)
        
        # 创建侧边栏控制按钮容器
        sidebar_control_container = QWidget()
        sidebar_control_container.setFixedWidth(20)  # 增加宽度到20px
        sidebar_control_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        sidebar_control_container.setStyleSheet("""
            QWidget {
                background-color: #1A202C;
                border-left: none;
                border-right: 1px solid #3498DB;
            }
        """)
        
        # 创建垂直布局
        sidebar_control_layout = QVBoxLayout(sidebar_control_container)
        sidebar_control_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_control_layout.setSpacing(0)
        
        # 创建切换按钮，使用图标替代文字
        self.toggle_sidebar_btn = QPushButton()
        self.toggle_sidebar_btn.setFixedWidth(20)  # 保持宽度
        self.toggle_sidebar_btn.setFixedHeight(50)  # 设置固定高度使图标更显眼
        # 使用图标
        self.toggle_sidebar_btn.setIcon(QIcon(":/images/icons/dropleft.svg"))
        self.toggle_sidebar_btn.setIconSize(QSize(16, 16))
        self.toggle_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A202C;  /* 与周围颜色相协调 */
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3498DB;  /* 蓝色悬停效果 */
            }
            QPushButton:pressed {
                background-color: #2980B9;  /* 按下效果 */
            }
        """)
        self.toggle_sidebar_btn.setCursor(Qt.PointingHandCursor)
        
        # 当按钮被点击时触发侧边栏的显示/隐藏或固定
        # 初始状态为隐藏，按钮图标应该显示向右箭头
        self.toggle_sidebar_btn.setIcon(QIcon(":/images/icons/dropright.svg"))
        self.toggle_sidebar_btn.clicked.connect(self.toggleLeftSidebarPinned)
        
        # 将按钮添加到布局
        sidebar_control_layout.addWidget(self.toggle_sidebar_btn, 0, Qt.AlignCenter)
        
        # 添加控制容器到主分割器
        self.main_splitter.addWidget(sidebar_control_container)
        
        # 中部：RViz + 底部视角切换（自由 / 跟随机体）
        self.rviz_center_container = QWidget()
        self.rviz_center_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rviz_outer = QVBoxLayout(self.rviz_center_container)
        rviz_outer.setContentsMargins(0, 0, 0, 0)
        rviz_outer.setSpacing(0)
        rviz_outer.addWidget(self.frame, 1)
        view_bar = QWidget()
        view_bar.setFixedHeight(36)
        view_bar.setStyleSheet("""
            QWidget { background-color: #1A202C; border-top: 1px solid #2d3748; }
            QLabel { color: #a0aec0; border: none; background: transparent; font-size: 10pt; }
            QPushButton {
                color: #e2e8f0;
                background-color: #2d3748;
                border: 1px solid #4a5568;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 10pt;
            }
            QPushButton:hover { background-color: #3182ce; border-color: #3182ce; }
            QPushButton:pressed { background-color: #2b6cb0; }
            QPushButton:checked { background-color: #3182ce; border-color: #63b3ed; }
        """)
        vb = QHBoxLayout(view_bar)
        vb.setContentsMargins(8, 4, 8, 4)
        vb.setSpacing(8)
        vb.addWidget(QLabel("视角"))
        self.rviz_view_free_btn = QPushButton("自由视角")
        self.rviz_view_follow_btn = QPushButton("跟随机体")
        self.rviz_view_free_btn.setCheckable(True)
        self.rviz_view_follow_btn.setCheckable(True)
        self.rviz_view_free_btn.setChecked(True)
        self.rviz_view_free_btn.setCursor(Qt.PointingHandCursor)
        self.rviz_view_follow_btn.setCursor(Qt.PointingHandCursor)
        self.rviz_view_free_btn.clicked.connect(self.onRvizViewFreeClick)
        self.rviz_view_follow_btn.clicked.connect(self.onRvizViewFollowClick)
        vb.addWidget(self.rviz_view_free_btn)
        vb.addWidget(self.rviz_view_follow_btn)
        vb.addStretch(1)
        rviz_outer.addWidget(view_bar, 0)
        self.main_splitter.addWidget(self.rviz_center_container)
        
        # # 设置按钮点击处理函数更新
        # self.settings_button.clicked.connect(self.toggleRVizDisplayPanel)
        
        # 创建右侧栏控制按钮容器
        right_sidebar_control_container = QWidget()
        right_sidebar_control_container.setFixedWidth(20)  # 增加宽度到20px
        right_sidebar_control_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        right_sidebar_control_container.setStyleSheet("""
            QWidget {
                background-color: #1A202C;
                border-left: none;
                border-right: 1px solid #3498DB;
            }
        """)
        
        # 创建垂直布局
        right_sidebar_control_layout = QVBoxLayout(right_sidebar_control_container)
        right_sidebar_control_layout.setContentsMargins(0, 0, 0, 0)
        right_sidebar_control_layout.setSpacing(0)
        
        # 创建切换按钮，使用图标替代文字
        self.toggle_right_sidebar_btn = QPushButton()
        self.toggle_right_sidebar_btn.setFixedWidth(20)  # 保持宽度
        self.toggle_right_sidebar_btn.setFixedHeight(50)  # 设置固定高度使图标更显眼
        # 使用图标
        self.toggle_right_sidebar_btn.setIcon(QIcon(":/images/icons/dropright.svg"))
        self.toggle_right_sidebar_btn.setIconSize(QSize(16, 16))
        self.toggle_right_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A202C;  /* 与周围颜色相协调 */
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3498DB;  /* 蓝色悬停效果 */
            }
            QPushButton:pressed {
                background-color: #2980B9;  /* 按下效果 */
            }
        """)
        self.toggle_right_sidebar_btn.setCursor(Qt.PointingHandCursor)
        
        # 当按钮被点击时触发右侧栏的显示/隐藏或固定
        # 初始状态为隐藏，按钮图标应该显示向左箭头
        self.toggle_right_sidebar_btn.setIcon(QIcon(":/images/icons/dropleft.svg"))
        self.toggle_right_sidebar_btn.clicked.connect(self.toggleRightSidebarPinned)
        
        # 将按钮添加到布局
        right_sidebar_control_layout.addWidget(self.toggle_right_sidebar_btn, 0, Qt.AlignCenter)
        
        # 添加右侧控制按钮容器到主分割器
        self.main_splitter.addWidget(right_sidebar_control_container)
        
        # 创建右侧栏
        self.right_sidebar = QWidget()
        # 初始状态设置为隐藏（宽度为0）
        self.right_sidebar.setFixedWidth(0)
        self.right_sidebar.setVisible(False)
        # 使右侧栏可以在垂直方向调整大小
        self.right_sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)  # 设置固定宽度策略
        right_sidebar_layout = QVBoxLayout(self.right_sidebar)
        right_sidebar_layout.setContentsMargins(5, 5, 5, 5)  # 设置较小的边距
        right_sidebar_layout.setSpacing(0)  # 去除组件间距
        
        # 添加标题（已移除文本）
        image_title = QLabel("")
        image_title.setStyleSheet("padding: 0px;")
        image_title.setAlignment(Qt.AlignCenter)
        
        right_sidebar_layout.addSpacing(10)

        comm_group = QGroupBox("📡 无人机通信监控")
        comm_group.setStyleSheet("""
            QGroupBox {
                color: #2ECC71;
                font-size: 14pt;
                font-weight: bold;
                border: 2px solid #2ECC71;
                border-radius: 10px;
                padding: 10px;
                margin-top: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(46, 204, 113, 0.12),
                    stop:1 rgba(26, 32, 44, 0.85));
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                background-color: #1E2330;
                border-radius: 4px;
            }
        """)
        comm_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        comm_layout = QVBoxLayout(comm_group)
        comm_layout.setContentsMargins(6, 10, 6, 6)
        self.comm_monitor_text = QTextEdit()
        self.comm_monitor_text.setReadOnly(True)
        self.comm_monitor_text.setMinimumHeight(168)
        self.comm_monitor_text.setMaximumHeight(300)
        self.comm_monitor_text.setHtml(
            "<p style='color:#BDC3C7;font-size:13px;margin:6px;'>正在连接，请稍候…</p>"
        )
        self.comm_monitor_text.setStyleSheet("""
            QTextEdit {
                background-color: #1A202C;
                color: #ECF0F1;
                border: 1px solid rgba(46, 204, 113, 0.45);
                border-radius: 8px;
                font-family: "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", sans-serif;
                font-size: 12pt;
                padding: 6px;
            }
        """)
        comm_layout.addWidget(self.comm_monitor_text)
        right_sidebar_layout.addWidget(comm_group, 2)

        warn_group = QGroupBox("⚠️ 避障警告")
        warn_group.setStyleSheet("""
            QGroupBox {
                color: #E74C3C;
                font-size: 14pt;
                font-weight: bold;
                border: 2px solid #E74C3C;
                border-radius: 10px;
                padding: 10px;
                margin-top: 10px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(231, 76, 60, 0.12),
                    stop:1 rgba(26, 32, 44, 0.85));
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                background-color: #1E2330;
                border-radius: 4px;
            }
        """)
        warn_layout = QVBoxLayout(warn_group)
        warn_layout.setContentsMargins(6, 10, 6, 6)
        self.obstacle_warning_label = QLabel(
            "<div style='font-size:12pt;color:#BDC3C7;padding:10px;line-height:1.45;'>"
            "正在等待传感器数据…"
            "</div>"
        )
        self.obstacle_warning_label.setWordWrap(True)
        self.obstacle_warning_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.obstacle_warning_label.setMinimumHeight(88)
        self.obstacle_warning_label.setStyleSheet(
            "background-color: #1A202C; border-radius: 6px; border: 1px solid rgba(231, 76, 60, 0.35);"
        )
        warn_layout.addWidget(self.obstacle_warning_label)
        right_sidebar_layout.addWidget(warn_group, 1)

        # 在底部添加图像显示区域和控制按钮
        image_display_container = QWidget()
        image_display_layout = QVBoxLayout(image_display_container)
        image_display_layout.setContentsMargins(0, 0, 0, 0)
        image_display_layout.setSpacing(0)  # 去除组件间距

        # 创建图像显示组 - 现代化卡片设计
        image_group = QGroupBox("📷 实时图像")
        image_group.setStyleSheet("""
            QGroupBox {
                color: #3498DB;
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #3498DB;
                border-radius: 8px;
                padding: 8px;
                margin-top: 15px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(52, 152, 219, 0.1),
                    stop:1 rgba(26, 32, 44, 0.8));
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                background-color: #1E2330;
                border-radius: 4px;
            }
        """)
        image_group_layout = QVBoxLayout(image_group)
        image_group_layout.setContentsMargins(0, 0, 0, 0)  # 进一步减少内边距
        image_group_layout.setSpacing(0)  # 进一步减少组件间距

        # RGB / 深度图 标签式切换（与参考界面右下角一致）
        image_mode_bar = QWidget()
        image_mode_layout = QHBoxLayout(image_mode_bar)
        image_mode_layout.setContentsMargins(4, 4, 4, 2)
        image_mode_layout.setSpacing(6)
        tab_style = """
            QPushButton {
                background-color: #2C3E50;
                color: #ECF0F1;
                border: 1px solid #3498DB;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:checked {
                background-color: #3498DB;
                color: #1A202C;
            }
            QPushButton:hover:!checked {
                background-color: #34495E;
            }
        """
        self.rgb_button = QPushButton("RGB 图像")
        self.depth_button = QPushButton("深度图")
        self.rgb_button.setCheckable(True)
        self.depth_button.setCheckable(True)
        self.rgb_button.setCursor(Qt.PointingHandCursor)
        self.depth_button.setCursor(Qt.PointingHandCursor)
        self.rgb_button.setStyleSheet(tab_style)
        self.depth_button.setStyleSheet(tab_style)
        self.rgb_button.setChecked(True)
        self._image_mode_button_group = QButtonGroup(self)
        self._image_mode_button_group.setExclusive(True)
        self._image_mode_button_group.addButton(self.rgb_button)
        self._image_mode_button_group.addButton(self.depth_button)
        self.rgb_button.clicked.connect(self.switchToRGBImage)
        self.depth_button.clicked.connect(self.switchToDepthImage)
        image_mode_layout.addWidget(self.rgb_button)
        image_mode_layout.addWidget(self.depth_button)
        image_group_layout.addWidget(image_mode_bar)

        # 创建图像显示容器
        image_frame = QFrame()
        image_frame.setFrameShape(QFrame.StyledPanel)
        image_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(44, 62, 80, 0.9),
                    stop:1 rgba(26, 32, 44, 0.9));
                border-radius: 6px;
                border: 1px solid rgba(52, 152, 219, 0.3);
            }
        """)
        image_frame_layout = QVBoxLayout(image_frame)
        image_frame_layout.setContentsMargins(2, 2, 2, 2)  # 进一步减少内边距
        image_frame_layout.setSpacing(0)

        # 图像显示标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(self.adaptive_image_width - 16, self.adaptive_image_height - 10)  # 调整尺寸适应新布局
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #1A202C;
                border: 1px solid #3498DB;
                border-radius: 4px;
                color: #FFFFFF;
                font-size: 10pt;
            }
        """)
        self.image_label.setText("""
            <div style='
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                width: 100%;
                font-size: 16pt;
                color: #3498DB;
                text-align: center;
                font-weight: bold;
            '>
                等待图像...
            </div>
        """)
        self.image_label.setScaledContents(True)  # 启用内容缩放
        image_frame_layout.addWidget(self.image_label, 0, Qt.AlignCenter)

        image_group_layout.addWidget(image_frame)

        # 添加图像组到图像显示布局
        image_display_layout.addWidget(image_group)
        
        # 添加图像显示容器，使用拉伸系数1
        right_sidebar_layout.addWidget(image_display_container, 1)
        
        self.current_image_mode = "rgb"

        # 深度图像数据
        self.depth_image = None

        # 添加右侧栏到主分割器
        self.main_splitter.addWidget(self.right_sidebar)
        
        # 设置分割器手柄宽度
        self.main_splitter.setHandleWidth(3)  # 设置较小的分割器手柄宽度
        self.main_splitter.setChildrenCollapsible(False)  # 防止子部件被完全折叠
        
        # 设置自适应的分割器初始比例
        self.setupAdaptiveSplitterSizes()

        # 设置窗口最小尺寸，确保在小屏幕上也能正常显示
        min_width = self.adaptive_left_width + self.adaptive_right_width + 500  # 最小中间区域500px
        min_height = 600  # 最小高度600px
        self.setMinimumSize(min_width, min_height)

        # 禁止分割器伸缩右侧栏
        self.main_splitter.setStretchFactor(0, 0)  # 左侧栏不自动拉伸
        self.main_splitter.setStretchFactor(1, 0)  # 左侧控制按钮不自动拉伸
        self.main_splitter.setStretchFactor(2, 1)  # 中间RViz区域自动拉伸
        self.main_splitter.setStretchFactor(3, 0)  # 右侧控制按钮不自动拉伸
        self.main_splitter.setStretchFactor(4, 0)  # 右侧栏不自动拉伸
        
        # 初始分割比例将在setupAdaptiveSplitterSizes中设置
        
        main_layout.addWidget(self.main_splitter)
        
        # 创建底部状态栏，包含位置和时间信息
        status_bar = QStatusBar()
        status_bar.setStyleSheet("background-color: #1A202C; padding: 2px;")
        status_bar.setMaximumHeight(25)  # 限制底部状态栏高度
        
        # 创建位置显示标签(左侧)
        self.position_label = QLabel("Position: (X:0.0000 Y:0.0000 Z:0.0000)")
        self.position_label.setStyleSheet("color: #3498DB; padding-left: 15px; font-weight: bold;")
        self.position_label.setMinimumWidth(300)  # 设置最小宽度确保显示完整
        status_bar.addWidget(self.position_label)
        
        # 添加占位符，使FPS和时间显示在右侧
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_bar.addWidget(spacer)
        
        # 创建帧率标签(英文)
        self.frame_rate_label = QLabel("FPS: 0.00")
        self.frame_rate_label.setStyleSheet("color: #3498DB; padding-right: 15px;")
        status_bar.addPermanentWidget(self.frame_rate_label)
        
        # 创建ROS时间显示(英文)
        self.ros_time_label = QLabel("Time: 0.0000")
        self.ros_time_label.setStyleSheet("color: #3498DB; padding-right: 50px;")  # 增加右侧内边距，避免与右侧按钮重叠
        status_bar.addPermanentWidget(self.ros_time_label)
        
        # 注意：定时器已在_init_timers中统一初始化，这里不再重复创建

        self.last_frame_time = time.time()

        # 速度数据
        self.speed = 0
        self.linear_speed = 0
        self.angular_speed = 0

        # 初始状态设置为未连接
        if hasattr(self, 'connection_label'):
            self.connection_label.setText("未连接")
            # 不设置字体大小，保持卡片的原始字体设置
            self.connection_label.setStyleSheet("""
                QLabel {
                    color: #E74C3C;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 0px;
                    margin: 0px;
                }
            """)
        if hasattr(self, 'mode_label'):
            self.mode_label.setText("未连接")
        
        main_layout.addWidget(status_bar)
        
        # 设置布局的拉伸因子，让中间的RViz显示区域占据大部分空间
        main_layout.setStretch(1, 10)  # 中间部分(splitter)占据更多空间
        main_layout.setStretch(0, 1)   # 标题栏占据较少空间
        main_layout.setStretch(2, 1)   # 底部栏占据较少空间

        # QMainWindow已经在初始化时设置了central_widget，不需要再调用setLayout
        
        # 注意：延迟初始化已在_init_timers中处理，避免重复
        
        # 初始化话题订阅器变量，但不启动订阅（在__init__末尾会自动订阅）
        self.topic_subscriber = None
        
        # 用于存储小球截图的字典 {ball_id: {"path": 文件路径, "timestamp": 时间戳}}
        # 注意：不再存储图像数据，只存储文件路径以避免内存问题
        
        # 截图目录已在初始化时设置，这里不需要重复设置

    def calculateAdaptiveSizes(self):
        """根据屏幕分辨率计算自适应尺寸"""
        # 基准分辨率为1920x1080
        base_width = 1920
        base_height = 1080

        # 计算自适应的侧边栏宽度 - 使用固定比例而不是绝对值
        # 左侧栏占屏幕宽度的比例：小屏幕20%，中等屏幕22%，大屏幕25%
        # 右侧栏占屏幕宽度的比例：小屏幕25%，中等屏幕28%，大屏幕30%

        if self.screen_width <= 1366:  # 小屏幕 (1366x768等)
            left_ratio = 0.20
            right_ratio = 0.25
        elif self.screen_width <= 1920:  # 中等屏幕 (1920x1080)
            left_ratio = 0.22
            right_ratio = 0.28
        else:  # 大屏幕 (2K, 4K等)
            left_ratio = 0.25
            right_ratio = 0.30

        # 计算侧边栏宽度，设置合理的最小值和最大值
        self.adaptive_left_width = max(280, min(600, int(self.screen_width * left_ratio)))
        self.adaptive_right_width = max(350, min(800, int(self.screen_width * right_ratio)))

        # 初始化图像尺寸变量，这些将在updateImageSizes中动态计算
        self.adaptive_image_width = 320
        self.adaptive_image_height = 240

        print(f"自适应尺寸 - 左侧栏: {self.adaptive_left_width}px, 右侧栏: {self.adaptive_right_width}px")

    def updateImageSizes(self):
        """动态更新图像尺寸以适应右侧栏宽度"""
        if not hasattr(self, 'right_sidebar'):
            return

        # 获取右侧栏的实际宽度
        actual_right_width = self.right_sidebar.width() if self.right_sidebar.isVisible() else self.adaptive_right_width

        # 计算图像区域可用宽度，留出边距
        margin = 20  # 减少边距以更好利用空间
        available_width = actual_right_width - margin

        # 确保最小宽度
        min_image_width = 240
        available_width = max(min_image_width, available_width)

        # 保持640:480的宽高比 (4:3)
        self.adaptive_image_width = available_width
        self.adaptive_image_height = int(available_width * 480 / 640)  # 640:480比例

        # 检查总高度是否合理（仅实时图像区域，无鸟瞰图）
        available_height = self.screen_height - 300  # 预留300px给其他UI元素
        total_image_height = self.adaptive_image_height + 120

        if total_image_height > available_height:
            # 按比例缩小
            scale_factor = available_height / total_image_height
            self.adaptive_image_height = int(self.adaptive_image_height * scale_factor)
            # 根据高度重新计算宽度，保持640:480比例
            self.adaptive_image_width = int(self.adaptive_image_height * 640 / 480)

        # 更新图像组件尺寸
        if hasattr(self, 'image_label'):
            self.image_label.setFixedSize(self.adaptive_image_width, self.adaptive_image_height)
        if hasattr(self, 'rgb_button') and hasattr(self, 'depth_button'):
            button_width = self.adaptive_image_width // 2
            # 更新按钮样式以适应新宽度
            self.updateButtonStyles(button_width)


        print(f"更新图像尺寸 - 图像: {self.adaptive_image_width}x{self.adaptive_image_height}px")



    def updateButtonStyles(self, button_width):
        """更新按钮样式以适应新宽度 - 现在使用内联样式，此函数保留以兼容性"""
        # 按钮样式现在在创建时直接设置，无需动态更新
        pass

    def setupAdaptiveSplitterSizes(self):
        """设置自适应的分割器尺寸"""
        # 使用定时器延迟设置，确保窗口已经完全初始化
        QTimer.singleShot(100, self._setAdaptiveSplitterSizes)

    def _setAdaptiveSplitterSizes(self):
        """实际设置分割器尺寸的方法"""
        try:
            # 获取当前窗口宽度，如果窗口还没有显示，使用屏幕宽度
            current_width = self.width() if self.isVisible() else self.screen_width

            # 计算各部分的宽度
            control_button_width = 20  # 控制按钮宽度
            total_control_width = control_button_width * 2  # 两个控制按钮

            # 检查侧边栏当前是否可见
            left_visible = hasattr(self, 'left_sidebar') and self.left_sidebar.isVisible()
            right_visible = hasattr(self, 'right_sidebar') and self.right_sidebar.isVisible()

            # 根据侧边栏可见性计算实际使用的宽度
            actual_left_width = self.adaptive_left_width if left_visible else 0
            actual_right_width = self.adaptive_right_width if right_visible else 0

            # 计算中间RViz区域的宽度
            remaining_width = current_width - actual_left_width - actual_right_width - total_control_width

            # 确保中间区域有最小宽度
            min_center_width = 400
            if remaining_width < min_center_width:
                # 如果空间不足，按比例缩小侧边栏
                total_sidebar_width = actual_left_width + actual_right_width
                available_sidebar_width = current_width - min_center_width - total_control_width

                if available_sidebar_width > 0 and total_sidebar_width > 0:
                    scale_factor = available_sidebar_width / total_sidebar_width
                    adjusted_left_width = max(200 if left_visible else 0, int(actual_left_width * scale_factor))
                    adjusted_right_width = max(300 if right_visible else 0, int(actual_right_width * scale_factor))
                    remaining_width = current_width - adjusted_left_width - adjusted_right_width - total_control_width
                else:
                    # 极端情况，使用最小值
                    adjusted_left_width = 200 if left_visible else 0
                    adjusted_right_width = 300 if right_visible else 0
                    remaining_width = max(min_center_width, current_width - adjusted_left_width - adjusted_right_width - total_control_width)
            else:
                adjusted_left_width = actual_left_width
                adjusted_right_width = actual_right_width

            # 设置分割器尺寸
            sizes = [adjusted_left_width, control_button_width, remaining_width, control_button_width, adjusted_right_width]

            # 只有在尺寸真正改变时才设置，避免不必要的布局调整
            current_sizes = self.main_splitter.sizes()
            if current_sizes != sizes:
                self.main_splitter.setSizes(sizes)
                print(f"分割器尺寸设置: 左侧栏={adjusted_left_width}px, 中间={remaining_width}px, 右侧栏={adjusted_right_width}px")

        except Exception as e:
            print(f"设置分割器尺寸时出错: {str(e)}")
    
    def createStatusCards(self, parent_layout):
        """创建现代化的状态卡片"""
        # 第一行状态卡片
        row1_container = QWidget()
        row1_layout = QHBoxLayout(row1_container)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(3)  # 进一步减少卡片间距

        # 飞行模式卡片 - 使用compact模式
        mode_card = self.createStatusCard("飞行模式", "MANUAL", "#3498DB", compact=True)
        self.mode_label = mode_card.findChild(QLabel, "value_label")
        row1_layout.addWidget(mode_card)

        # 连接状态卡片 - 使用compact模式
        connection_card = self.createStatusCard("连接状态", "已连接", "#2ECC71", compact=True)
        self.connection_label = connection_card.findChild(QLabel, "value_label")
        row1_layout.addWidget(connection_card)

        parent_layout.addWidget(row1_container)

        row1b_container = QWidget()
        row1b_layout = QHBoxLayout(row1b_container)
        row1b_layout.setContentsMargins(0, 0, 0, 0)
        row1b_layout.setSpacing(3)
        takeoff_card = self.createStatusCard("起飞状态", "未知", "#16A085", compact=True)
        self.takeoff_state_label = takeoff_card.findChild(QLabel, "value_label")
        row1b_layout.addWidget(takeoff_card, 2)
        op_card = self.createStatusCard("当前任务", "未启动", "#9B59B6", compact=True)
        self.operational_state_label = op_card.findChild(QLabel, "value_label")
        row1b_layout.addWidget(op_card, 3)
        if self.operational_state_label:
            self.operational_state_label.setStyleSheet(
                """
                QLabel {
                    color: #D7BDE2;
                    font-size: 13pt;
                    font-weight: bold;
                    background: transparent;
                    border: none;
                    padding: 2px 4px;
                    margin: 0px;
                }
                """
            )
        parent_layout.addWidget(row1b_container)

        # 第二行状态卡片
        row2_container = QWidget()
        row2_layout = QHBoxLayout(row2_container)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(3)  # 进一步减少卡片间距

        # 飞行高度卡片 - 使用compact模式
        altitude_card = self.createStatusCard("飞行高度", "0.0000 m", "#E67E22", compact=True)
        self.altitude_label = altitude_card.findChild(QLabel, "value_label")
        row2_layout.addWidget(altitude_card)

        # 地面速度卡片 - 使用compact模式
        speed_card = self.createStatusCard("地面速度", "0.0000 m/s", "#9B59B6", compact=True)
        self.ground_speed_label = speed_card.findChild(QLabel, "value_label")
        row2_layout.addWidget(speed_card)

        parent_layout.addWidget(row2_container)

        # 第三行状态卡片 - 姿态信息
        row3_container = QWidget()
        row3_layout = QHBoxLayout(row3_container)
        row3_layout.setContentsMargins(0, 0, 0, 0)
        row3_layout.setSpacing(3)  # 进一步减少卡片间距

        # 俯仰角卡片
        pitch_card = self.createStatusCard("俯仰角", "0.00°", "#1ABC9C", compact=True)
        self.pitch_label = pitch_card.findChild(QLabel, "value_label")
        row3_layout.addWidget(pitch_card)

        # 滚转角卡片
        roll_card = self.createStatusCard("滚转角", "0.00°", "#F39C12", compact=True)
        self.roll_label = roll_card.findChild(QLabel, "value_label")
        row3_layout.addWidget(roll_card)

        # 偏航角卡片
        yaw_card = self.createStatusCard("偏航角", "0.00°", "#E74C3C", compact=True)
        self.yaw_label = yaw_card.findChild(QLabel, "value_label")
        row3_layout.addWidget(yaw_card)

        parent_layout.addWidget(row3_container)

        # 第四行 - 电池状态卡片（全宽）
        battery_card = self.createStatusCard("电池状态", f"{self.battery_percentage:.1f}%", "#27AE60", full_width=True)
        self.battery_status_label = battery_card.findChild(QLabel, "value_label")
        parent_layout.addWidget(battery_card)

    def createStatusCard(self, title, value, color, compact=False, full_width=False):
        """创建单个状态卡片"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)

        # 根据是否紧凑模式和全宽模式设置不同的样式
        if compact:
            card.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.08),
                        stop:1 rgba(0, 0, 0, 0.12));
                    border: 1px solid {color};
                    border-radius: 6px;
                    margin: 0px;
                }}
                QFrame:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.12),
                        stop:1 rgba(0, 0, 0, 0.08));
                    border: 2px solid {color};
                }}
            """)
            # 根据屏幕分辨率调整高度，增加高度以更好填充空间
            if hasattr(self, 'screen_height') and self.screen_height <= 768:  # 1K分辨率或更小
                card.setMinimumHeight(60)
                card.setMaximumHeight(60)
            else:
                card.setMinimumHeight(70)
                card.setMaximumHeight(70)
        else:
            card.setStyleSheet(f"""
                QFrame {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.08),
                        stop:1 rgba(0, 0, 0, 0.12));
                    border: 1px solid {color};
                    border-radius: 10px;
                    margin: 1px;
                }}
                QFrame:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(255, 255, 255, 0.12),
                        stop:1 rgba(0, 0, 0, 0.08));
                    border: 2px solid {color};
                }}
            """)
            if full_width:
                card.setMinimumHeight(80)  # 增加全宽卡片高度
                card.setMaximumHeight(80)
            else:
                card.setMinimumHeight(90)  # 增加普通卡片高度
                card.setMaximumHeight(90)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)  # 去掉内边距
        layout.setSpacing(0)  # 去掉间距

        # 标题标签 - 占50%高度
        title_label = QLabel(title)

        # 根据屏幕分辨率和compact模式调整标题字体大小
        if compact:
            if hasattr(self, 'screen_height') and self.screen_height <= 768:  # 1K分辨率或更小
                title_font_size = '8pt'
            else:
                title_font_size = '9pt'
        else:
            title_font_size = '11pt'

        title_label.setStyleSheet(f"""
            QLabel {{
                color: #FFFFFF;
                font-size: {title_font_size};
                font-weight: normal;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
        """)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(title_label, 1)  # 拉伸因子1，占50%

        # 数值标签 - 占50%高度
        value_label = QLabel(value)
        value_label.setObjectName("value_label")  # 设置对象名以便查找

        # 根据屏幕分辨率和compact模式调整字体大小
        if compact:
            if hasattr(self, 'screen_height') and self.screen_height <= 768:  # 1K分辨率或更小
                font_size = '10pt'
            else:
                font_size = '11pt'
        else:
            font_size = '14pt'

        value_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: {font_size};
                font-weight: bold;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }}
        """)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(value_label, 1)  # 拉伸因子1，占50%

        return card

    def _refresh_takeoff_and_operational_labels(self):
        """根据 MAVROS state、里程计高度与仿真链路刷新「起飞状态」「当前状态」。"""
        try:
            if not hasattr(self, "takeoff_state_label") or not self.takeoff_state_label:
                return
            alt = self._last_altitude_m
            m = self._last_mavros_status or {}
            armed = bool(m.get("armed"))
            connected = bool(m.get("connected"))
            mode = (m.get("mode") or "").strip()
            guided = bool(m.get("guided"))

            sim_link = bool(
                self.topic_subscriber
                and (
                    self.topic_subscriber.is_topic_active("odometry")
                    or self.topic_subscriber.is_topic_active("camera")
                )
            )
            has_mavros_status = bool(self.topics_with_data.get("status")) and bool(m)

            takeoff_txt = "未知"
            if alt is None and not sim_link:
                takeoff_txt = "等待位姿"
            elif has_mavros_status:
                if not armed:
                    takeoff_txt = "未解锁·地面"
                elif alt is None:
                    takeoff_txt = "已解锁（无高度）"
                elif alt < 0.35:
                    takeoff_txt = "已解锁·近地"
                else:
                    takeoff_txt = "已起飞"
            elif sim_link and alt is not None:
                takeoff_txt = "仿真·空中" if alt >= 0.35 else "仿真·近地/地面"
            elif sim_link:
                takeoff_txt = "仿真链路（无高度）"
            else:
                takeoff_txt = "等待数据"

            self.takeoff_state_label.setText(takeoff_txt)
            self._update_mission_status_label()
        except Exception:
            pass

    def _is_stack_running(self):
        procs = getattr(self, "processes", None) or {}
        return any(p is not None for p in procs.values())

    def _set_mission_phase(self, phase):
        """任务阶段：idle / launching / returning / waypoint / stopped"""
        prev = getattr(self, "_mission_phase", "idle")
        self._mission_phase = phase or "idle"
        self._update_mission_status_label()

        # 栈从 launching 进入 idle（启动完成）或完全停止：清 hold-goal 跳变防护，避免新会话被旧位姿卡住
        try:
            if phase == "stopped" or (phase == "idle" and prev == "launching"):
                setattr(self, "_hold_goal_last_accepted_xyz", None)
        except Exception:
            pass

        try:
            ht = getattr(self, "_idle_hold_timer", None)
            if ht is not None:
                if self._mission_phase != "idle":
                    ht.stop()
                elif not self._nav_behavior_bool(
                    "/myviz/publish_hold_goal_on_idle",
                    "auto_publish_hold_goal_on_idle",
                    False,
                ):
                    ht.stop()
                else:
                    period = float(rospy.get_param("/myviz/idle_hold_goal_period_sec", 1.5))
                    if period <= 0:
                        ht.stop()
                    else:
                        ht.setInterval(max(500, int(1000 * period)))
                        if self._is_stack_running() and not ht.isActive():
                            ht.start()
        except Exception:
            pass

        # 进入待机时可选立刻刷一次 hold（与 auto_publish_hold_goal_on_idle 一致）
        if self._mission_phase == "idle" and prev != "idle":
            try:
                if self._nav_behavior_bool(
                    "/myviz/publish_hold_goal_on_idle",
                    "auto_publish_hold_goal_on_idle",
                    False,
                ):
                    QTimer.singleShot(400, self._idle_refresh_navigation_goal)
            except Exception:
                pass

    def _update_mission_status_label(self):
        """「当前任务」：返航 / 前往目标 / 待机 / 手动 等（不展示底层链路细节）。"""
        try:
            if not hasattr(self, "operational_state_label") or not self.operational_state_label:
                return
            ph = getattr(self, "_mission_phase", "idle")
            manual = getattr(self, "_manual_control_page", False)
            running = self._is_stack_running()

            if ph == "launching":
                text = "正在启动系统"
            elif ph == "returning":
                text = "返航中"
            elif ph == "waypoint":
                text = "前往目标点"
            elif ph == "stopped":
                text = "已停止"
            elif manual and running:
                text = "手动操控"
            elif running:
                text = "待机"
            else:
                text = "未启动"
            self.operational_state_label.setText(text)
        except Exception:
            pass

    def _on_control_center_page_changed(self, page_index):
        self._manual_control_page = bool(page_index == 1)
        self._update_mission_status_label()

    def toggleDisplayPanel(self):
        """此方法已不再使用，保留以避免可能的引用错误"""
        self.toggleRVizDisplayPanel()
    
    def toggleLeftSidebarPinned(self):
        """切换左侧栏的固定状态"""
        if self.left_sidebar_pinned:
            # 如果当前是固定状态，解除固定并隐藏
            self.left_sidebar_pinned = False
            self.toggleSidebar(hide=True, animate=True)
            # 更新按钮样式，恢复正常
            self.toggle_sidebar_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1A202C;  /* 与周围颜色相协调 */
                    border: none;
                    border-radius: 0;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: #3498DB;  /* 蓝色悬停效果 */
                }
                QPushButton:pressed {
                    background-color: #2980B9;  /* 按下效果 */
                }
            """)
        else:
            # 如果当前非固定，切换为固定状态并显示
            self.left_sidebar_pinned = True
            self.toggleSidebar(hide=False, animate=True)
            # 更新按钮样式，显示固定状态
            self.toggle_sidebar_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498DB;  /* 蓝色背景表示已固定 */
                    border: none;
                    border-radius: 0;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #2980B9;
                }
            """)
    
    def toggleSidebar(self, hide=None, animate=False):
        """显示或隐藏侧边栏
        
        参数:
            hide: 是否隐藏侧边栏。如果为None，则切换当前状态
            animate: 是否使用动画效果
        """
        # 如果指定了hide参数，则根据参数决定是否隐藏
        should_hide = hide if hide is not None else self.sidebar_expanded
        
        # 如果已经在动画中，则不重复触发
        if hasattr(self, 'sidebar_animation') and self.sidebar_animation.state() == QPropertyAnimation.Running:
            return

        # 清理之前的动画对象
        if hasattr(self, 'sidebar_animation'):
            try:
                self.sidebar_animation.finished.disconnect()
                self.sidebar_animation.valueChanged.disconnect()
                self.sidebar_animation.stop()
                self.sidebar_animation.deleteLater()
            except:
                pass  # 忽略断开连接时的错误

        # 打印调试信息
        # print(f"切换侧边栏: hide={should_hide}, animate={animate}, 当前状态={self.sidebar_expanded}")

        if should_hide:
            # 隐藏侧边栏
            if animate:
                # 使用动画效果
                self.sidebar_animation = QPropertyAnimation(self.left_sidebar, b"maximumWidth")
                self.sidebar_animation.setDuration(200)  # 动画持续时间200ms
                current_width = self.left_sidebar.width()
                self.sidebar_animation.setStartValue(current_width)
                self.sidebar_animation.setEndValue(0)
                self.sidebar_animation.setEasingCurve(QEasingCurve.InOutQuad)

                # 确保侧边栏可见性正确
                self.left_sidebar.setVisible(True)

                # 动画结束后更新状态
                self.sidebar_animation.finished.connect(lambda: self.finishSidebarAnimation(False))

                # 动画过程中定期更新悬浮窗口位置
                self.sidebar_animation.valueChanged.connect(lambda: self._update_overlay_positions())

                # 启动动画
                self.sidebar_animation.start()
                
                # 立即更新状态，但不隐藏侧边栏（等动画完成）
                self.updateSidebarState(False)
                
                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                self.main_splitter.setSizes([0, 20, sizes[0] + sizes[2]])
            else:
                # 直接隐藏
                self.left_sidebar.setMaximumWidth(0)
                self.left_sidebar.setMinimumWidth(0)
                self.left_sidebar.setVisible(False)
                self.updateSidebarState(False)
                
                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                self.main_splitter.setSizes([0, 20, sizes[0] + sizes[2]])

                # 立即更新悬浮窗口位置
                QTimer.singleShot(50, self._update_overlay_positions)
        else:
            # 显示侧边栏
            if animate:
                # 清理之前的动画对象（如果存在）
                if hasattr(self, 'sidebar_animation'):
                    try:
                        self.sidebar_animation.finished.disconnect()
                        self.sidebar_animation.valueChanged.disconnect()
                        self.sidebar_animation.stop()
                        self.sidebar_animation.deleteLater()
                    except:
                        pass  # 忽略断开连接时的错误

                # 先设置最大宽度，以便动画可以工作
                self.left_sidebar.setMaximumWidth(self.adaptive_left_width)
                self.left_sidebar.setMinimumWidth(0)
                self.left_sidebar.setVisible(True)

                # 使用动画效果
                self.sidebar_animation = QPropertyAnimation(self.left_sidebar, b"maximumWidth")
                self.sidebar_animation.setDuration(200)  # 动画持续时间200ms
                self.sidebar_animation.setStartValue(0)
                self.sidebar_animation.setEndValue(self.adaptive_left_width)
                self.sidebar_animation.setEasingCurve(QEasingCurve.InOutQuad)

                # 动画结束后更新状态
                self.sidebar_animation.finished.connect(lambda: self.finishSidebarAnimation(True))

                # 动画过程中定期更新悬浮窗口位置
                self.sidebar_animation.valueChanged.connect(lambda: self._update_overlay_positions())

                # 启动动画
                self.sidebar_animation.start()

                # 立即更新状态
                self.updateSidebarState(True)

                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                self.main_splitter.setSizes([self.adaptive_left_width, 20, sizes[2] - self.adaptive_left_width])
            else:
                # 直接显示
                self.left_sidebar.setFixedWidth(self.adaptive_left_width)  # 使用自适应宽度
                self.left_sidebar.setVisible(True)
                self.updateSidebarState(True)

                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                self.main_splitter.setSizes([self.adaptive_left_width, 20, sizes[2] - self.adaptive_left_width])

                # 立即更新悬浮窗口位置
                QTimer.singleShot(50, self._update_overlay_positions)
    
    def finishSidebarAnimation(self, expanded):
        """动画结束后的处理

        参数:
            expanded: 是否展开
        """
        if not expanded:
            # 动画结束后，如果是隐藏状态，则设置不可见以减少资源占用
            self.left_sidebar.setVisible(False)
        else:
            # 如果是显示状态，确保最小宽度也设置好
            self.left_sidebar.setMinimumWidth(self.adaptive_left_width)

        # 动画完成后立即更新悬浮窗口位置，使用多次延迟更新确保位置正确
        self._update_overlay_positions()
        QTimer.singleShot(50, self._update_overlay_positions)
        QTimer.singleShot(100, self._update_overlay_positions)
        QTimer.singleShot(200, self._update_overlay_positions)
    
    def updateSidebarState(self, expanded):
        """更新侧边栏状态

        参数:
            expanded: 是否展开
        """
        self.sidebar_expanded = expanded
        self.toggle_sidebar_btn.setIcon(QIcon(":/images/icons/dropleft.svg" if expanded else ":/images/icons/dropright.svg"))
        self.toggle_sidebar_btn.style().unpolish(self.toggle_sidebar_btn)
        self.toggle_sidebar_btn.style().polish(self.toggle_sidebar_btn)

    def onTopButtonClick(self):
        self.switchToView("Top View")
        
    def onSideButtonClick(self):
        self.switchToView("Side View")
    
    def onFreeViewClick(self):
        self.onRvizViewFreeClick()

    @staticmethod
    def _rviz_saved_view_name_str(raw):
        if raw is None:
            return ""
        if isinstance(raw, (bytes, bytearray)):
            return raw.decode("utf-8", errors="ignore").strip()
        return str(raw).strip()

    def _switch_rviz_saved_view(self, view_name):
        try:
            want = self._rviz_saved_view_name_str(view_name)
            vm = self.manager.getViewManager()
            for i in range(vm.getNumViews()):
                got = self._rviz_saved_view_name_str(vm.getViewAt(i).getName())
                if got == want:
                    vm.setCurrentFrom(vm.getViewAt(i))
                    return True
        except Exception:
            pass
        return False

    def _apply_third_person_follow_view(self, frame):
        """不依赖 my_config 中是否保存「跟随无人机」：直接切到 ThirdPersonFollower 并设目标坐标系。"""
        try:
            vm = self.manager.getViewManager()
            vm.setCurrentViewControllerType("rviz/ThirdPersonFollower")
            vc = vm.getCurrent()
            if vc is None:
                return False
            f = (frame or "base_link").strip() or "base_link"
            for prop_name, val in (
                ("Target Frame", f),
                ("Distance", 10.0),
                ("Pitch", 0.45),
            ):
                try:
                    p = vc.subProp(prop_name)
                    if p is not None:
                        p.setValue(val)
                except Exception:
                    pass
            return True
        except Exception as ex:
            rospy.logdebug("ThirdPersonFollower: %s", ex)
            return False

    def onRvizViewFreeClick(self):
        """加载已保存的「自由视角」轨道相机（Orbit + Fixed Frame）。"""
        self._rviz_view_mode = "free"
        try:
            if hasattr(self, "rviz_view_free_btn"):
                self.rviz_view_free_btn.setChecked(True)
            if hasattr(self, "rviz_view_follow_btn"):
                self.rviz_view_follow_btn.setChecked(False)
        except Exception:
            pass
        if not self._switch_rviz_saved_view("自由视角"):
            try:
                self.manager.getViewManager().setCurrentViewControllerType("rviz/Orbit")
            except Exception:
                pass

    def onRvizViewFollowClick(self):
        """第三人称跟随：目标坐标系默认可通过 /myviz/rviz_follow_target_frame 修改（如 base_footprint）。"""
        self._rviz_view_mode = "follow"
        try:
            if hasattr(self, "rviz_view_free_btn"):
                self.rviz_view_free_btn.setChecked(False)
            if hasattr(self, "rviz_view_follow_btn"):
                self.rviz_view_follow_btn.setChecked(True)
        except Exception:
            pass
        frame = "base_link"
        try:
            frame = str(rospy.get_param("/myviz/rviz_follow_target_frame", "base_link") or "base_link").strip()
        except Exception:
            pass
        if self._apply_third_person_follow_view(frame):
            return
        if not self._switch_rviz_saved_view("跟随无人机"):
            rospy.logwarn_throttle(
                10.0,
                "无法切换到第三人称跟随视角（RViz ViewManager 不可用），请检查 RViz 是否正常加载",
            )

    def switchToView(self, view_name):
        if not self._switch_rviz_saved_view(view_name):
            print("Did not find view named %s." % view_name)

    def updateBatteryStatus(self, battery_data):
        """更新电池状态显示"""
        try:
            if not battery_data:
                return
                
            # 更新电池百分比和电压
            percentage = battery_data.get("percentage", 0.0) * 100  # 转换为百分比
            voltage = battery_data.get("voltage", 0.0)  # 获取电压值
            current = battery_data.get("current", 0.0)  # 获取电流值
            temperature = battery_data.get("temperature", 0.0)  # 获取温度
            
            # 保存数据以便在模拟模式下使用
            self.battery_percentage = percentage
            self.battery_voltage = voltage
            
            # 更新顶部状态栏电压显示
            if hasattr(self, 'voltage_label'):
                self.voltage_label.setText(f"{voltage:.2f} V")
            
            # 更新电池状态详情标签
            if hasattr(self, 'battery_status_label'):
                self.battery_status_label.setText(f"{percentage:.1f}% ({voltage:.2f}V)")
            
            # 根据电量选择对应图标并更新
            if hasattr(self, 'battery_icon_label'):
                if percentage <= 15:
                    icon_path = ":/images/icons/battery_0.svg"
                elif percentage <= 50:
                    icon_path = ":/images/icons/battery_50.svg"
                elif percentage <= 75:
                    icon_path = ":/images/icons/battery_75.svg"
                else:
                    icon_path = ":/images/icons/battery_100.svg"
                    
                # 更新电池图标
                self.battery_icon_label.setPixmap(QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            # 同时更新RViz悬浮窗口的电池和电压显示
            if hasattr(self, 'battery_value') and self.battery_value:
                try:
                    battery_formatted = f"{percentage:.1f}"
                    unit = self.battery_value.property("unit") or ""
                    self.battery_value.setText(f"{battery_formatted} {unit}".strip())
                except Exception as e:
                    pass  # 静默处理错误

            if hasattr(self, 'voltage_value') and self.voltage_value:
                try:
                    voltage_formatted = f"{voltage:.2f}"
                    unit = self.voltage_value.property("unit") or ""
                    self.voltage_value.setText(f"{voltage_formatted} {unit}".strip())
                except Exception as e:
                    pass  # 静默处理错误

            # 标记电池话题有数据
            self.topics_with_data["battery"] = True
            
        except Exception as e:
            print(f"更新电池状态显示时出错: {str(e)}")
    
    def updatePositionDisplay(self, odometry_data):
        """更新位置信息显示"""
        try:
            if not odometry_data:
                return
                
            # 获取位置数据
            pos_x = odometry_data["position"]["x"]
            pos_y = odometry_data["position"]["y"]
            pos_z = odometry_data["position"]["z"]
            self._last_altitude_m = float(pos_z)

            # 更新状态栏位置标签，保留四位小数
            if hasattr(self, 'position_label'):
                self.position_label.setText(f"Position: (X:{pos_x:.4f} Y:{pos_y:.4f} Z:{pos_z:.4f})")
            
            # 更新高度显示
            if hasattr(self, 'altitude_label'):
                self.altitude_label.setText(f"{pos_z:.4f} m")

            # 同时更新RViz悬浮窗口的高度显示
            if hasattr(self, 'altitude_value') and self.altitude_value:
                try:
                    height_formatted = f"{pos_z:.2f}"
                    unit = self.altitude_value.property("unit") or ""
                    self.altitude_value.setText(f"{height_formatted} {unit}".strip())
                except Exception as e:
                    pass  # 静默处理错误

            # 标记位置话题有数据
            self.topics_with_data["odometry"] = True

            self._refresh_takeoff_and_operational_labels()

            # 返航原点：未「栈就绪快照」前，仅在尚无 home 时用非零首包作临时值（拒绝 0,0,0 脏数据）
            if not getattr(self, "_home_position_locked", False):
                if getattr(self, "_home_position", None) is None:
                    try:
                        if (
                            abs(pos_x) + abs(pos_y) > 0.08
                            or pos_z > 0.18
                            or max(abs(pos_x), abs(pos_y)) > 0.25
                        ):
                            self._home_position = {
                                "x": float(pos_x),
                                "y": float(pos_y),
                                "z": max(0.45, float(pos_z)),
                            }
                    except Exception:
                        pass
            
        except Exception as e:
            print(f"更新位置显示时出错: {str(e)}")
    
    def updateVelocityDisplay(self, velocity_data):
        """更新速度信息显示"""
        try:
            if not velocity_data:
                return
                
            # 获取速度数据
            linear_x = velocity_data["linear"]["x"]
            linear_y = velocity_data["linear"]["y"]
            linear_z = velocity_data["linear"]["z"]
            
            # 获取角速度数据
            angular_x = velocity_data["angular"]["x"]
            angular_y = velocity_data["angular"]["y"]
            angular_z = velocity_data["angular"]["z"]
            
            # 计算合成速度(cm/s)
            speed = velocity_data.get("speed", 0.0)
            
            # 检查NaN值并替换为0
            if math.isnan(speed):
                speed = 0.0
                
            # 检查线性速度分量是否为NaN
            if math.isnan(linear_x):
                linear_x = 0.0
            if math.isnan(linear_y):
                linear_y = 0.0
            if math.isnan(linear_z):
                linear_z = 0.0
            
            # 保存速度数据以便在模拟模式下使用
            self.speed = int(speed)
            self.linear_speed = math.sqrt(linear_x**2 + linear_y**2)  # 地面速度
            
            # 更新地面速度标签
            if hasattr(self, 'ground_speed_label'):
                self.ground_speed_label.setText(f"{self.linear_speed:.4f} m/s")

            # 同时更新RViz悬浮窗口的速度显示
            if hasattr(self, 'speed_value') and self.speed_value:
                try:
                    speed_formatted = f"{self.linear_speed:.2f}"
                    unit = self.speed_value.property("unit") or ""
                    self.speed_value.setText(f"{speed_formatted} {unit}".strip())
                except Exception as e:
                    pass  # 静默处理错误

            # 标记速度话题有数据
            self.topics_with_data["velocity"] = True
        except Exception as e:
            print(f"更新速度显示时出错: {str(e)}")
    
    def updateStatusDisplay(self, status_data):
        """更新无人机状态信息显示"""
        try:
            if not status_data:
                return
                
            # 获取状态数据
            connected = status_data.get("connected", False)
            mode = status_data.get("mode", "")
            armed = status_data.get("armed", False)
            guided = status_data.get("guided", False)

            self._last_mavros_status = {
                "connected": connected,
                "armed": armed,
                "mode": mode or "",
                "guided": guided,
            }

            # 更新连接状态
            if hasattr(self, 'connection_label'):
                if connected:
                    self.connection_label.setText("已连接")
                    # 不设置字体大小，保持卡片的原始字体设置
                    self.connection_label.setStyleSheet("""
                        QLabel {
                            color: #2ECC71;
                            font-weight: bold;
                            background: transparent;
                            border: none;
                            padding: 0px;
                            margin: 0px;
                        }
                    """)
                else:
                    self.connection_label.setText("未连接")
                    # 不设置字体大小，保持卡片的原始字体设置
                    self.connection_label.setStyleSheet("""
                        QLabel {
                            color: #E74C3C;
                            font-weight: bold;
                            background: transparent;
                            border: none;
                            padding: 0px;
                            margin: 0px;
                        }
                    """)
            
            # 更新模式显示
            if hasattr(self, 'mode_label'):
                self.mode_label.setText(mode if mode else "UNKNOWN")

            # 同时更新RViz悬浮窗口的模式显示
            if hasattr(self, 'mode_value') and self.mode_value:
                try:
                    mode_text = mode if mode else "--"
                    self.mode_value.setText(mode_text)
                except Exception as e:
                    pass  # 静默处理错误

            # 标记话题有数据
            self.topics_with_data["status"] = True

            self._refresh_takeoff_and_operational_labels()

        except Exception as e:
            print(f"更新状态显示时出错: {str(e)}")

    def updateRCDisplay(self, rc_data):
        """更新遥控器状态显示"""
        try:
            if not rc_data:
                # 没有数据时显示未连接
                if hasattr(self, 'rc_value') and self.rc_value:
                    self.rc_value.setText("未连接")
                    self.rc_value.setStyleSheet("color: #E74C3C; font-weight: bold;")
                return

            # 检查是否有通道数据
            channels = rc_data.get('channels', [])
            if channels and len(channels) > 0:
                # 有通道数据，显示已连接
                if hasattr(self, 'rc_value') and self.rc_value:
                    self.rc_value.setText("已连接")
                    self.rc_value.setStyleSheet("color: #2ECC71; font-weight: bold;")
            else:
                # 没有通道数据，显示未连接
                if hasattr(self, 'rc_value') and self.rc_value:
                    self.rc_value.setText("未连接")
                    self.rc_value.setStyleSheet("color: #E74C3C; font-weight: bold;")

            # 标记遥控器话题有数据
            self.topics_with_data["rc_input"] = True

        except Exception as e:
            pass  # 静默处理错误

    def updateCameraImage(self, camera_data):
        """处理摄像头图像更新 - 优化版本，确保实时更新"""
        try:
            if not camera_data or camera_data["image"] is None:
                return

            # 验证图像数据的有效性
            image = camera_data["image"]
            if not isinstance(image, np.ndarray):
                print("图像数据不是numpy数组")
                return

            if image.size == 0:
                print("图像数据为空")
                return

            # 检查图像维度
            if len(image.shape) not in [2, 3]:
                print(f"不支持的图像维度: {image.shape}")
                return

            # 节流：相机常 20–30Hz，全量转 QPixmap 极耗 CPU；约 10–12Hz 刷新右侧预览
            now = time.monotonic()
            if now - self._last_right_rgb_emit < self._right_panel_image_min_dt:
                return
            self._last_right_rgb_emit = now
            self.camera_image = image.copy()

            if hasattr(self, 'image_label') and self.image_label:
                if self.current_image_mode == "rgb":
                    if pyqtSignal is not None and hasattr(self, 'image_update_signal'):
                        self.image_update_signal.emit()
                    else:
                        QTimer.singleShot(0, self.updateImageDisplay)

        except Exception as e:
            print(f"处理图像更新时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def updateImageDisplay(self):
        """更新图像显示 - 优化版本，增强调试和错误处理"""
        try:
            if not hasattr(self, 'image_label') or not self.image_label:
                print("警告: image_label不存在或为None")
                return

            if self.current_image_mode == "rgb":
                image_data = self.camera_image
            else:
                image_data = None
                if self.depth_image is not None:
                    image_data = self._process_depth_image(self.depth_image)

            if image_data is not None:
                pixmap = self._convert_cv_to_pixmap(image_data)
                if pixmap and not pixmap.isNull():
                    success = self._scale_and_set_pixmap('image_label', pixmap)
                    if success:
                        self.topics_with_data[self.current_image_mode] = True
                    else:
                        print("警告: 设置图像到标签失败")
                        self._show_image_placeholder()
                else:
                    print("警告: 图像转换为QPixmap失败")
                    self._show_image_placeholder()
            else:
                # print(f"没有可用的{self.current_image_mode}图像数据，显示占位符")
                self._show_image_placeholder()

        except Exception as e:
            print(f"更新图像显示时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'image_label'):
                try:
                    self.image_label.setText(f"图像显示错误: {str(e)}")
                except Exception as e2:
                    print(f"设置错误文本时也出错: {str(e2)}")

    def _process_depth_image(self, depth_image):
        """处理深度图像：分位拉伸 + CLAHE，使远近层次（柱顶/近地面）在伪彩色里更易分辨。"""
        cv_img = depth_image.copy()

        if len(cv_img.shape) == 2:  # 单通道深度图
            d = cv_img.astype(np.float32)
            if np.issubdtype(depth_image.dtype, np.integer):
                d = d * 0.001
            with np.errstate(invalid="ignore"):
                finite = np.isfinite(d)
                invalid = ~finite | (finite & ((d <= 0.02) | (d > 120.0)))
            valid = d[~invalid]
            if valid.size == 0:
                min_val, max_val, _, _ = cv2.minMaxLoc(cv_img)
                if max_val <= min_val:
                    return cv2.applyColorMap(np.zeros_like(cv_img, dtype=np.uint8), cv2.COLORMAP_TURBO)
                u8 = cv2.convertScaleAbs(
                    cv_img, alpha=255.0 / (max_val - min_val), beta=-min_val * 255.0 / (max_val - min_val)
                )
                clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
                u8 = clahe.apply(u8)
                cv_img = cv2.applyColorMap(u8, cv2.COLORMAP_TURBO)
            else:
                lo, hi = np.percentile(valid, [2.0, 98.0])
                if hi <= lo + 1e-4:
                    lo, hi = float(valid.min()), float(valid.max())
                d = np.clip(d, lo, hi)
                d[invalid] = lo
                u8 = ((d - lo) / (hi - lo + 1e-9) * 255.0).astype(np.uint8)
                clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
                u8 = clahe.apply(u8)
                cv_img = cv2.applyColorMap(u8, cv2.COLORMAP_TURBO)

        return cv_img

    def _convert_cv_to_pixmap(self, cv_image):
        """将OpenCV图像转换为QPixmap - 安全版本"""
        try:
            if cv_image is None:
                print("输入图像为None")
                return None

            # 检查图像是否有效
            if cv_image.size == 0:
                print("图像数据为空")
                return None

            # 检查图像数据类型
            if not isinstance(cv_image, np.ndarray):
                print(f"图像数据类型错误: {type(cv_image)}")
                return None

            # 确保图像数据是连续的
            if not cv_image.flags['C_CONTIGUOUS']:
                cv_image = np.ascontiguousarray(cv_image)

            # 确保是3通道BGR图像
            if len(cv_image.shape) == 3:
                height, width, channel = cv_image.shape
                if channel != 3:
                    print(f"不支持的通道数: {channel}")
                    return None
                # 将BGR转换为RGB格式
                try:
                    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
                except Exception as e:
                    print(f"BGR到RGB转换失败: {e}")
                    return None
            elif len(cv_image.shape) == 2:
                # 单通道图像转换为RGB
                try:
                    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_GRAY2RGB)
                    height, width, channel = rgb_image.shape
                except Exception as e:
                    print(f"灰度到RGB转换失败: {e}")
                    return None
            else:
                print(f"不支持的图像维度: {cv_image.shape}")
                return None

            # 确保转换后的图像数据是连续的
            if not rgb_image.flags['C_CONTIGUOUS']:
                rgb_image = np.ascontiguousarray(rgb_image)

            bytes_per_line = 3 * width

            # 创建QImage时使用copy确保数据安全
            try:
                q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)

                if q_image.isNull():
                    print("创建QImage失败")
                    return None

                # 创建QPixmap的副本以确保数据生命周期
                pixmap = QPixmap.fromImage(q_image.copy())

                if pixmap.isNull():
                    print("创建QPixmap失败")
                    return None

                return pixmap
            except Exception as e:
                print(f"创建QImage/QPixmap时出错: {e}")
                return None

        except Exception as e:
            print(f"图像转换错误: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _show_image_placeholder(self):
        """显示图像占位符"""
        if not self.topic_subscriber:
            text = "正在自动连接话题，请稍候..."
        else:
            if self.current_image_mode == "depth":
                if not self.topic_subscriber.is_topic_active("depth"):
                    text = "等待深度图像话题连接..."
                else:
                    text = "等待深度图数据..."
            elif not self.topic_subscriber.is_topic_active("camera"):
                text = "等待相机话题连接..."
            else:
                text = "等待相机画面数据..."

        # 使用更好的居中样式，确保文字在标签中完全居中
        self.image_label.setText(f"""
            <div style='
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                width: 100%;
                font-size: 16pt;
                color: #3498DB;
                text-align: center;
                font-weight: bold;
            '>
                {text}
            </div>
        """)
    
    def updateStatusBar(self):
        # 更新帧率（按整秒统计，避免每 100ms 刷标签且计数语义混乱）
        current_time = time.time()
        elapsed_time = current_time - self.last_frame_time
        if elapsed_time >= 1.0:
            hz = self._fps_ui_ticks / elapsed_time
            self.frame_rate_label.setText(f"节拍: {hz:.1f} Hz")
            self._fps_ui_ticks = 0
            self.last_frame_time = current_time

        # ROS 时间标签：降低 setText 频率
        if current_time - self._last_ros_time_label_wall >= 0.25:
            self._last_ros_time_label_wall = current_time
            if not rospy.is_shutdown():
                try:
                    if rospy.get_name() != "/unnamed":
                        now = rospy.Time.now()
                        ros_time = now.to_sec()
                        self.ros_time_label.setText(f"Time: {ros_time:.4f}")
                    else:
                        self.ros_time_label.setText(f"Time: {time.time():.4f}")
                except Exception as e:
                    print(f"获取ROS时间出错: {str(e)}")
                    self.ros_time_label.setText(f"Time: {time.time():.4f}")
        
        # 话题状态 tooltip 刷新：低频即可
        self._topic_status_cycle += 1
        if self._topic_status_cycle % 8 == 0:
            self.updateTopicStatus()
        
        # 如果没有话题订阅器，显示待启动状态
        if not self.topic_subscriber:
            # 显示静态状态信息而不使用模拟数据
            if hasattr(self, 'battery_icon_label'):
                self.battery_icon_label.setPixmap(QPixmap(":/images/icons/battery_0.svg").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            if hasattr(self, 'voltage_label'):
                self.voltage_label.setText("-- V")
            if hasattr(self, "battery_status_label"):
                self.battery_status_label.setText("暂无")
            
            if hasattr(self, 'position_label'):
                self.position_label.setText("Position: (等待话题连接)")
            
            if hasattr(self, 'altitude_label'):
                self.altitude_label.setText("-- m")
                
            if hasattr(self, 'ground_speed_label'):
                self.ground_speed_label.setText("-- m/s")

            # 当没有话题订阅器时，不使用模拟数据
            return
        
        # 如果话题订阅器存在但话题还未连接，显示等待连接状态而不是模拟数据
        fresh = lambda n, age=2.5: bool(self.topic_subscriber and self.topic_subscriber.has_fresh_data(n, age))
        if not (
            fresh("battery") or
            fresh("odometry") or
            fresh("velocity") or
            fresh("status") or
            fresh("camera") or
            fresh("attitude")
        ):
            # 显示等待连接状态
            if hasattr(self, 'battery_icon_label'):
                self.battery_icon_label.setPixmap(QPixmap(":/images/icons/battery_100.svg").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            if hasattr(self, 'voltage_label'):
                self.voltage_label.setText("-- V")
            if hasattr(self, "battery_status_label"):
                self.battery_status_label.setText("仿真暂无电量读数")
            
            if hasattr(self, 'position_label'):
                self.position_label.setText("Position: (等待无人机连接)")
            
            if hasattr(self, 'altitude_label'):
                self.altitude_label.setText("-- m")
                
            if hasattr(self, 'ground_speed_label'):
                self.ground_speed_label.setText("-- m/s")
            
            # 当没有/mavros/state话题连接时，显示为未连接状态
            if hasattr(self, 'connection_label'):
                if not self.topic_subscriber or not fresh("status"):
                    # 无 MAVROS 时，仿真链路（odom/camera）也视作“已连接”
                    sim_connected = False
                    try:
                        sim_connected = (
                            fresh("odometry")
                            or fresh("camera")
                        )
                    except Exception:
                        sim_connected = False
                    if sim_connected:
                        self.connection_label.setText("已连接")
                        self.connection_label.setStyleSheet("""
                            QLabel {
                                color: #2ECC71;
                                font-weight: bold;
                                background: transparent;
                                border: none;
                                padding: 0px;
                                margin: 0px;
                            }
                        """)
                    else:
                        self.connection_label.setText("未连接")
                        self.connection_label.setStyleSheet("""
                            QLabel {
                                color: #E74C3C;
                                font-weight: bold;
                                background: transparent;
                                border: none;
                                padding: 0px;
                                margin: 0px;
                            }
                        """)
                # 注意：如果话题已连接，则由updateStatusDisplay函数更新状态
            
            # 当没有/mavros/state话题连接时，显示为未知模式
            if hasattr(self, 'mode_label'):
                if not self.topic_subscriber or not fresh("status"):
                    self.mode_label.setText("SIM")  # 仿真模式下不再误报“未连接”
            
            # 话题未连接时，不生成模拟图像，只更新UI显示消息
            
            # 更新RGB图像显示文本 - 使用自定义HTML样式显示
            if hasattr(self, 'image_label'):
                if not fresh("camera"):
                    if self.current_image_mode == "rgb":  # 只在RGB模式下更新
                        self.image_label.setText("""
                            <div style='
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                height: 100%;
                                width: 100%;
                                font-size: 16pt;
                                color: #3498DB;
                                text-align: center;
                                font-weight: bold;
                            '>
                                等待RGB图像话题连接...
                            </div>
                        """)
                    # 确保未使用模拟图像
                    self.camera_image = None

            # 更新深度图像显示文本 - 使用自定义HTML样式显示
            if hasattr(self, 'image_label'):
                if not fresh("depth"):
                    if self.current_image_mode == "depth":  # 只在深度模式下更新
                        self.image_label.setText("""
                            <div style='
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                height: 100%;
                                width: 100%;
                                font-size: 16pt;
                                color: #3498DB;
                                text-align: center;
                                font-weight: bold;
                            '>
                                等待深度图像话题连接...
                            </div>
                        """)
                    # 确保未使用模拟图像
                    self.depth_image = None
                
        # 关键修复：即使 /mavros/state 无发布者，只要仿真链路（odom/camera）正在产出数据，
        # 也要持续把左上角连接卡片更新为“已连接/SIM”。否则会卡在初始化默认“未连接”。
        try:
            sim_connected = bool(
                self.topic_subscriber
                and (
                    self.topic_subscriber.is_topic_active("odometry")
                    or self.topic_subscriber.is_topic_active("camera")
                )
            )
            if sim_connected and hasattr(self, "connection_label") and self.connection_label:
                if self.connection_label.text() != "已连接":
                    self.connection_label.setText("已连接")
                    self.connection_label.setStyleSheet(
                        """
                        QLabel {
                            color: #2ECC71;
                            font-weight: bold;
                            background: transparent;
                            border: none;
                            padding: 0px;
                            margin: 0px;
                        }
                        """
                    )
            if sim_connected and hasattr(self, "mode_label") and self.mode_label:
                if self.mode_label.text() != "SIM":
                    self.mode_label.setText("SIM")
            self._refresh_takeoff_and_operational_labels()
        except Exception:
            pass

        try:
            if self.topic_subscriber and not self.topic_subscriber.has_fresh_data("battery", 4.0):
                if self.battery_percentage is None and hasattr(self, "battery_status_label"):
                    self.battery_status_label.setText("暂无电量数据")
        except Exception:
            pass

    def updateTopicStatus(self):
        """更新并显示话题状态"""
        if not hasattr(self, 'topic_subscriber') or not self.topic_subscriber:
            # 如果话题订阅器未初始化，显示等待启动信息
            if hasattr(self, 'position_label'):
                tooltip = "话题订阅器正在初始化\n正在自动尝试连接ROS话题，请稍候..."
                self.position_label.setToolTip(tooltip)
                
                # 添加或更新状态指示器
                if not hasattr(self, 'topic_status_indicator'):
                    # 创建状态指示器
                    self.topic_status_indicator = QLabel("ℹ️")
                    self.topic_status_indicator.setStyleSheet("color: #3498DB; font-weight: bold; padding-left: 5px; padding-right: 20px;")
                    self.topic_status_indicator.setToolTip(tooltip)
                    
                    # 将指示器添加到位置标签后面
                    if self.position_label.parent():
                        layout = self.position_label.parent().layout()
                        if layout:
                            layout.addWidget(self.topic_status_indicator)
                else:
                    self.topic_status_indicator.setText("ℹ️")
                    self.topic_status_indicator.setStyleSheet("color: #3498DB; font-weight: bold; padding-left: 5px; padding-right: 20px;")
                    self.topic_status_indicator.setToolTip(tooltip)
                    self.topic_status_indicator.show()
            return
            
        # 构建状态信息
        inactive_topics = []
        no_data_topics = []
        
        # 检查每个话题的状态
        for topic_name, is_active in self.topic_subscriber.topics_active.items():
            if not is_active:
                inactive_topics.append(topic_name)
            elif is_active and not self.topics_with_data.get(topic_name, False):
                no_data_topics.append(topic_name)
        
        # 如果有inactive或no_data话题，更新状态信息
        if inactive_topics or no_data_topics:
            status_text = ""
            
            if inactive_topics:
                status_text += f"未连接话题: {', '.join(inactive_topics)}"
            
            if no_data_topics:
                if status_text:
                    status_text += " | "
                status_text += f"无数据话题: {', '.join(no_data_topics)}"
            
            # 更新状态栏
            if hasattr(self, 'position_label'):
                tooltip = "部分话题未连接或没有数据\n\n"
                if inactive_topics:
                    tooltip += f"未连接话题:\n{', '.join(inactive_topics)}\n\n"
                if no_data_topics:
                    tooltip += f"已连接但无数据话题:\n{', '.join(no_data_topics)}"
                
                self.position_label.setToolTip(tooltip)
                
                # 在状态栏显示红点指示器
                if not hasattr(self, 'topic_status_indicator'):
                    # 创建状态指示器
                    self.topic_status_indicator = QLabel("⚠️")
                    self.topic_status_indicator.setStyleSheet("color: #E74C3C; font-weight: bold; padding-left: 5px; padding-right: 20px;")
                    self.topic_status_indicator.setToolTip(tooltip)
                    
                    # 将指示器添加到位置标签后面
                    if self.position_label.parent():
                        layout = self.position_label.parent().layout()
                        if layout:
                            layout.addWidget(self.topic_status_indicator)
                else:
                    self.topic_status_indicator.setText("⚠️")
                    self.topic_status_indicator.setStyleSheet("color: #E74C3C; font-weight: bold; padding-left: 5px; padding-right: 20px;")
                    self.topic_status_indicator.setToolTip(tooltip)
                    self.topic_status_indicator.show()
        elif hasattr(self, 'topic_status_indicator'):
            # 如果所有话题都正常，隐藏指示器
            self.topic_status_indicator.hide()

    def toggleRightSidebarPinned(self):
        """切换右侧栏的固定状态"""
        if self.right_sidebar_pinned:
            # 如果当前是固定状态，解除固定并隐藏
            self.right_sidebar_pinned = False
            self.toggleRightSidebar(hide=True, animate=True)
            # 更新按钮样式，恢复正常
            self.toggle_right_sidebar_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1A202C;  /* 与周围颜色相协调 */
                    border: none;
                    border-radius: 0;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: #3498DB;  /* 蓝色悬停效果 */
                }
                QPushButton:pressed {
                    background-color: #2980B9;  /* 按下效果 */
                }
            """)
        else:
            # 如果当前非固定，切换为固定状态并显示
            self.right_sidebar_pinned = True
            self.toggleRightSidebar(hide=False, animate=True)
            # 更新按钮样式，显示固定状态
            self.toggle_right_sidebar_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498DB;  /* 蓝色背景表示已固定 */
                    border: none;
                    border-radius: 0;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: #2980B9;
                }
                QPushButton:pressed {
                    background-color: #2980B9;
                }
            """)

        # 延迟更新图像尺寸以适应侧边栏变化
        QTimer.singleShot(300, self.updateImageSizes)
    
    def toggleRightSidebar(self, hide=None, animate=False):
        """显示或隐藏右侧栏
        
        参数:
            hide: 是否隐藏右侧栏。如果为None，则切换当前状态
            animate: 是否使用动画效果
        """
        # 如果指定了hide参数，则根据参数决定是否隐藏
        should_hide = hide if hide is not None else self.right_sidebar_expanded
        
        # 如果已经在动画中，则不重复触发
        if hasattr(self, 'right_sidebar_animation') and self.right_sidebar_animation.state() == QPropertyAnimation.Running:
            return

        # 清理之前的动画对象
        if hasattr(self, 'right_sidebar_animation'):
            try:
                self.right_sidebar_animation.finished.disconnect()
                self.right_sidebar_animation.valueChanged.disconnect()
                self.right_sidebar_animation.stop()
                self.right_sidebar_animation.deleteLater()
            except:
                pass  # 忽略断开连接时的错误

        if should_hide:
            # 隐藏右侧栏
            if animate:
                # 使用动画效果
                self.right_sidebar_animation = QPropertyAnimation(self.right_sidebar, b"maximumWidth")
                self.right_sidebar_animation.setDuration(200)  # 动画持续时间200ms
                current_width = self.right_sidebar.width()
                self.right_sidebar_animation.setStartValue(current_width)
                self.right_sidebar_animation.setEndValue(0)
                self.right_sidebar_animation.setEasingCurve(QEasingCurve.InOutQuad)

                # 确保右侧栏可见性正确
                self.right_sidebar.setVisible(True)

                # 动画结束后更新状态
                self.right_sidebar_animation.finished.connect(lambda: self.finishRightSidebarAnimation(False))

                # 动画过程中定期更新悬浮窗口位置
                self.right_sidebar_animation.valueChanged.connect(lambda: self._update_overlay_positions())

                # 启动动画
                self.right_sidebar_animation.start()
                
                # 立即更新状态，但不隐藏右侧栏（等动画完成）
                self.updateRightSidebarState(False)
                
                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                new_sizes = [sizes[0], sizes[1], sizes[2] + sizes[4], sizes[3], 0]
                self.main_splitter.setSizes(new_sizes)
            else:
                # 直接隐藏
                self.right_sidebar.setMaximumWidth(0)
                self.right_sidebar.setMinimumWidth(0)
                self.right_sidebar.setVisible(False)
                self.updateRightSidebarState(False)
                
                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                new_sizes = [sizes[0], sizes[1], sizes[2] + sizes[4], sizes[3], 0]
                self.main_splitter.setSizes(new_sizes)

                # 立即更新悬浮窗口位置
                QTimer.singleShot(50, self._update_overlay_positions)
        else:
            # 显示右侧栏
            if animate:
                # 清理之前的动画对象（如果存在）
                if hasattr(self, 'right_sidebar_animation'):
                    try:
                        self.right_sidebar_animation.finished.disconnect()
                        self.right_sidebar_animation.valueChanged.disconnect()
                        self.right_sidebar_animation.stop()
                        self.right_sidebar_animation.deleteLater()
                    except:
                        pass  # 忽略断开连接时的错误

                # 先设置最大宽度，以便动画可以工作
                self.right_sidebar.setMaximumWidth(self.adaptive_right_width)
                self.right_sidebar.setMinimumWidth(0)
                self.right_sidebar.setVisible(True)

                # 使用动画效果
                self.right_sidebar_animation = QPropertyAnimation(self.right_sidebar, b"maximumWidth")
                self.right_sidebar_animation.setDuration(200)  # 动画持续时间200ms
                self.right_sidebar_animation.setStartValue(0)
                self.right_sidebar_animation.setEndValue(self.adaptive_right_width)
                self.right_sidebar_animation.setEasingCurve(QEasingCurve.InOutQuad)

                # 动画结束后更新状态
                self.right_sidebar_animation.finished.connect(lambda: self.finishRightSidebarAnimation(True))

                # 动画过程中定期更新悬浮窗口位置
                self.right_sidebar_animation.valueChanged.connect(lambda: self._update_overlay_positions())

                # 启动动画
                self.right_sidebar_animation.start()

                # 立即更新状态
                self.updateRightSidebarState(True)

                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                if sizes[2] > self.adaptive_right_width:  # 确保中间区域有足够空间
                    new_sizes = [sizes[0], sizes[1], sizes[2] - self.adaptive_right_width, sizes[3], self.adaptive_right_width]
                else:  # 如果中间区域空间不足，则按比例分配
                    total_space = sizes[2]
                    new_middle = max(int(total_space * 0.4), 100)  # 至少保留100px给中间区域
                    new_sizes = [sizes[0], sizes[1], new_middle, sizes[3], total_space - new_middle]
                self.main_splitter.setSizes(new_sizes)
            else:
                # 直接显示
                self.right_sidebar.setFixedWidth(self.adaptive_right_width)  # 使用自适应宽度
                self.right_sidebar.setVisible(True)
                self.updateRightSidebarState(True)

                # 更新分割器尺寸
                sizes = self.main_splitter.sizes()
                if sizes[2] > self.adaptive_right_width:  # 确保中间区域有足够空间
                    new_sizes = [sizes[0], sizes[1], sizes[2] - self.adaptive_right_width, sizes[3], self.adaptive_right_width]
                else:  # 如果中间区域空间不足，则按比例分配
                    total_space = sizes[2]
                    new_middle = max(int(total_space * 0.4), 100)  # 至少保留100px给中间区域
                    new_sizes = [sizes[0], sizes[1], new_middle, sizes[3], total_space - new_middle]
                self.main_splitter.setSizes(new_sizes)

                # 立即更新悬浮窗口位置
                QTimer.singleShot(50, self._update_overlay_positions)

        # 延迟更新图像尺寸以适应侧边栏变化
        QTimer.singleShot(250, self.updateImageSizes)
                
    def finishRightSidebarAnimation(self, expanded):
        """右侧栏动画结束后的处理

        参数:
            expanded: 是否展开
        """
        if not expanded:
            # 动画结束后，如果是隐藏状态，则设置不可见以减少资源占用
            self.right_sidebar.setVisible(False)
        else:
            # 如果是显示状态，确保最小宽度也设置好
            self.right_sidebar.setMinimumWidth(self.adaptive_right_width)

        # 动画完成后立即更新悬浮窗口位置，使用多次延迟更新确保位置正确
        self._update_overlay_positions()
        QTimer.singleShot(50, self._update_overlay_positions)
        QTimer.singleShot(100, self._update_overlay_positions)
        QTimer.singleShot(200, self._update_overlay_positions)
    
    def updateRightSidebarState(self, expanded):
        """更新右侧栏状态

        参数:
            expanded: 是否展开
        """
        self.right_sidebar_expanded = expanded
        self.toggle_right_sidebar_btn.setIcon(QIcon(":/images/icons/dropright.svg" if expanded else ":/images/icons/dropleft.svg"))
        self.toggle_right_sidebar_btn.style().unpolish(self.toggle_right_sidebar_btn)
        self.toggle_right_sidebar_btn.style().polish(self.toggle_right_sidebar_btn)

    def toggleRVizDisplayPanel(self):
        """显示或隐藏RViz的原生显示面板"""
        try:
            # 使用RViz的setDisplayConfigVisible方法切换显示面板可见性
            display_visible = self.manager.getDisplayConfigVisibility()
            self.manager.setDisplayConfigVisibility(not display_visible)
            
            # 更新按钮文本
            if not display_visible:
                self.settings_button.setText("隐藏设置")
            else:
                self.settings_button.setText("设置")
        except Exception as e:
            print(f"切换RViz显示面板时出错: {str(e)}")

    def updateAttitudeDisplay(self, data=None):
        """更新姿态信息显示"""
        try:
            # 从话题数据中获取姿态信息
            if self.topic_subscriber and self.topic_subscriber.is_topic_active("attitude"):
                # 如果有真实姿态数据，使用真实数据
                attitude_data = data if data else self.topic_subscriber.get_latest_data("attitude")
                if attitude_data:
                    # 获取俯仰角并检查是否为列表
                    pitch_value = attitude_data.get("pitch", 0)
                    if isinstance(pitch_value, list):
                        if len(pitch_value) > 0:
                            pitch_value = pitch_value[0]
                        else:
                            pitch_value = 0
                    self.pitch = pitch_value
                    
                    # 获取滚转角并检查是否为列表
                    roll_value = attitude_data.get("roll", 0)
                    if isinstance(roll_value, list):
                        if len(roll_value) > 0:
                            roll_value = roll_value[0]
                        else:
                            roll_value = 0
                    self.roll = roll_value
                    
                    # 获取偏航角
                    yaw_value = attitude_data.get("yaw", 0)
                    if isinstance(yaw_value, list):
                        if len(yaw_value) > 0:
                            yaw_value = yaw_value[0]
                        else:
                            yaw_value = 0
                    
                    # 更新姿态标签 - 使用原始偏航角值
                    if hasattr(self, 'pitch_label'):
                        self.pitch_label.setText(f"{pitch_value:.2f}°")
                    if hasattr(self, 'roll_label'):
                        self.roll_label.setText(f"{roll_value:.2f}°")
                    if hasattr(self, 'yaw_label'):
                        self.yaw_label.setText(f"{-yaw_value:.2f}°")

                    # 同时更新RViz悬浮窗口组件
                    if hasattr(self, 'compass') and self.compass:
                        self.compass.set_heading(-yaw_value)

                    if hasattr(self, 'attitude_widget') and self.attitude_widget:
                        self.attitude_widget.update_attitude(pitch_value, roll_value)

                    # 保留对姿态指示器的更新，如果还在使用的话
                    if hasattr(self, 'attitude_indicator'):
                        self.attitude_indicator.update_attitude(self.pitch, self.roll)
            else:
                # 没有实际姿态数据时，显示默认值
                self.pitch = 0
                self.roll = 0
                if hasattr(self, 'pitch_label'):
                    self.pitch_label.setText("0.00°")
                if hasattr(self, 'roll_label'):
                    self.roll_label.setText("0.00°")
                if hasattr(self, 'yaw_label'):
                    self.yaw_label.setText("0.00°")
                
                # 如果姿态指示器还存在，也更新为零位
                if hasattr(self, 'attitude_indicator'):
                    self.attitude_indicator.update_attitude(self.pitch, self.roll)
        except Exception as e:
            print(f"更新姿态显示时出错: {str(e)}")
    
    def updateObstacleAvoidanceWarning(self, obstacle_data=None):
        """避障提示：面向操作员，避免代码腔与日志腔。"""
        try:
            if not hasattr(self, "obstacle_warning_label") or not self.obstacle_warning_label:
                return

            ts = self.topic_subscriber
            depth_dp = ts.get_data("depth_proximity") if ts else None
            depth_ok = bool(depth_dp and depth_dp.get("ok"))
            depth_near = float(depth_dp.get("near_m", -1.0)) if depth_ok else -1.0
            depth_min = float(depth_dp.get("min_m", -1.0)) if depth_ok else -1.0
            depth_fresh = bool(ts and ts.has_fresh_data("depth", 2.5))

            obstacles = []
            if obstacle_data:
                obstacles = obstacle_data.get("obstacles", [])
            elif ts and ts.is_topic_active("obstacle_states"):
                data = ts.get_data("obstacle_states")
                if data:
                    obstacles = data.get("obstacles", [])

            drone_pos = {"x": 0.0, "y": 0.0, "z": 0.0}
            if ts and ts.is_topic_active("odometry"):
                odom_data = ts.get_data("odometry")
                if odom_data and "position" in odom_data:
                    drone_pos = odom_data["position"]

            det_topic_up = bool(ts and ts.is_topic_active("obstacle_states"))
            det_fresh = bool(ts and ts.has_fresh_data("obstacle_states", 5.0))

            dists = []
            d_bbox = None
            if obstacles:
                for obs in obstacles:
                    obs_pos = obs.get("position", {"x": 0, "y": 0, "z": 0})
                    dx = obs_pos["x"] - drone_pos["x"]
                    dy = obs_pos["y"] - drone_pos["y"]
                    dz = obs_pos["z"] - drone_pos["z"]
                    dists.append((dx * dx + dy * dy + dz * dz) ** 0.5)
                d_bbox = min(dists)

            d_use = None
            has_detector = d_bbox is not None
            if depth_ok and depth_near > 0:
                d_use = depth_near if d_bbox is None else min(d_bbox, depth_near)
            elif d_bbox is not None:
                d_use = d_bbox

            wrap = (
                "<div style='padding:10px 12px;line-height:1.55;border-radius:8px;"
                "background:rgba(0,0,0,0.25);'>{}</div>"
            )

            if d_use is None:
                if not det_topic_up and not depth_fresh:
                    self.obstacle_warning_label.setText(
                        wrap.format(
                            "<span style='color:#95A5A6;font-size:12pt;'>"
                            "<b>暂无数据</b><br/>"
                            "<span style='font-size:11pt;'>未收到障碍物与深度信息，无法估算前向距离。</span>"
                            "</span>"
                        )
                    )
                    return
                if det_topic_up and det_fresh and not obstacles and depth_fresh and not depth_ok:
                    self.obstacle_warning_label.setText(
                        wrap.format(
                            "<span style='color:#F39C12;font-size:12pt;'>"
                            "<b>提示</b><br/>"
                            "<span style='font-size:11pt;'>画面里若有人或物体，深度可能暂时不可靠，请结合目视判断。</span>"
                            "</span>"
                        )
                    )
                    return
                if det_topic_up and det_fresh and not obstacles and not depth_ok:
                    self.obstacle_warning_label.setText(
                        wrap.format(
                            "<span style='color:#2ECC71;font-size:12pt;'>"
                            "<b>当前较空旷</b><br/>"
                            "<span style='font-size:11pt;'>未报告动态障碍；前向距离待深度稳定后更新。</span>"
                            "</span>"
                        )
                    )
                    return
                self.obstacle_warning_label.setText(
                    wrap.format(
                        "<span style='color:#95A5A6;font-size:12pt;'>"
                        "暂时无法估算前向距离，请稍候或检查相机。</span>"
                    )
                )
                return

            if d_use < 1.35:
                color = "#E74C3C"
                title = "高度注意"
                body = (
                    f"疑似前方非常近（约 <b style='font-size:15pt'>{d_use:.1f}</b> 米），"
                    "建议减速或绕行，并保持目视。"
                )
            elif d_use < 2.4:
                color = "#E74C3C"
                title = "注意距离"
                body = (
                    f"前方可能较近（约 <b style='font-size:15pt'>{d_use:.1f}</b> 米），"
                    "请保持警惕。"
                )
            elif d_use < 4.2:
                color = "#F39C12"
                title = "中等距离"
                body = (
                    f"估计前向约 <b style='font-size:15pt'>{d_use:.1f}</b> 米，"
                    "若画面中有移动目标，请持续观察。"
                )
            else:
                color = "#2ECC71"
                title = "相对安全"
                body = (
                    f"估计前向约 <b style='font-size:15pt'>{d_use:.1f}</b> 米，"
                    "仍请以实际环境为准。"
                )

            sub = ""
            if has_detector and obstacles:
                sub = f"<br/><span style='color:#BDC3C7;font-size:10pt;'>已同步 {len(obstacles)} 个跟踪目标。</span>"
            elif depth_ok and not has_detector:
                sub = "<br/><span style='color:#BDC3C7;font-size:10pt;'>距离主要由相机深度估计，仅供参考。</span>"
            if depth_ok and depth_min > 0 and depth_min + 0.5 < depth_near:
                sub += "<br/><span style='color:#85929E;font-size:10pt;'>可能存在更近的局部反射，请以目视为准。</span>"

            self.obstacle_warning_label.setText(
                wrap.format(
                    f"<span style='color:{color};font-size:13pt;font-weight:bold;'>{title}</span><br/>"
                    f"<span style='color:#ECF0F1;font-size:12pt;'>{body}</span>{sub}"
                )
            )
        except Exception as e:
            print(f"更新避障警告时出错: {str(e)}")
            
    def toggleLogWindow(self):
        """显示或隐藏日志窗口"""
        try:
            # 如果按钮被选中，但窗口不存在或已关闭
            if self.log_button.isChecked():
                # 如果窗口不存在，创建一个
                if not self.log_window or not hasattr(self.log_window, 'isVisible') or not self.log_window.isVisible():
                    if TopicLogger:
                        try:
                            from topic_logger import TopicLoggerDialog
                            self.log_window = TopicLoggerDialog(self)
                            # 窗口关闭时自动取消按钮选中状态
                            self.log_window.finished.connect(lambda: self.log_button.setChecked(False))
                            self.log_window.show()
                        except Exception as e:
                            print(f"创建日志窗口时出错: {str(e)}")
                            self.log_button.setChecked(False)
                    else:
                        print("话题日志组件不可用")
                        self.log_button.setChecked(False)
            else:
                # 如果按钮未选中，关闭窗口
                if self.log_window and hasattr(self.log_window, 'isVisible') and self.log_window.isVisible():
                    self.log_window.close()
        except Exception as e:
            print(f"切换日志窗口时出错: {str(e)}")
            self.log_button.setChecked(False)

    @staticmethod
    def _sleep_ui_responsive(seconds, progress_dialog=None):
        """在 UI 线程等待时周期性 processEvents，降低长 sleep 造成的整窗无响应。"""
        if seconds <= 0:
            return
        deadline = time.time() + float(seconds)
        while time.time() < deadline:
            try:
                QApplication.processEvents()
            except Exception:
                pass
            if progress_dialog is not None and progress_dialog.wasCanceled():
                break
            time.sleep(0.05)

    def _gazebo_pause_physics_blocking(self, progress_dialog=None, timeout_sec=120.0):
        """
        调用 /gazebo/pause_physics：一键启动过程中仿真若已运行，先冻结物理，
        避免 NavRL/控制栈未就绪时行人或碰撞把无人机拖走。
        由 ROS 参数 /myviz/pause_gazebo_until_stack_ready 控制（默认 true）。
        若 launch 已带 paused:=true，世界本身已冻结，可跳过对本服务的阻塞等待（见 /myviz/skip_pause_physics_when_launch_paused）。
        """
        try:
            if not rospy.get_param("/myviz/pause_gazebo_until_stack_ready", True):
                return False
        except Exception:
            pass
        try:
            skip_lp = rospy.get_param("/myviz/skip_pause_physics_when_launch_paused", True)
        except Exception:
            skip_lp = True
        if skip_lp and getattr(self, "_uav_sim_launch_paused", False):
            rospy.loginfo(
                "myviz: 世界以 paused 启动，跳过阻塞等待 /gazebo/pause_physics（已处于冻结状态）"
            )
            return True
        try:
            from std_srvs.srv import Empty
        except ImportError:
            return False
        t_end = time.time() + float(timeout_sec)
        t0 = time.time()
        while time.time() < t_end:
            try:
                rospy.wait_for_service("/gazebo/pause_physics", timeout=0.65)
                rospy.ServiceProxy("/gazebo/pause_physics", Empty)()
                rospy.loginfo(
                    "myviz: 已暂停 Gazebo 物理（导航栈就绪后将自动恢复仿真）"
                )
                return True
            except Exception:
                if progress_dialog is not None:
                    try:
                        waited = int(time.time() - t0)
                        progress_dialog.setLabelText(
                            f"等待 Gazebo 服务 /gazebo/pause_physics（已等待 {waited}s，"
                            f"仿真完全加载后可用）…"
                        )
                        progress_dialog.setValue(min(8, waited))
                        QApplication.processEvents()
                    except Exception:
                        pass
                time.sleep(0.12)
        rospy.logwarn(
            "myviz: 超时未等到 /gazebo/pause_physics，仿真将继续运行（若已起 Gazebo）"
        )
        return False

    def _gazebo_unpause_physics_blocking(self, progress_dialog=None, timeout_sec=15.0):
        """恢复 /gazebo/unpause_physics。"""
        try:
            from std_srvs.srv import Empty
            rospy.wait_for_service("/gazebo/unpause_physics", timeout=float(timeout_sec))
            rospy.ServiceProxy("/gazebo/unpause_physics", Empty)()
            rospy.loginfo("myviz: 已恢复 Gazebo 仿真")
            return True
        except Exception as ex:
            rospy.logwarn("myviz: unpause_physics 失败: %s", ex)
            return False

    def _navrl_stack_ready(self):
        """
        检测 NavRL 侧是否已开始对外发布关键话题。
        注意：/rl_navigation/raycast 在仅有 odom、尚未完成策略控制时就会出现，不能单独作为「可 unpause」条件。
        """
        try:
            topic_set = {t[0] for t in rospy.get_published_topics()}
        except Exception:
            return False
        try:
            strict = rospy.get_param("/myviz/navrl_ready_require_topics", None)
            if isinstance(strict, str):
                strict = [x.strip() for x in strict.split(",") if x.strip()]
            if isinstance(strict, (list, tuple)) and len(strict) > 0:
                strict = [str(x).strip() for x in strict if str(x).strip()]
                return all(t in topic_set for t in strict)
        except Exception:
            pass
        # 默认：需同时存在「可视化 raycast」与「控制量 cmd_vel」，避免仅 raycast 就误判就绪
        return ("/rl_navigation/raycast" in topic_set) and (
            "/CERLAB/quadcopter/cmd_vel" in topic_set
        )

    def _navrl_ready_for_unpause(self):
        """在 _navrl_stack_ready 基础上，再满足 NavRL 进程启动后的最短墙钟等待。"""
        if not self._navrl_stack_ready():
            return False
        try:
            min_wall = float(rospy.get_param("/myviz/navrl_ready_min_wall_sec", 14.0))
        except Exception:
            min_wall = 14.0
        t0 = getattr(self, "_navrl_popen_wall_time", None)
        if t0 is None:
            return True
        return (time.time() - float(t0)) >= max(0.0, min_wall)

    def _wait_for_navrl_ready_blocking(self, progress_dialog, need_wait):
        """
        在仿真已 unpause、时间可推进的前提下阻塞，直到 NavRL 关键话题出现或超时。
        若 Gazebo 仍暂停，NavRL 往往无法发布 /CERLAB/quadcopter/cmd_vel，会导致永久「未就绪」。
        need_wait：本次一键启动是否实际启动了 NavRL（run_navrl_navigation）。
        """
        if not need_wait:
            return
        try:
            if os.environ.get("EXPLORE_SKIP_NAVRL_READY_WAIT", "").strip().lower() in (
                "1",
                "true",
                "yes",
            ):
                rospy.logwarn("myviz: 已跳过 NavRL 就绪等待（EXPLORE_SKIP_NAVRL_READY_WAIT）")
                return
        except Exception:
            pass
        try:
            if not rospy.get_param("/myviz/wait_navrl_ready_before_unpause", True):
                return
        except Exception:
            pass
        try:
            timeout_sec = float(rospy.get_param("/myviz/navrl_ready_timeout_sec", 120.0))
        except Exception:
            timeout_sec = 120.0
        deadline = time.time() + max(5.0, timeout_sec)
        wait_t0 = time.time()
        try:
            min_wall = float(rospy.get_param("/myviz/navrl_ready_min_wall_sec", 14.0))
        except Exception:
            min_wall = 14.0
        rospy.loginfo(
            "myviz: 等待 NavRL 就绪（最长约 %.0fs，最短 %.0fs；仿真应已恢复推进）…",
            timeout_sec,
            min_wall,
        )
        while time.time() < deadline:
            elapsed = time.time() - wait_t0
            # NavRL 的 raycast/控制环依赖 goal_received；一键启动时 goal 在栈后才同步，这里提前刷一次 hold goal 打通控制链
            if (
                getattr(self, "_navrl_popen_wall_time", None) is not None
                and elapsed >= 3.5
                and not getattr(self, "_did_navrl_preflight_goal", False)
            ):
                self._did_navrl_preflight_goal = True
                try:
                    self._sync_nav_goal_to_current_odom_once(
                        quiet=True, reason="preflight"
                    )
                except Exception:
                    pass
            sig = self._navrl_stack_ready()
            wall_ok = self._navrl_ready_for_unpause()
            if sig and wall_ok:
                try:
                    extra_delay = float(rospy.get_param("/myviz/gazebo_unpause_extra_delay_sec", 0.5))
                except Exception:
                    extra_delay = 0.5
                extra_delay = max(0.0, extra_delay)
                if extra_delay > 0:
                    rospy.loginfo(
                        "myviz: NavRL 已就绪，额外等待 %.2fs 后恢复仿真",
                        extra_delay,
                    )
                    self._sleep_ui_responsive(extra_delay, progress_dialog)
                else:
                    rospy.loginfo("myviz: NavRL 已就绪，即将恢复 Gazebo 仿真")
                return
            elapsed = time.time() - wait_t0
            remain = max(0.0, deadline - time.time())
            frac = min(1.0, elapsed / max(timeout_sec, 1.0))
            # 等待阶段单独占 58%→86%，避免「88% 却还剩两分钟」的错觉
            bar = int(58 + frac * 28)
            if progress_dialog is not None:
                try:
                    if sig and (not wall_ok):
                        wr = max(0.0, min_wall - (time.time() - (getattr(self, "_navrl_popen_wall_time", wait_t0) or wait_t0)))
                        progress_dialog.setLabelText(
                            "NavRL 已响应 ROS，仍在最短安全等待 "
                            f"{int(math.ceil(wr))} 秒（确保权重与控制就绪）…"
                        )
                    else:
                        progress_dialog.setLabelText(
                            "NavRL 强化学习导航加载中… "
                            f"已等待 {int(elapsed)} 秒，剩余约 {int(math.ceil(remain))} 秒"
                        )
                    progress_dialog.setValue(min(86, bar))
                    QApplication.processEvents()
                except Exception:
                    pass
            self._sleep_ui_responsive(1.0, progress_dialog)
        rospy.logwarn(
            "myviz: 等待 NavRL 就绪超时（%.0fs），仍将恢复仿真；若飞机异常请检查 NavRL 日志",
            timeout_sec,
        )

    def _post_unpause_cerlab_stabilize_blocking(self, progress_dialog, need_navrl):
        """
        unpause 后 CERLAB 机体可能仍贴地/穿模：发 takeoff 脉冲并短暂等待里程计 z，
        避免「物理已开但推力/位姿未跟上」导致陷入地底。
        """
        if not need_navrl:
            return
        try:
            if not rospy.get_param("/myviz/post_unpause_cerlab_stabilize", True):
                return
        except Exception:
            pass
        try:
            min_z = float(rospy.get_param("/myviz/post_unpause_min_odom_z_m", 0.42))
        except Exception:
            min_z = 0.42
        try:
            timeout_sec = float(rospy.get_param("/myviz/post_unpause_stabilize_timeout_sec", 24.0))
        except Exception:
            timeout_sec = 24.0
        deadline = time.time() + max(3.0, timeout_sec)
        rospy.loginfo(
            "myviz: 仿真已恢复，等待机体离地稳定（里程计 z≥%.2fm，最长 %.0fs）…",
            min_z,
            timeout_sec,
        )
        try:
            from std_msgs.msg import Empty

            pub = rospy.Publisher("/CERLAB/quadcopter/takeoff", Empty, queue_size=2)
            rospy.sleep(0.12)
            pub.publish(Empty())
            rospy.sleep(0.18)
            pub.publish(Empty())
        except Exception as ex:
            rospy.logwarn("myviz: 发送 CERLAB takeoff 脉冲失败（可忽略）: %s", ex)

        ts = getattr(self, "topic_subscriber", None)
        while time.time() < deadline:
            if ts and ts.has_fresh_data("odometry", 2.5):
                o = ts.get_data("odometry") or {}
                p = o.get("position") or {}
                try:
                    z = float(p.get("z", -999.0))
                except (TypeError, ValueError):
                    z = -999.0
                if z >= min_z:
                    rospy.loginfo("myviz: 机体高度已稳定（odom z=%.3f m），可继续", z)
                    return
            remain = int(max(0.0, deadline - time.time()))
            if progress_dialog is not None:
                try:
                    progress_dialog.setLabelText(
                        f"仿真运行中，等待机体离地…（约 {remain} 秒）"
                    )
                    QApplication.processEvents()
                except Exception:
                    pass
            self._sleep_ui_responsive(0.35, progress_dialog)

        rospy.logwarn(
            "myviz: 等待离地超时（目标 z≥%.2fm）；若仍贴地请检查 CERLAB 插件或略提高 control_config spawn_xyz[2]",
            min_z,
        )

    def _gazebo_probe_drone_world_full(self, gsm, model_name, progress_dialog):
        """
        读取 Gazebo 中机体世界位姿。
        返回 (z, 实际模型名, pose, twist)；失败为 (None, None, None, None)。
        注意：GetModelState 的响应字段是 geometry_msgs/Pose pose，不是 pose.pose。
        """
        z = None
        used_name = None
        pose = None
        twist = None
        for _ in range(6):
            for rel in ("", "world"):
                try:
                    r = gsm(model_name, rel)
                    if r.success:
                        pose = r.pose
                        z = float(pose.position.z)
                        used_name = model_name
                        twist = getattr(r, "twist", None)
                        break
                    rospy.logwarn_throttle(
                        5.0,
                        "myviz: get_model_state(%s,%r) 失败: %s",
                        model_name,
                        rel,
                        getattr(r, "status_message", "") or "?",
                    )
                except Exception as ex:
                    rospy.logwarn_throttle(5.0, "myviz: get_model_state 异常: %s", ex)
            if z is not None and pose is not None:
                return z, used_name, pose, twist
            self._sleep_ui_responsive(0.2, progress_dialog)
        try:
            from gazebo_msgs.msg import ModelStates

            msg = rospy.wait_for_message(
                "/gazebo/model_states", ModelStates, timeout=3.0
            )
            names = list(msg.name or [])
            poses = list(msg.pose or [])
            twists = list(msg.twist or []) if msg.twist else []
            if names and poses and len(names) == len(poses):
                want = model_name.lower()
                for i, n in enumerate(names):
                    if n.lower() == want:
                        p = poses[i]
                        tw = twists[i] if i < len(twists) else None
                        return float(p.position.z), n, p, tw
                subs = ("quad", "cerlab", "uav", "iris", "drone")
                skip = ("ground", "plane", "person", "human", "actor", "walker", "pillar", "column", "obstacle")
                best = None
                best_z = -1e9
                best_i = None
                for i, n in enumerate(names):
                    nl = n.lower()
                    if any(s in nl for s in skip):
                        continue
                    if any(s in nl for s in subs):
                        zz = float(poses[i].position.z)
                        if zz > best_z:
                            best_z = zz
                            best = n
                            best_i = i
                if best is not None and best_i is not None:
                    p = poses[best_i]
                    tw = twists[best_i] if best_i < len(twists) else None
                    rospy.loginfo(
                        "myviz: 经 /gazebo/model_states 推断机体为「%s」z=%.3f m",
                        best,
                        best_z,
                    )
                    return best_z, best, p, tw
        except Exception as ex:
            rospy.logwarn("myviz: 读取 /gazebo/model_states 失败: %s", ex)
        return None, None, None, None

    def _gazebo_rescue_if_model_buried_blocking(self, progress_dialog, need_navrl):
        """
        里程计 z 正常时，Gazebo 碰撞体仍可能穿入地面（插件与网格不一致）。
        用 /gazebo/get_model_state 读真实模型高度，过低则 pause+set_model_state 抬升。
        """
        if not need_navrl:
            return
        try:
            if not rospy.get_param("/myviz/gazebo_rescue_after_unpause", True):
                return
        except Exception:
            pass
        try:
            thr = float(rospy.get_param("/myviz/gazebo_rescue_if_model_z_below_m", 0.38))
        except Exception:
            thr = 0.38
        try:
            target_z = float(rospy.get_param("/myviz/gazebo_rescue_target_z_m", 0.95))
        except Exception:
            target_z = 0.95
        cfg_path = os.path.join(os.path.dirname(__file__), "control_config.json")
        try:
            with open(cfg_path, "r", encoding="utf-8") as cf:
                cfg = json.load(cf)
        except Exception as ex:
            rospy.logwarn("myviz: 无法读取 control_config.json，跳过 Gazebo 埋地救援: %s", ex)
            return
        g = cfg.get("gazebo") or {}
        model_name = str(g.get("drone_model_name", "quadcopter"))
        try:
            from gazebo_msgs.srv import GetModelState
        except Exception as ex:
            rospy.logwarn("myviz: 未找到 gazebo_msgs，跳过埋地救援: %s", ex)
            return
        try:
            rospy.wait_for_service("/gazebo/get_model_state", timeout=6.0)
            gsm = rospy.ServiceProxy("/gazebo/get_model_state", GetModelState)
        except Exception as ex:
            rospy.logwarn("myviz: /gazebo/get_model_state 不可用，跳过埋地救援: %s", ex)
            return
        self._sleep_ui_responsive(0.35, progress_dialog)
        z, resolved, gpose, gtwist = self._gazebo_probe_drone_world_full(
            gsm, model_name, progress_dialog
        )
        if z is None or gpose is None:
            rospy.logwarn(
                "myviz: 无法读取机体 Gazebo 位姿（已试模型名 %s），跳过埋地救援",
                model_name,
            )
            return
        if z >= thr:
            rospy.loginfo(
                "myviz: Gazebo 模型高度 z=%.3f m（≥%.2f），无需埋地救援",
                z,
                thr,
            )
            return
        rospy.logwarn(
            "myviz: Gazebo 模型 z=%.3f m < %.2f m（与里程计可能不一致），"
            "执行就地抬升（保持当前水平位置，避免拉回 spawn 原点）→ z≥%.2f m",
            z,
            thr,
            target_z,
        )
        if progress_dialog is not None:
            try:
                progress_dialog.setLabelText("检测到机体穿模/贴地，正在 Gazebo 就地抬升…")
                QApplication.processEvents()
            except Exception:
                pass
        try:
            from gazebo_msgs.msg import ModelState
            from gazebo_msgs.srv import SetModelState
            from geometry_msgs.msg import Twist
            from std_srvs.srv import Empty

            svc = str(g.get("set_model_state_service", "/gazebo/set_model_state"))
            pause_svc = str(g.get("pause_physics_service", "/gazebo/pause_physics"))
            unpause_svc = str(g.get("unpause_physics_service", "/gazebo/unpause_physics"))
            mname = str(resolved or model_name)
            new_pose = copy.deepcopy(gpose)
            nz = max(float(target_z), float(gpose.position.z) + 0.18)
            try:
                z_cap = float(rospy.get_param("/myviz/gazebo_buried_rescue_max_z_m", 6.0))
            except Exception:
                z_cap = 6.0
            new_pose.position.z = min(nz, z_cap)

            try:
                rospy.wait_for_service(pause_svc, timeout=0.35)
                rospy.ServiceProxy(pause_svc, Empty)()
            except Exception:
                pass

            st = ModelState()
            st.model_name = mname
            st.reference_frame = "world"
            st.pose = new_pose
            if gtwist is not None:
                st.twist = copy.deepcopy(gtwist)
            else:
                st.twist = Twist()

            rospy.wait_for_service(svc, timeout=1.2)
            resp = rospy.ServiceProxy(svc, SetModelState)(st)
            if not resp.success:
                rospy.logwarn(
                    "myviz: 埋地就地抬升 set_model_state 失败: %s",
                    getattr(resp, "status_message", "") or "?",
                )
            else:
                rospy.loginfo(
                    "myviz: 已对「%s」就地抬升至 z=%.3f（xy 未改）",
                    mname,
                    new_pose.position.z,
                )

            try:
                rospy.wait_for_service(unpause_svc, timeout=0.45)
                rospy.ServiceProxy(unpause_svc, Empty)()
            except Exception:
                pass
        except Exception as ex:
            rospy.logwarn("myviz: Gazebo 埋地就地抬升异常: %s", ex)
        try:
            from std_msgs.msg import Empty

            pub = rospy.Publisher("/CERLAB/quadcopter/takeoff", Empty, queue_size=2)
            rospy.sleep(0.1)
            pub.publish(Empty())
        except Exception:
            pass

    def _navigation_config_dict(self):
        nav_path = os.path.join(os.path.dirname(__file__), "navigation_config.json")
        try:
            with open(nav_path, "r", encoding="utf-8") as nf:
                return json.load(nf)
        except Exception:
            return {}

    def _nav_behavior_bool(self, rosparam_name, config_key, default):
        """navigation_config 与 /myviz/*：未显式设置 rosparam 时采用配置文件中的值。"""
        try:
            base = bool(self._navigation_config_dict().get(config_key, default))
        except Exception:
            base = default
        try:
            return bool(rospy.get_param(rosparam_name, base))
        except Exception:
            return base

    def _on_stack_start_goal_sync(self):
        self._sync_nav_goal_to_current_odom_once(quiet=False, reason="stack")

    def _navigation_goal_frame_id(self):
        return (self._navigation_config_dict().get("goal_frame_id") or "map").strip()

    def _snapshot_home_position_from_odom(self, attempt=0):
        """栈启动完成、仿真 unpause 后延迟采样真实起飞位，避免返航飞向 map 原点 (0,0) 穿墙。"""
        max_att = 10
        ts = getattr(self, "topic_subscriber", None)
        if not ts or not ts.has_fresh_data("odometry", 6.0):
            if attempt < max_att:
                QTimer.singleShot(2000, lambda: self._snapshot_home_position_from_odom(attempt + 1))
            else:
                rospy.logwarn("myviz: 返航原点快照失败：无新鲜里程计")
            return
        o = ts.get_data("odometry") or {}
        p = o.get("position") or {}
        try:
            x = float(p.get("x", 0.0))
            y = float(p.get("y", 0.0))
            z = float(p.get("z", 0.0))
        except (TypeError, ValueError):
            x = y = z = 0.0
        if abs(x) < 1e-5 and abs(y) < 1e-5 and z < 0.08 and attempt < max_att:
            QTimer.singleShot(1500, lambda: self._snapshot_home_position_from_odom(attempt + 1))
            return
        nav = self._navigation_config_dict()
        z_floor = float(nav.get("return_home_default_z_min", 0.45))
        self._home_position = {"x": x, "y": y, "z": max(z_floor, z)}
        self._home_frame_id = (o.get("frame_id") or "").strip()
        self._home_position_locked = True
        rospy.loginfo(
            "myviz: 已锁定返航点（栈就绪后快照）: (%.3f, %.3f, %.3f) odom_frame=%s",
            x,
            y,
            self._home_position["z"],
            self._home_frame_id or "?",
        )

    def _resolve_return_home_xyz(self):
        """返航坐标：优先锁定 home → 当前里程计 → 配置默认 Z（避免硬编码飞向原点）。"""
        nav = self._navigation_config_dict()
        z_def = float(nav.get("return_home_default_z", 0.95))
        z_min = float(nav.get("return_home_default_z_min", 0.45))
        if getattr(self, "_home_position", None):
            try:
                hx = float(self._home_position.get("x", 0.0))
                hy = float(self._home_position.get("y", 0.0))
                hz = float(self._home_position.get("z", z_def))
                return hx, hy, max(z_min, hz)
            except (TypeError, ValueError):
                pass
        ts = getattr(self, "topic_subscriber", None)
        if ts and ts.has_fresh_data("odometry", 6.0):
            p = (ts.get_data("odometry") or {}).get("position") or {}
            try:
                hx = float(p.get("x", 0.0))
                hy = float(p.get("y", 0.0))
                hz = max(z_min, float(p.get("z", z_def)))
                return hx, hy, hz
            except (TypeError, ValueError):
                pass
        return 0.0, 0.0, max(z_min, z_def)

    def _configure_return_home_detection(self, wa=None):
        """从 waypoint_advance 加载到达判定：支持 horizontal（水平+分向 Z）与 3D。"""
        nav_cfg = self._navigation_config_dict()
        base = dict(nav_cfg.get("waypoint_advance") or {})
        if wa:
            base.update(dict(wa))
        wa = base
        dm = float(wa.get("distance_fallback_m", 0.65))
        self._return_home_dist_mode = str(wa.get("distance_mode", "3d")).strip().lower()
        self._return_home_xy_thresh = float(wa.get("distance_fallback_xy_m", dm))
        self._return_home_z_thresh = float(wa.get("distance_fallback_z_m", 0.85))
        self._return_home_dist_thresh = float(wa.get("distance_fallback_m", dm))
        self._return_home_min_sec = float(wa.get("min_seconds_before_distance_check", 2.5))
        self._return_home_fsm_exec = int(wa.get("exec_state", 4))
        self._return_home_fsm_wait = int(wa.get("wait_state", 1))
        self._return_home_navrl_grace_sec = float(wa.get("navrl_traj_done_grace_sec", 2.0))

    def _return_home_position_reached(self, pos, tgt):
        """按当前模式判断里程计位置是否已到达返航目标附近。"""
        if not pos or not tgt:
            return False
        dx = float(pos.get("x", 0.0)) - float(tgt.get("x", 0.0))
        dy = float(pos.get("y", 0.0)) - float(tgt.get("y", 0.0))
        dz = float(pos.get("z", 0.0)) - float(tgt.get("z", 0.0))
        mode = (getattr(self, "_return_home_dist_mode", None) or "3d").lower()
        xy = math.sqrt(dx * dx + dy * dy)
        z_abs = abs(dz)
        if mode in ("horizontal", "xy", "planar", "2d"):
            return bool(
                xy < float(getattr(self, "_return_home_xy_thresh", 0.65))
                and z_abs < float(getattr(self, "_return_home_z_thresh", 0.85))
            )
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        return bool(dist < float(getattr(self, "_return_home_dist_thresh", 0.65)))

    def startDroneSystem(self):
        """启动无人机导航系统 - 使用配置文件驱动"""
        self._gazebo_paused_for_stack_start = False
        self._uav_sim_launch_paused = False
        need_wait_navrl = False
        self._navrl_popen_wall_time = None
        self._did_navrl_preflight_goal = False
        # 新会话重新学习起飞点，避免沿用旧 home 飞到墙内/原点
        self._home_position = None
        self._home_position_locked = False
        self._home_frame_id = ""
        try:
            # 加载进程配置
            config = load_processes_config()
            processes_list = config.get('processes', [])
            
            if not processes_list:
                notify(self, "配置错误", "进程配置为空，请检查 processes_config.json", "warning")
                return
            
            # 获取日志保存配置
            save_log = config.get('save_log', True)
            
            # 创建日志目录
            log_dir_name = config.get('log_directory', 'log')
            log_dir = get_data_directory(log_dir_name)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # 获取工作空间路径（容错：配置错误时自动回退到常见目录）
            catkin_ws = self._resolve_catkin_workspace(config)
            if not catkin_ws:
                notify_error(
                    self,
                    "工作空间错误",
                    "未找到可用 Catkin 工作空间。\n"
                    "请检查 processes_config.json 的 catkin_workspace，"
                    "或创建工作空间并确保 devel/setup.bash 存在。"
                )
                return

            try:
                rospy.set_param("/myviz/catkin_workspace", catkin_ws)
                ts = getattr(self, "topic_subscriber", None)
                if ts is not None and hasattr(ts, "invalidate_drone_mesh_cache"):
                    ts.invalidate_drone_mesh_cache()
            except Exception:
                pass
            
            # 显示进度对话框
            progress_dialog = QProgressDialog("正在启动无人机导航系统，请稍候...", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("系统启动")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setCancelButton(None)
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()
            self._set_mission_phase("launching")

            # 初始化
            self.log_files = {}
            if hasattr(self, "_launch_log_fhs"):
                for _fh in self._launch_log_fhs.values():
                    try:
                        _fh.flush()
                        _fh.close()
                    except Exception:
                        pass
            self._launch_log_fhs = {}
            total_processes = len(processes_list)
            progress_per_process = 90 // total_processes  # 预留10%给最终完成
            unpaused_physics_this_run = False

            # 依次启动每个进程
            for idx, proc_config in enumerate(processes_list):
                proc_name = proc_config.get('name', f'process_{idx}')
                display_name = proc_config.get('display_name', proc_name)
                start_cmd = proc_config.get('start_command', '')
                _explore_root = os.path.dirname(os.path.abspath(__file__))
                start_cmd = (start_cmd or "").replace("__EXPLORE_ROOT__", _explore_root)
                _navrl_root = os.environ.get(
                    "NAVRL_ROOT",
                    os.path.normpath(os.path.join(_explore_root, "..", "NavRL")),
                )
                start_cmd = start_cmd.replace("__NAVRL_ROOT__", _navrl_root)
                wait_seconds = proc_config.get('wait_seconds', 5)
                
                if not start_cmd:
                    print(f"警告: 进程 {proc_name} 没有配置启动命令，跳过")
                    continue

                env_gate = proc_config.get("enabled_if_env")
                if env_gate and not str(os.environ.get(env_gate, "") or "").strip():
                    print(f"[启动] 跳过 {display_name}（未设置环境变量 {env_gate}）")
                    continue

                # 若 Gazebo 已在跑（常见：用户手动开过仿真/上次残留），避免重复启动导致冲突/崩溃。
                if "uav_simulator" in start_cmd and "start.launch" in start_cmd:
                    try:
                        out = subprocess.run(
                            "source /opt/ros/noetic/setup.bash && rosservice list",
                            shell=True,
                            executable="/bin/bash",
                            capture_output=True,
                            text=True,
                            timeout=3,
                        ).stdout
                        if "/gazebo/get_model_state" in (out or ""):
                            print("[启动] 检测到 Gazebo 已运行（/gazebo/get_model_state 存在），跳过重复启动 uav_simulator")
                            self.processes[proc_name] = None
                            progress_dialog.setLabelText(
                                "检测到已有 Gazebo，正在暂停物理直至导航栈就绪…"
                            )
                            QApplication.processEvents()
                            if self._gazebo_pause_physics_blocking(progress_dialog):
                                self._gazebo_paused_for_stack_start = True
                            continue
                    except Exception:
                        pass

                # gzserver 进程里 librospack 常读不到 ROS_PACKAGE_PATH，package:// 会报 uav_simulator not found。
                # 强制传入与本机 catkin_ws 一致的 mesh 目录；xacro 生成 file:// 绝对路径，不依赖 rospack。
                if (
                    "uav_simulator" in start_cmd
                    and "start.launch" in start_cmd
                    and "mesh_prefix:=" not in start_cmd
                ):
                    mesh_dir = _find_uav_simulator_mesh_dir(catkin_ws)
                    if mesh_dir:
                        start_cmd = f"{start_cmd.strip()} mesh_prefix:={mesh_dir}"
                    else:
                        print(
                            f"[启动] 未找到 uav_simulator 网格目录（已检查 {catkin_ws}/src/uav_simulator），"
                            "mesh_prefix 未注入，Gazebo 中机体可能不可见或无法生成"
                        )
                    # 与 uav_simulator/start.launch 的 $(arg spawn_z) 对齐，避免 launch 内仍用 -z0.2 导致出生穿地
                    if "spawn_z:=" not in start_cmd:
                        try:
                            cc_path = os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                "control_config.json",
                            )
                            with open(cc_path, "r", encoding="utf-8") as cf:
                                _cc = json.load(cf)
                            _gz = (_cc.get("gazebo") or {}).get("spawn_xyz") or [0.0, 0.0, 0.72]
                            _sz = float(_gz[2]) if len(_gz) > 2 else 0.72
                            _sz = max(0.35, min(2.5, _sz))
                            start_cmd = f"{start_cmd.strip()} spawn_z:={_sz}"
                        except Exception:
                            start_cmd = f"{start_cmd.strip()} spawn_z:=0.72"
                    try:
                        _launch_paused = rospy.get_param("/myviz/gazebo_launch_world_paused", True)
                    except Exception:
                        _launch_paused = True
                    if _launch_paused and "paused:=" not in start_cmd:
                        start_cmd = f"{start_cmd.strip()} paused:=true"
                        self._uav_sim_launch_paused = True

                gazebo_res_export = ""
                if "uav_simulator" in start_cmd and "start.launch" in start_cmd:
                    gmesh = _find_uav_simulator_mesh_dir(catkin_ws)
                    gurdf = os.path.normpath(
                        os.path.join(catkin_ws, "src", "uav_simulator", "urdf")
                    )
                    if os.path.isdir(gmesh):
                        # 材质/嵌套资源查找；网格主路径以 URDF 中 file:// 为准
                        gazebo_res_export = (
                            f'export GAZEBO_RESOURCE_PATH="{gmesh}:{gurdf}:${{GAZEBO_RESOURCE_PATH:-}}" && '
                        )

                # 计算进度
                base_progress = idx * progress_per_process
                
                # 更新进度显示
                progress_dialog.setLabelText(f"正在启动 {display_name}...")
                progress_dialog.setValue(base_progress)
                QApplication.processEvents()
                
                # 构建完整命令（先 source ROS，再 source 工作空间，确保 roslaunch 可用）
                # 显式把 src 放进 ROS_PACKAGE_PATH：部分环境（Conda/子 shell）下 Gazebo 解析 package:// 会失败
                # Conda 常把 python3 放在 PATH 前面；xacro 使用 #!/usr/bin/env python3，会误用 conda
                # 导致 “No module named 'rospkg'”，robot_description 生成失败。强制优先系统 Python。
                full_cmd = (
                    f"source /opt/ros/noetic/setup.bash && "
                    f"cd {catkin_ws} && "
                    f"source {catkin_ws}/devel/setup.bash && "
                    f'export PATH="/usr/bin:/usr/local/bin:$PATH" && '
                    f"export PYTHONUNBUFFERED=1 && "
                    f'export ROS_PACKAGE_PATH="{catkin_ws}/src:$ROS_PACKAGE_PATH" && '
                    f"{gazebo_res_export}"
                    f"{start_cmd}"
                )
                
                # 启动进程
                if save_log:
                    # 创建日志文件
                    log_file_path = f"{log_dir}/{proc_name}_{timestamp}.log"
                    self.log_files[proc_name] = log_file_path
                    print(f"{proc_name} 日志文件: {log_file_path}")
                    # 勿在 with 内打开后立即关闭：部分环境下子进程日志会写不进或得到 0 字节文件
                    log_fp = open(log_file_path, "w", buffering=1, encoding="utf-8", errors="replace")
                    self._launch_log_fhs[proc_name] = log_fp
                    process = subprocess.Popen(
                        full_cmd,
                        shell=True,
                        stdout=log_fp,
                        stderr=subprocess.STDOUT,
                        executable="/bin/bash",
                        text=True,
                    )
                else:
                    # 不保存日志，也不输出到终端（丢弃输出）
                    process = subprocess.Popen(
                        full_cmd, 
                        shell=True, 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL,
                        executable='/bin/bash', 
                        text=True
                    )
                    
                self.processes[proc_name] = process
                if "run_navrl_navigation" in (start_cmd or "") or proc_name == "navrl_rl_navigation":
                    need_wait_navrl = True
                    self._navrl_popen_wall_time = time.time()

                # 快速健康检查：若启动命令秒退，立即报告而不是继续“假成功”
                self._sleep_ui_responsive(0.8, progress_dialog)
                rc = process.poll()
                if rc is not None and rc != 0:
                    log_hint = ""
                    if save_log and proc_name in self.log_files:
                        log_path = self.log_files[proc_name]
                        log_hint = f"\n\n日志: {log_path}"
                        try:
                            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                                tail = f.read()[-1200:]
                            if tail.strip():
                                log_hint += f"\n\n最近日志:\n{tail}"
                        except Exception:
                            pass
                    raise RuntimeError(
                        f"{display_name} 启动失败（返回码 {rc}）。"
                        f"{log_hint}"
                    )

                # 新起的 Gazebo：尽快暂停物理，避免后续 ~30s 内栈未就绪时仿真把飞机拖走
                if (
                    "uav_simulator" in start_cmd
                    and "start.launch" in start_cmd
                    and self.processes.get(proc_name)
                ):
                    progress_dialog.setLabelText(
                        f"{display_name} 已启动，正在暂停仿真直至导航栈就绪…"
                    )
                    QApplication.processEvents()
                    if self._gazebo_pause_physics_blocking(progress_dialog):
                        self._gazebo_paused_for_stack_start = True

                # 等待指定时间
                for i in range(wait_seconds):
                    progress_dialog.setLabelText(f"正在启动 {display_name}...（等待 {wait_seconds - i} 秒）")
                    wait_progress = base_progress + (i * progress_per_process // wait_seconds)
                    progress_dialog.setValue(min(wait_progress, 90))
                    self._sleep_ui_responsive(1.0, progress_dialog)
            
            # 完成启动：若曾暂停 Gazebo，必须先 unpause 再等待 NavRL（暂停时仿真时间不推进，NavRL 往往无法发布 cmd_vel，会死锁）
            if getattr(self, "_gazebo_paused_for_stack_start", False):
                progress_dialog.setLabelText("正在恢复 Gazebo 仿真（NavRL 初始化需要时间推进）…")
                QApplication.processEvents()
                if self._gazebo_unpause_physics_blocking(progress_dialog):
                    unpaused_physics_this_run = True
                self._gazebo_paused_for_stack_start = False
                progress_dialog.setLabelText("导航栈启动中，等待 NavRL 就绪…")
                QApplication.processEvents()
                self._wait_for_navrl_ready_blocking(progress_dialog, need_wait_navrl)
                if unpaused_physics_this_run:
                    progress_dialog.setLabelText("仿真已运行，正在等待机体离地稳定…")
                    QApplication.processEvents()
                    self._post_unpause_cerlab_stabilize_blocking(progress_dialog, need_wait_navrl)
                    self._gazebo_rescue_if_model_buried_blocking(progress_dialog, need_wait_navrl)

            progress_dialog.setValue(100)
            progress_dialog.setLabelText("导航系统启动完成！")
            QApplication.processEvents()
            self._sleep_ui_responsive(1.0, progress_dialog)
            progress_dialog.close()
            
            # 显示成功消息
            started_count = len([p for p in self.processes.values() if p is not None])
            
            msg = f"无人机导航系统已启动！\n\n启动了 {started_count} 个进程\n"
            if save_log:
                msg += f"所有日志文件保存在:\n{log_dir}"
            else:
                msg += "日志未保存（已禁用）"
                
            notify(self, "启动完成", msg, "info")
            self._set_mission_phase("idle")

            # 启动后（尤其是先启动仿真再启动前端）重试一次控制后端选择
            try:
                QTimer.singleShot(1500, self._ensure_control_backend_ready)
            except Exception:
                pass
            # NavRL：可选在栈就绪后同步一次 goal（默认关，避免未操作却刷 /move_base_simple/goal）
            try:
                if self._nav_behavior_bool(
                    "/myviz/sync_goal_to_odom_on_stack_start",
                    "auto_sync_goal_on_stack_start",
                    False,
                ):
                    self._goal_sync_timer.start(2500)
            except Exception:
                pass

            try:
                delay_ms = int(rospy.get_param("/myviz/home_snapshot_delay_ms", 3200))
            except Exception:
                delay_ms = 3200
            QTimer.singleShot(delay_ms, lambda: self._snapshot_home_position_from_odom(0))

        except Exception as e:
            if 'progress_dialog' in locals() and progress_dialog is not None:
                progress_dialog.close()
            self._set_mission_phase("stopped")
            notify_error(self, "启动错误", f"启动无人机导航系统时出错: {str(e)}")
        finally:
            if getattr(self, "_gazebo_paused_for_stack_start", False):
                try:
                    self._gazebo_unpause_physics_blocking(None)
                except Exception:
                    pass
                self._gazebo_paused_for_stack_start = False

    def _resolve_catkin_workspace(self, config):
        """解析并返回可用 catkin 工作空间目录，不可用则返回空字符串。"""
        try:
            cfg_ws = os.path.expanduser((config or {}).get("catkin_workspace", "~/catkin_ws_dyn"))
            candidates = [
                cfg_ws,
                os.environ.get("CATKIN_WS", ""),
                os.path.expanduser("~/catkin_ws_dyn"),
                os.path.expanduser("~/catkin_ws"),
                os.path.expanduser("~/GUET_UAV_Drone_v2"),
            ]
            # 去重且保序
            uniq = []
            for p in candidates:
                p = (p or "").strip()
                if p and p not in uniq:
                    uniq.append(p)

            def _is_valid_ws(ws):
                return bool(ws) and os.path.isdir(ws) and os.path.isfile(
                    os.path.join(ws, "devel", "setup.bash")
                )

            # 一键启动 uav_simulator 时：勿选用「仅有 devel、却无仿真包」的误配置工作空间
            if _processes_need_uav_simulator(config):
                for ws in uniq:
                    if not _is_valid_ws(ws):
                        continue
                    if os.path.isdir(os.path.join(ws, "src", "uav_simulator")):
                        cfg_has_uav = _is_valid_ws(cfg_ws) and os.path.isdir(
                            os.path.join(cfg_ws, "src", "uav_simulator")
                        )
                        if not cfg_has_uav and ws != cfg_ws:
                            print(
                                f"[启动] 配置路径 {cfg_ws} 下无 src/uav_simulator，"
                                f"已改用含仿真包的工作空间: {ws}"
                            )
                        return ws
                print(
                    "[启动] 警告: 候选路径中均未发现 src/uav_simulator；"
                    "仍将使用首个可用 devel 空间，Gazebo 可能无机体。"
                )

            for ws in uniq:
                if _is_valid_ws(ws):
                    if ws != cfg_ws:
                        print(f"[启动] 配置工作空间不可用，自动回退到: {ws}")
                    return ws
            print(f"[启动] 未找到可用工作空间，已尝试: {uniq}")
            return ""
        except Exception as ex:
            print(f"[启动] 解析工作空间失败: {ex}")
            return ""
    

    

    def monitorAllProcesses(self):
        """监视所有启动的进程状态"""
        try:
            if not hasattr(self, 'processes'):
                return
                
            for name, process in self.processes.items():
                if process is None:
                    continue
                    
                returncode = process.poll()
                if returncode is not None and returncode != 0:
                    # 进程已异常退出
                    try:
                        _, stderr = process.communicate(timeout=0.5)
                    except Exception:
                        stderr = "无法获取错误输出"
                        
                    error_msg = f"{name}进程异常终止，返回代码: {returncode}\n\n错误信息:\n{stderr[:500]}..."
                    notify(self, "进程异常", error_msg, "warning")
                    
                    # 将进程标记为None，避免重复报警
                    self.processes[name] = None
        except Exception as e:
            print(f"监视进程时出错: {str(e)}")

    def checkProcessStatus(self, process, process_name):
        """检查进程状态，如果异常终止则显示错误"""
        try:
            # 检查该定时器是否已停止
            timer_name = f"check_process{process_name.split('系统')[0].strip() if '系统' in process_name else ''}_timer"
            timer_name = timer_name.replace("主", "")  # 处理"主系统"的特殊情况
            timer = getattr(self, timer_name, None)
            if timer is None or not timer.isActive():
                return False  # 定时器已停止，不再进行检查
                
            returncode = process.poll()
            if returncode is not None:  # 进程已结束
                # 先停止定时器，防止重复触发
                if timer:
                    timer.stop()
                
                # 只有在非正常退出且非SIGKILL/SIGTERM情况下才弹出错误
                # -9是SIGKILL, -15是SIGTERM, 这些通常是由停止按钮触发的，不应视为错误
                if returncode != 0 and returncode != -9 and returncode != -15:
                    # 获取错误输出
                    try:
                        _, stderr = process.communicate(timeout=0.5)  # 使用超时避免阻塞
                    except subprocess.TimeoutExpired:
                        stderr = "无法获取错误输出，进程可能仍在运行"
                    except Exception:
                        stderr = "无法获取错误输出"
                    
                    error_msg = f"{process_name}异常终止，返回代码: {returncode}\n\n错误信息:\n{stderr[:500]}..."
                    notify_error(self, "运行错误", error_msg)
                    return False
            return True
        except Exception as e:
            print(f"检查进程状态时出错: {str(e)}")
            if hasattr(self, timer_name) and getattr(self, timer_name).isActive():
                getattr(self, timer_name).stop()  # 发生错误时也停止定时器
            return False
    

    def setupTopicSubscriber(self):
        """初始化话题订阅器和相关回调函数"""
        try:
            # 如果已经有订阅器存在，先关闭它
            if self.topic_subscriber:
                self.topic_subscriber.shutdown()
                self.topic_subscriber = None
            
            # 重置话题数据状态标志
            self.topics_with_data = {
                "battery": False,
                "status": False,
                "odometry": False,
                "velocity": False,
                "camera": False,
                "depth": False,
                "bird_view": False,
                "obstacle_states": False,
            }

            
            # 重置相关UI元素显示状态
            # 如果有电池状态显示，重置为初始状态
            if hasattr(self, 'battery_progress'):
                self.battery_progress.setValue(0)
                self.battery_percentage.setText("---%")
                self.battery_voltage.setText("--.- V")
            
            # 如果有位置显示，重置为初始状态
            if hasattr(self, 'position_value'):
                self.position_value.setText("x: ---m, y: ---m, z: ---m")
            
            # 如果有速度显示，重置为初始状态
            if hasattr(self, 'velocity_value'):
                self.velocity_value.setText("---m/s")
                
            # 如果有状态显示，重置为初始状态
            if hasattr(self, 'status_value'):
                self.status_value.setText("未连接")
                
            # 如果有相机图像显示，清空图像
            if hasattr(self, 'camera_image'):
                self.camera_image = None
                if hasattr(self, 'image_label'):
                    self.image_label.setText("""
                        <div style='
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100%;
                            width: 100%;
                            font-size: 16pt;
                            color: #3498DB;
                            text-align: center;
                            font-weight: bold;
                        '>
                            等待图像数据...
                        </div>
                    """)
                
            # 创建新的订阅器
            self.topic_subscriber = TopicsSubscriber()
            try:
                cfg_ws = (load_processes_config() or {}).get("catkin_workspace") or ""
                cfg_ws = os.path.expanduser(str(cfg_ws).strip())
                if cfg_ws:
                    rospy.set_param("/myviz/catkin_workspace", cfg_ws)
                if hasattr(self.topic_subscriber, "invalidate_drone_mesh_cache"):
                    self.topic_subscriber.invalidate_drone_mesh_cache()
            except Exception:
                pass
            
            # 注册线程安全的回调函数
            self.topic_subscriber.register_callback("battery", self._thread_safe_battery_callback)
            self.topic_subscriber.register_callback("odometry", self._thread_safe_position_callback)
            self.topic_subscriber.register_callback("velocity", self._thread_safe_velocity_callback)
            self.topic_subscriber.register_callback("status", self._thread_safe_status_callback)
            self.topic_subscriber.register_callback("rc_input", self._thread_safe_rc_callback)
            self.topic_subscriber.register_callback("camera", self._thread_safe_camera_callback)
            self.topic_subscriber.register_callback("depth", self._thread_safe_depth_callback)
            self.topic_subscriber.register_callback("attitude", self._thread_safe_attitude_callback)

            self.topic_subscriber.register_callback("obstacle_states", self._thread_safe_obstacle_callback)
            
            # 注意：已移除MAVROS话题回调，使用普通话题替代
            
            print("话题订阅器已启动，将在后台自动连接可用话题...")
            print("注意：已启用线程安全的GUI更新机制，防止段错误")
            self.setupNavigationAuxSubscribers()
            return True
        except Exception as e:
            print(f"初始化话题订阅器失败: {str(e)}")
            self.topic_subscriber = None
            return False

    def setupNavigationAuxSubscribers(self):
        """原局部路径规划 Marker 订阅已移除；预测可视化请直接使用 RViz。"""

    def setupManualController(self):
        """初始化手动控制器"""
        try:
            # 新控制后端（px4ctrl / mavros offboard），用于“真操控”，并避免假成功
            self.control_backend = None
            self.control_backend_name = "none"
            cfg_path = os.path.join(os.path.dirname(__file__), "control_config.json")
            if create_backend is not None and os.path.exists(cfg_path):
                b, name = create_backend(rospy, cfg_path)
                self.control_backend = b
                self.control_backend_name = name
                if b is not None:
                    print(f"控制后端已启用: {name}")
                    # 旧手动控制器仍保留，但优先走 control_backend
                    return True
                print("未能自动选择控制后端（请检查 ROS master/话题，或编辑 control_config.json 指定 backend）")

            if initialize_manual_controller and get_manual_controller:
                # 初始化手动控制器
                if initialize_manual_controller():
                    self.manual_controller = get_manual_controller()
                    print("手动控制器已成功初始化")
                    return True
                else:
                    print("手动控制器初始化失败")
                    self.manual_controller = None
                    return False
            else:
                print("手动控制器模块未正确导入")
                self.manual_controller = None
                return False
        except Exception as e:
            print(f"初始化手动控制器时出错: {str(e)}")
            self.manual_controller = None
            self.control_backend = None
            self.control_backend_name = "none"
            return False

    def _ensure_idle_hold_timer_running(self):
        try:
            if getattr(self, "_mission_phase", "") != "idle":
                return
            if not self._is_stack_running():
                return
            if not self._nav_behavior_bool(
                "/myviz/publish_hold_goal_on_idle",
                "auto_publish_hold_goal_on_idle",
                False,
            ):
                return
            period = float(rospy.get_param("/myviz/idle_hold_goal_period_sec", 1.5))
            if period <= 0:
                return
            ht = getattr(self, "_idle_hold_timer", None)
            if ht is None or ht.isActive():
                return
            ht.setInterval(max(500, int(1000 * period)))
            ht.start()
        except Exception:
            pass

    def _get_hold_goal_publishers(self):
        """navigation_config 中 goal_topics 的持久发布者（不依赖是否打开航点对话框）。"""
        if getattr(self, "_hold_goal_publishers", None):
            return self._hold_goal_publishers
        nav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "navigation_config.json")
        nav_cfg = {}
        if os.path.isfile(nav_path):
            with open(nav_path, "r", encoding="utf-8") as nf:
                nav_cfg = json.load(nf)
        goal_topics = nav_cfg.get("goal_topics") or ["/move_base_simple/goal"]
        pubs = {}
        for gt in goal_topics:
            t = (gt or "").strip()
            if not t:
                continue
            try:
                pubs[t] = rospy.Publisher(t, PoseStamped, queue_size=10)
            except Exception:
                pass
        try:
            rospy.sleep(0.1)
        except Exception:
            pass
        self._hold_goal_publishers = pubs if pubs else None
        return self._hold_goal_publishers

    def _on_waypoint_navigation_started(self, _wps):
        """用户开始航点导航时取消「同步 goal」，避免晚到的同步把 (5,5,3) 覆盖成当前位导致策略原地不动。"""
        try:
            if getattr(self, "_goal_sync_timer", None) and self._goal_sync_timer.isActive():
                self._goal_sync_timer.stop()
        except Exception:
            pass
        self._set_mission_phase("waypoint")
        try:
            nav_cfg = self._navigation_config_dict()
            if nav_cfg.get("clear_flight_path_on_navigation_start", True):
                ts = getattr(self, "topic_subscriber", None)
                if ts is not None and hasattr(ts, "clear_flight_path"):
                    ts.clear_flight_path()
        except Exception:
            pass

    def _on_waypoint_navigation_ended(self):
        if getattr(self, "_mission_phase", "") == "waypoint":
            self._set_mission_phase("idle")

    def _idle_refresh_navigation_goal(self):
        """待机且未在航点导航时，把导航目标刷成当前位，避免策略层仍追远处 goal。"""
        try:
            if getattr(self, "_mission_phase", "") != "idle":
                return
            if not self._is_stack_running():
                return
            if not self._nav_behavior_bool(
                "/myviz/publish_hold_goal_on_idle",
                "auto_publish_hold_goal_on_idle",
                False,
            ):
                return
            wd = getattr(self, "waypoint_dialog", None)
            if wd is not None and getattr(wd, "is_navigating", False):
                return
            self._sync_nav_goal_to_current_odom_once(quiet=True, reason="idle")
        except Exception:
            pass

    def _sync_nav_goal_to_current_odom_once(self, quiet=False, reason="stack"):
        """
        用当前里程计发布 move_base 系 goal（可选）。
        默认不在栈启动/待机/NavRL 预检时自动发布；见 navigation_config.json 与 /myviz/sync_goal_to_odom_on_stack_start 等。
        """
        try:
            if reason == "stack":
                if not self._nav_behavior_bool(
                    "/myviz/sync_goal_to_odom_on_stack_start",
                    "auto_sync_goal_on_stack_start",
                    False,
                ):
                    return
            elif reason == "preflight":
                if not self._nav_behavior_bool(
                    "/myviz/navrl_preflight_hold_goal",
                    "navrl_preflight_hold_goal",
                    False,
                ):
                    return
            elif reason == "idle":
                if not self._nav_behavior_bool(
                    "/myviz/publish_hold_goal_on_idle",
                    "auto_publish_hold_goal_on_idle",
                    False,
                ):
                    return
            wd = getattr(self, "waypoint_dialog", None)
            if wd is not None and getattr(wd, "is_navigating", False):
                rospy.logdebug("跳过陈旧 goal 同步：航点导航进行中")
                return
            ts = getattr(self, "topic_subscriber", None)
            if ts is None or not ts.has_fresh_data("odometry", 5.0):
                return
            odom = ts.get_data("odometry") or {}
            pos = odom.get("position") or {}
            prev_xyz = getattr(self, "_hold_goal_last_accepted_xyz", None)
            try:
                mx = float(rospy.get_param("/myviz/hold_goal_max_xy_jump_m", 9.0))
                # 默认勿过大：曾用 3.0 时「z 0.9→0」的坠地脏帧不会触发 z_jump；与 utils.z_plunge 双保险
                mz = float(rospy.get_param("/myviz/hold_goal_max_z_jump_m", 0.85))
                oxy = float(rospy.get_param("/myviz/hold_goal_origin_snap_xy_m", 0.12))
                mpn = float(rospy.get_param("/myviz/hold_goal_origin_snap_min_prev_xy_norm_m", 3.0))
                zpp = float(rospy.get_param("/myviz/hold_goal_z_plunge_prev_min_m", 0.55))
                zpn = float(rospy.get_param("/myviz/hold_goal_z_plunge_new_max_m", 0.18))
                zpd = float(rospy.get_param("/myviz/hold_goal_z_plunge_min_drop_m", 0.95))
                zpr = float(rospy.get_param("/myviz/hold_goal_z_plunge_min_prev_xy_norm_m", 1.25))
            except Exception:
                mx, mz, oxy, mpn = 9.0, 0.85, 0.12, 3.0
                zpp, zpn, zpd, zpr = 0.55, 0.18, 0.95, 1.25
            skip_glitch, glitch_why = hold_goal_odom_glitch_should_skip(
                pos,
                prev_xyz,
                max_xy_jump_m=mx,
                max_z_jump_m=mz,
                origin_snap_xy=oxy,
                min_prev_xy_norm_for_origin_snap=mpn,
                z_plunge_prev_min=zpp,
                z_plunge_new_max=zpn,
                z_plunge_min_drop_m=zpd,
                z_plunge_min_prev_xy_norm_m=zpr,
            )
            if skip_glitch:
                if quiet:
                    rospy.logwarn_throttle(
                        4.0,
                        "myviz: 跳过导航目标同步（里程计异常，避免把策略拉向错误点）: %s",
                        glitch_why,
                    )
                else:
                    rospy.logwarn(
                        "myviz: 跳过导航目标同步（里程计异常，避免把策略拉向错误点）: %s",
                        glitch_why,
                    )
                return
            nav_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "navigation_config.json")
            nav_cfg = {}
            if os.path.isfile(nav_path):
                with open(nav_path, "r", encoding="utf-8") as nf:
                    nav_cfg = json.load(nf)
            goal_topics = nav_cfg.get("goal_topics") or ["/move_base_simple/goal"]
            frame_id = (nav_cfg.get("goal_frame_id") or "map").strip()
            if nav_cfg.get("sync_goal_frame_to_odom", False):
                lf = (odom.get("frame_id") or "").strip()
                if lf:
                    frame_id = lf
            hold = PoseStamped()
            hold.header.frame_id = frame_id
            hold.header.stamp = rospy.Time.now()
            hold.pose.position.x = float(pos.get("x", 0.0))
            hold.pose.position.y = float(pos.get("y", 0.0))
            hold.pose.position.z = float(pos.get("z", 0.0))
            try:
                z_floor_pub = float(
                    rospy.get_param(
                        "/myviz/hold_goal_publish_min_z_m",
                        float(nav_cfg.get("hold_goal_publish_min_z_m", 0.45)),
                    )
                )
            except Exception:
                z_floor_pub = float(nav_cfg.get("hold_goal_publish_min_z_m", 0.45))
            if hold.pose.position.z < z_floor_pub:
                hold.pose.position.z = z_floor_pub
            ort = odom.get("orientation") or {}
            if isinstance(ort, dict) and all(k in ort for k in ("x", "y", "z", "w")):
                hold.pose.orientation.x = float(ort.get("x", 0.0))
                hold.pose.orientation.y = float(ort.get("y", 0.0))
                hold.pose.orientation.z = float(ort.get("z", 0.0))
                hold.pose.orientation.w = float(ort.get("w", 1.0))
            else:
                hold.pose.orientation.w = 1.0
            pubs = getattr(wd, "_goal_publishers", None) if wd is not None else None
            if not pubs:
                pubs = self._get_hold_goal_publishers()
            if pubs:
                try:
                    for pub in pubs.values():
                        pub.publish(hold)
                except Exception:
                    pass
            else:
                for gt in goal_topics:
                    try:
                        pub = rospy.Publisher(gt, PoseStamped, queue_size=1)
                        rospy.sleep(0.06)
                        pub.publish(hold)
                    except Exception:
                        pass
            if quiet:
                rospy.logdebug_throttle(
                    20.0,
                    "待机保持：已用当前位置同步导航目标 -> %s",
                    ", ".join(goal_topics),
                )
            else:
                rospy.loginfo(
                    "已用当前位置同步导航目标（清除陈旧 goal）-> %s",
                    ", ".join(goal_topics),
                )
            try:
                self._hold_goal_last_accepted_xyz = (
                    float(pos.get("x", 0.0)),
                    float(pos.get("y", 0.0)),
                    float(pos.get("z", 0.0)),
                )
            except Exception:
                pass
        except Exception as ex:
            rospy.logdebug("sync_nav_goal_to_odom: %s", ex)

    def _ensure_control_backend_ready(self):
        """按当前 ROS 话题状态重试控制后端选择（仿真后启动时常见）。"""
        try:
            if hasattr(self, "control_backend") and self.control_backend:
                return True
            cfg_path = os.path.join(os.path.dirname(__file__), "control_config.json")
            if create_backend is None or not os.path.exists(cfg_path):
                return False
            b, name = create_backend(rospy, cfg_path)
            self.control_backend = b
            self.control_backend_name = name
            if b is not None:
                print(f"控制后端重试成功: {name}")
                return True
            return False
        except Exception as e:
            print(f"重试控制后端失败: {e}")
            return False

    def _is_vehicle_connected_for_control(self):
        """
        控制可用判据：
        1) 若 /mavros/state 有效，则要求 connected=True；
        2) 若无 MAVROS，也允许仿真链路（至少 odometry 或 camera 有效）。
        """
        try:
            if not hasattr(self, "topic_subscriber") or self.topic_subscriber is None:
                return False
            ts = self.topic_subscriber

            if ts.is_topic_active("status") and ts.has_fresh_data("status", 2.0):
                st = ts.get_data("status") or {}
                if bool(st.get("connected", False)):
                    return True

            return ts.has_fresh_data("odometry", 2.0) or ts.has_fresh_data("camera", 2.0)
        except Exception:
            return False

    def _guard_manual_control(self, action_name: str) -> bool:
        if self._is_vehicle_connected_for_control():
            return True
        notify(
            self,
            "控制不可用",
            f"当前未连接到可控飞行链路，已阻止{action_name}。请先确认连接状态为已连接。",
            "warning",
        )
        return False


    def selectOdomTopic(self):
        """选择odom话题"""
        try:
            if self.log_window and hasattr(self.log_window, 'logger_widget'):
                # 查找/converted_odom话题
                odom_topic = "/converted_odom"
                combo = self.log_window.logger_widget.topic_combo
                
                # 寻找话题
                index = combo.findText(odom_topic)
                if index >= 0:
                    combo.setCurrentIndex(index)
                    # 点击打印按钮开始记录
                    self.log_window.logger_widget.log_btn.click()
                else:
                    print(f"找不到话题 {odom_topic}，等待话题可用")
                    # 再次尝试
                    QTimer.singleShot(2000, self.selectOdomTopic)
        except Exception as e:
            print(f"选择odom话题时出错: {str(e)}")

    def switchToRGBImage(self):
        """切换到RGB图像模式"""
        print("切换到RGB图像模式")
        if hasattr(self, "rgb_button") and self.rgb_button:
            self.rgb_button.setChecked(True)
        if hasattr(self, "depth_button") and self.depth_button:
            self.depth_button.setChecked(False)
        self.current_image_mode = "rgb"
        # 立即更新显示
        self.updateImageDisplay()

    def switchToDepthImage(self):
        """切换到深度图像模式"""
        print("切换到深度图像模式")
        if hasattr(self, "rgb_button") and self.rgb_button:
            self.rgb_button.setChecked(False)
        if hasattr(self, "depth_button") and self.depth_button:
            self.depth_button.setChecked(True)
        self.current_image_mode = "depth"
        # 立即更新显示
        self.updateImageDisplay()
    
    def updateDepthImage(self, depth_data):
        """处理深度图像更新 - 优化版本，确保实时更新"""
        try:
            if not depth_data or depth_data["image"] is None:
                return

            # 验证深度图像数据的有效性
            image = depth_data["image"]
            if not isinstance(image, np.ndarray):
                print("深度图像数据不是numpy数组")
                return

            if image.size == 0:
                print("深度图像数据为空")
                return

            now = time.monotonic()
            if now - self._last_right_depth_emit < self._right_panel_image_min_dt:
                return
            self._last_right_depth_emit = now
            self.depth_image = image.copy()

            if self.current_image_mode == "depth" and hasattr(self, "image_label") and self.image_label:
                if pyqtSignal is not None and hasattr(self, "image_update_signal"):
                    self.image_update_signal.emit()
                else:
                    QTimer.singleShot(0, self.updateImageDisplay)

        except Exception as e:
            print(f"处理深度图像更新时出错: {str(e)}")
            import traceback
            traceback.print_exc()

    def updateBirdViewImage(self, bird_view_data):
        """鸟瞰图 UI 已移除；保留空实现以防旧代码路径调用。"""
        return

    def updateBirdViewDisplay(self):
        return

    def _show_bird_view_placeholder(self, message):
        return

    def onResize(self, event):
        """窗口大小变化时调整组件尺寸"""
        try:
            # 获取当前窗口大小
            window_height = self.height()
            window_width = self.width()

            # 只有在窗口大小显著变化时才重新计算（避免频繁调整）
            if not hasattr(self, '_last_window_size'):
                self._last_window_size = (window_width, window_height)
                should_recalculate = True
            else:
                last_width, last_height = self._last_window_size
                width_diff = abs(window_width - last_width)
                height_diff = abs(window_height - last_height)
                # 只有当宽度或高度变化超过50px时才重新计算
                should_recalculate = width_diff > 50 or height_diff > 50

            if should_recalculate:
                # 更新记录的窗口大小
                self._last_window_size = (window_width, window_height)

                # 重新计算自适应尺寸
                old_screen_width = self.screen_width
                old_screen_height = self.screen_height
                self.screen_width = window_width
                self.screen_height = window_height
                self.calculateAdaptiveSizes()

                # 只有在尺寸真正改变时才更新组件
                if (old_screen_width != self.screen_width or old_screen_height != self.screen_height):
                    # 动态调整侧边栏宽度
                    if hasattr(self, 'left_sidebar'):
                        self.left_sidebar.setFixedWidth(self.adaptive_left_width)

                    if hasattr(self, 'right_sidebar'):
                        self.right_sidebar.setFixedWidth(self.adaptive_right_width)

                    # 重新设置分割器尺寸
                    if hasattr(self, 'main_splitter'):
                        # 使用定时器延迟调整，避免与侧边栏动画冲突
                        QTimer.singleShot(100, self._setAdaptiveSplitterSizes)

                    # 延迟更新图像尺寸，确保分割器调整完成后再更新
                    QTimer.singleShot(200, self.updateImageSizes)
                    # 延迟更新悬浮窗口位置
                    QTimer.singleShot(300, self._update_overlay_positions)

            # 小窗口模式下简化功能组标题，避免截断
            if hasattr(self, 'function_group'):
                if window_width < 1600:
                    self.function_group.setTitle("🎮 控制中心")
                else:
                    self.function_group.setTitle("🎮 控制中心")

            # 调用原始的resizeEvent
            QMainWindow.resizeEvent(self, event)
        except Exception as e:
            print(f"调整窗口大小时出错: {str(e)}")
            # 确保原始事件被处理
            QMainWindow.resizeEvent(self, event)
    





    def stopDroneSystem(self):
        """停止无人机系统"""
        try:
            if not confirm(
                self,
                "stop_system",
                "确认停止",
                "确定要停止所有无人机系统进程吗？",
                default_no=True,
            ):
                return

            proc_cfg = load_processes_config()
                
            # 立即停止所有进程监控定时器，避免重复弹出错误消息
            for timer_attr in ['check_process_timer', 'check_process2_timer', 'check_process3_timer', 'process_monitor_timer']:
                if hasattr(self, timer_attr):
                    timer = getattr(self, timer_attr)
                    if timer and timer.isActive():
                        timer.stop()
                        print(f"已停止{timer_attr}")
            
            # 显示进度对话框
            progress_dialog = QProgressDialog("正在停止无人机系统...", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("系统停止")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setCancelButton(None)  # 禁用取消按钮
            progress_dialog.setValue(10)
            progress_dialog.show()
            QApplication.processEvents()  # 确保对话框显示出来
            
            # 停止流程中保留前端订阅器与 ROS 节点，避免后续“再次启动后未连接”
            progress_dialog.setLabelText("正在准备停止进程...")
            progress_dialog.setValue(30)
            QApplication.processEvents()
            
            # 逐个关闭之前启动的进程（顺序：processes_config 中 order 逆序 + 配置外仍存活的 name）
            if hasattr(self, 'processes') and self.processes:
                running = {k: v for k, v in self.processes.items() if v is not None}
                cfg_names = [
                    p.get("name")
                    for p in proc_cfg.get("processes", [])
                    if p.get("name")
                ]
                stop_order = list(reversed(cfg_names))
                seen = set()
                ordered_stop = []
                for n in stop_order:
                    if n in running and n not in seen:
                        ordered_stop.append(n)
                        seen.add(n)
                for n in running:
                    if n not in seen:
                        ordered_stop.append(n)
                        seen.add(n)

                total_processes = len(ordered_stop)
                progress_per_process = 50 / max(total_processes, 1)  # 在30%-80%的进度范围内分配
                current_progress = 30
                
                for process_name in ordered_stop:
                    if process_name in self.processes and self.processes[process_name]:
                        progress_dialog.setLabelText(f"正在停止{process_name}进程...")
                        progress_dialog.setValue(int(current_progress))
                        QApplication.processEvents()
                        
                        try:
                            # 终止进程
                            self.processes[process_name].terminate()
                            # 给进程一点时间自行退出
                            start_time = time.time()
                            while time.time() - start_time < 2:  # 最多等待2秒
                                if self.processes[process_name].poll() is not None:
                                    # 进程已结束
                                    break
                                time.sleep(0.1)
                            
                            # 如果进程仍未退出，强制杀死
                            if self.processes[process_name].poll() is None:
                                self.processes[process_name].kill()
                            
                            # 等待进程完全退出
                            self.processes[process_name].wait(timeout=1)
                            print(f"已停止{process_name}进程")
                        except Exception as e:
                            print(f"停止{process_name}进程时出错: {str(e)}")
                        
                        current_progress += progress_per_process
                
                # 清空进程列表
                self.processes = {}
                if hasattr(self, "_launch_log_fhs") and self._launch_log_fhs:
                    for _fh in list(self._launch_log_fhs.values()):
                        try:
                            _fh.flush()
                            _fh.close()
                        except Exception:
                            pass
                    self._launch_log_fhs = {}
                
                progress_dialog.setValue(60)
                QApplication.processEvents()
            
            # 使用强大的终止机制，确保所有相关进程都被终止
            progress_dialog.setLabelText("正在终止所有相关进程...")
            progress_dialog.setValue(70)
            QApplication.processEvents()
            
            # 按 processes_config 的 stop_pattern/start_command 生成 pkill 模式；空则回退 PROCESS_PATTERNS
            process_patterns = []
            for p in proc_cfg.get("processes", []):
                pat = (p.get("stop_pattern") or p.get("start_command") or "").strip()
                if pat and pat not in process_patterns:
                    process_patterns.append(pat)
            if not process_patterns:
                process_patterns = list(PROCESS_PATTERNS)
            
            # 使用pkill强制终止每个模式的进程
            for i, pattern in enumerate(process_patterns):
                progress_value = 70 + (i * 10 // len(process_patterns))
                progress_dialog.setValue(progress_value)
                progress_dialog.setLabelText(f"正在终止进程: {pattern}...")
                QApplication.processEvents()
                
                try:
                    # 使用pgrep检查进程是否存在
                    check_process = subprocess.run(
                        f"pgrep -f \"{pattern}\"", 
                        shell=True, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    
                    if check_process.returncode == 0:  # 进程存在
                        # 使用pkill -9 强制终止
                        kill_cmd = f"pkill -9 -f \"{pattern}\""
                        subprocess.run(kill_cmd, shell=True)
                        print(f"已终止进程：{pattern}")
                    else:
                        print(f"未找到进程：{pattern}")
                except Exception as e:
                    print(f"终止进程 {pattern} 时出错: {str(e)}")
            
            progress_dialog.setValue(80)
            progress_dialog.setLabelText("保留前端ROS连接，仅停止仿真相关进程...")
            QApplication.processEvents()
            print("停止流程: 已跳过全局 rosnode 清理，保留前端连接能力")
                
            progress_dialog.setValue(90)
            QApplication.processEvents()
            
            # 实际停止已在上方完成；旧版此处用 DummyProcess 读管道会导致 poll/stdout 不存在而崩溃
            stdout = ""
            stderr = ""
            stop_return_code = 0
            
            # 更新进度到100%
            progress_dialog.setValue(100)
            progress_dialog.setLabelText("停止完成")
            QApplication.processEvents()
            time.sleep(0.5)  # 短暂延迟以显示完成状态
            progress_dialog.close()
            
            # 简化UI流程，使用简单的消息框而不是复杂的对话框
            # 在控制台记录所有输出，但不在UI中显示详细信息
            print("停止流程 UI 收尾完成，返回码:", stop_return_code)
            if stdout:
                print("脚本输出:", stdout.strip())
            if stderr:
                print("错误信息:", stderr.strip())
            
            # 只显示简单的成功消息，减少UI阻塞
            if stop_return_code == 0:
                message = "✅ 无人机系统进程已停止"
                notify(self, "停止完成", message, "info")
            else:
                message = "⚠️ 部分进程可能未正常停止，请查看控制台日志"
                notify(self, "停止警告", message, "warning")
            
            # 无论成功与否，都重置UI状态，释放所有资源
            # 更新UI状态，显示系统已停止
            if hasattr(self, 'position_label'):
                self.position_label.setText("Position: (系统已停止)")
            
            # 停止后不关闭订阅器：允许仿真重启后自动重新感知并恢复“已连接”
            if not getattr(self, "topic_subscriber", None):
                try:
                    self.setupTopicSubscriber()
                except Exception as ex:
                    print(f"停止后重建话题订阅器失败: {ex}")
            
            # 重置所有UI标签到初始状态
            if hasattr(self, 'altitude_label'):
                self.altitude_label.setText("-- m")
            
            if hasattr(self, 'ground_speed_label'):
                self.ground_speed_label.setText("-- m/s")
            
            if hasattr(self, 'mode_label'):
                self.mode_label.setText("未连接")
            
            if hasattr(self, 'connection_label'):
                self.connection_label.setText("未连接")
                # 不设置字体大小，保持卡片的原始字体设置
                self.connection_label.setStyleSheet("""
                    QLabel {
                        color: #E74C3C;
                        font-weight: bold;
                        background: transparent;
                        border: none;
                        padding: 0px;
                        margin: 0px;
                    }
                """)
            
            if hasattr(self, 'battery_status_label'):
                self.battery_status_label.setText("--%")
            
            if hasattr(self, 'voltage_label'):
                self.voltage_label.setText("-- V")
            
            if hasattr(self, 'pitch_label'):
                self.pitch_label.setText("0.00°")
            
            if hasattr(self, 'roll_label'):
                self.roll_label.setText("0.00°")
            
            if hasattr(self, 'yaw_label'):
                self.yaw_label.setText("0.00°")
            
            # 重置电池图标
            if hasattr(self, 'battery_icon_label'):
                self.battery_icon_label.setPixmap(QPixmap(":/images/icons/battery_100.svg").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            # 重置图像显示区域状态
            if hasattr(self, 'image_label'):
                self.image_label.setText("<div style='font-size: 16pt; color: #3498DB; text-align: center; margin-top: 200px;'>系统已停止，请点击\"一键启动\"启动后台程序</div>")

            self._last_altitude_m = None
            self._last_mavros_status = {}
            self._set_mission_phase("stopped")
            self._hold_goal_publishers = None
            if hasattr(self, "takeoff_state_label"):
                self.takeoff_state_label.setText("未知")
            if hasattr(self, "comm_monitor_text") and self.comm_monitor_text:
                self.comm_monitor_text.setHtml(
                    "<p style='color:#BDC3C7;font-size:13px;'>系统已停止。再次一键启动后将更新本区域。</p>"
                )
            if hasattr(self, "obstacle_warning_label") and self.obstacle_warning_label:
                self.obstacle_warning_label.setText(
                    "<div style='font-size:11pt;color:#95A5A6;padding:8px;'>系统已停止，避障摘要不可用。</div>"
                )

            # 清除图像数据
            self.camera_image = None
            self.depth_image = None
            if hasattr(self, "return_home_goal_timer") and self.return_home_goal_timer:
                try:
                    self.return_home_goal_timer.stop()
                except Exception:
                    pass
            
            # 重置话题数据状态标志
            self.topics_with_data = {
                "battery": False,
                "status": False,
                "odometry": False,
                "velocity": False,
                "camera": False,
                "depth": False,
                "bird_view": False,
                "obstacle_states": False,
            }           

        except Exception as e:
            if 'progress_dialog' in locals() and progress_dialog is not None:
                try:
                    progress_dialog.close()
                except:
                    pass
            error_msg = f"停止无人机系统时出错: {str(e)}"
            notify_error(self, "停止失败", error_msg)

    def publishNavigationGoal(self):
        """打开目标点设置对话框"""
        try:
            if WaypointDialog is None:
                notify_error(self, "模块错误", "无法加载目标点对话框模块")
                return
            
            # 如果对话框已存在，显示并激活它
            if hasattr(self, 'waypoint_dialog') and self.waypoint_dialog is not None:
                self.waypoint_dialog.show()
                self.waypoint_dialog.raise_()
                self.waypoint_dialog.activateWindow()
                try:
                    self.waypoint_dialog.navigationEnded.disconnect(self._on_waypoint_navigation_ended)
                except Exception:
                    pass
                try:
                    self.waypoint_dialog.navigationEnded.connect(self._on_waypoint_navigation_ended)
                except Exception:
                    pass
            else:
                # 创建新的目标点对话框（非模态）
                self.waypoint_dialog = WaypointDialog(self, self.topic_subscriber)
                try:
                    self.waypoint_dialog.navigationStarted.connect(
                        self._on_waypoint_navigation_started
                    )
                    self.waypoint_dialog.navigationEnded.connect(self._on_waypoint_navigation_ended)
                except Exception:
                    pass
                self.waypoint_dialog.show()
            
        except Exception as e:
            notify_error(self, "对话框错误", f"打开目标点对话框时出错: {str(e)}")

    
    def _backend_uses_cerlab_quad_topics(self):
        """NavRL/CERLAB 仿真机体话题为 /CERLAB/quadcopter/*（含 navrl_passive），与 px4ctrl/quadrotor_msgs 不同。"""
        bn = (getattr(self, "control_backend_name", "") or "").lower()
        return "navrl" in bn or "cerlab" in bn

    def _suspend_waypoint_timers_for_return(self):
        """返航时停掉航点对话框里可能仍在刷的 CERLAB/航点定时器，避免与返航/NavRL 抢目标。"""
        wd = getattr(self, "waypoint_dialog", None)
        if not wd:
            return
        try:
            wd.is_navigating = False
            if getattr(wd, "fsm_check_timer", None):
                wd.fsm_check_timer.stop()
            if getattr(wd, "_cerlab_goal_timer", None):
                wd._cerlab_goal_timer.stop()
            wd._cerlab_goal_msg = None
        except Exception:
            pass

    def _start_navrl_gradual_return(self, hx, hy, hz):
        """NavRL 控飞：仅用 move_base 目标做平滑返航（插值），不再用 CERLAB setpoint 瞬移。"""
        nav_cfg = self._navigation_config_dict()
        goal_topics = nav_cfg.get("goal_topics") or ["/move_base_simple/goal"]
        frame_id = self._navigation_goal_frame_id()
        wa = nav_cfg.get("waypoint_advance") or {}
        self._configure_return_home_detection(wa)
        self._return_home_saw_exec = False
        self._return_home_start_time = time.time()
        self._return_home_target = {"x": float(hx), "y": float(hy), "z": float(hz)}

        if not hasattr(self, "_navrl_return_goal_pubs") or self._navrl_return_goal_pubs is None:
            self._navrl_return_goal_pubs = {
                t: rospy.Publisher(t, PoseStamped, queue_size=10) for t in goal_topics
            }
            rospy.sleep(0.2)

        odom = None
        if hasattr(self, "topic_subscriber") and self.topic_subscriber:
            odom = self.topic_subscriber.get_data("odometry")
        sx, sy, sz = 0.0, 0.0, float(hz)
        if odom and odom.get("position"):
            p = odom["position"]
            sx = float(p.get("x", 0.0))
            sy = float(p.get("y", 0.0))
            sz = float(p.get("z", hz))
        dist = math.sqrt((sx - hx) ** 2 + (sy - hy) ** 2 + (sz - hz) ** 2)
        # 返航不要太快：时间下限 + 按距离限速（约 0.28~0.4 m/s 等效）
        dur = max(14.0, min(55.0, dist / 0.32))
        self._return_home_navrl = {
            "sx": sx,
            "sy": sy,
            "sz": sz,
            "hx": float(hx),
            "hy": float(hy),
            "hz": float(hz),
            "t0": time.time(),
            "T": dur,
            "frame": frame_id,
            "pubs": list(self._navrl_return_goal_pubs.values()),
        }
        self._return_home_setpoint_pub = None
        self._return_home_goal_msg = None

        if not hasattr(self, "return_home_goal_timer") or self.return_home_goal_timer is None:
            self.return_home_goal_timer = QTimer()
            self.return_home_goal_timer.timeout.connect(self._republish_return_home_goal)
        if not self.return_home_goal_timer.isActive():
            self.return_home_goal_timer.start(100)

        notify(self, "返航中", "NavRL 平滑返航中（已同步 move_base 目标）…", "info")
        self.return_home_timer = QTimer()
        self.return_home_timer.timeout.connect(self.checkReturnHomeStatus)
        self.return_home_timer.start(500)

    def _tick_navrl_return_goal_publish(self):
        d = getattr(self, "_return_home_navrl", None)
        if not d or not d.get("pubs"):
            return
        from geometry_msgs.msg import PoseStamped

        t = min(1.0, max(0.0, (time.time() - d["t0"]) / max(d["T"], 1e-3)))
        gx = (1.0 - t) * d["sx"] + t * d["hx"]
        gy = (1.0 - t) * d["sy"] + t * d["hy"]
        gz = (1.0 - t) * d["sz"] + t * d["hz"]
        msg = PoseStamped()
        msg.header.frame_id = d["frame"]
        msg.header.stamp = rospy.Time.now()
        msg.pose.position.x = gx
        msg.pose.position.y = gy
        msg.pose.position.z = gz
        msg.pose.orientation.w = 1.0
        for pub in d["pubs"]:
            pub.publish(msg)

    def returnToHome(self):
        """一键返航功能 - CERLAB: setpoint_pose 回到 home(默认原点) 并降落；其他链路保持原逻辑"""
        try:
            hx, hy, hz = self._resolve_return_home_xyz()

            if not confirm(
                self,
                "return_home",
                "确认返航",
                f"确定要返航并降落吗？\n返航点: ({hx:.2f}, {hy:.2f}, {hz:.2f})",
                default_no=True,
            ):
                return

            self._set_mission_phase("returning")
            nav_cfg = self._navigation_config_dict()
            self._configure_return_home_detection(nav_cfg.get("waypoint_advance") or {})

            # NavRL：用 move_base 目标插值返航，避免 CERLAB setpoint 与 cmd_vel 冲突导致「瞬移」且 NavRL 内部 goal 不更新
            if self._backend_uses_cerlab_quad_topics() and "navrl" in (
                getattr(self, "control_backend_name", "") or ""
            ).lower():
                self._suspend_waypoint_timers_for_return()
                self._start_navrl_gradual_return(hx, hy, hz)
                return

            # 纯 CERLAB 位置直控返航
            if self._backend_uses_cerlab_quad_topics():
                from std_msgs.msg import Bool, Empty
                setpoint_pub = rospy.Publisher("/CERLAB/quadcopter/setpoint_pose", PoseStamped, queue_size=10)
                posctrl_pub = rospy.Publisher("/CERLAB/quadcopter/posctrl", Bool, queue_size=1)
                velmode_pub = rospy.Publisher("/CERLAB/quadcopter/vel_mode", Bool, queue_size=1)
                takeoff_pub = rospy.Publisher("/CERLAB/quadcopter/takeoff", Empty, queue_size=1)
                rospy.sleep(0.2)
                try:
                    takeoff_pub.publish(Empty())
                    velmode_pub.publish(Bool(data=False))
                    posctrl_pub.publish(Bool(data=True))
                except Exception:
                    pass

                goal_msg = PoseStamped()
                goal_msg.header.frame_id = self._navigation_goal_frame_id()
                goal_msg.header.stamp = rospy.Time.now()
                goal_msg.pose.position.x = hx
                goal_msg.pose.position.y = hy
                goal_msg.pose.position.z = hz
                goal_msg.pose.orientation.w = 1.0
                setpoint_pub.publish(goal_msg)
                # CERLAB 返航目标持续刷新（单次 setpoint 在部分版本不会持续执行）
                self._return_home_setpoint_pub = setpoint_pub
                self._return_home_goal_msg = goal_msg
                if not hasattr(self, "return_home_goal_timer") or self.return_home_goal_timer is None:
                    self.return_home_goal_timer = QTimer()
                    self.return_home_goal_timer.timeout.connect(self._republish_return_home_goal)
                if not self.return_home_goal_timer.isActive():
                    self.return_home_goal_timer.start(100)  # 10Hz

                # 返航监控目标点（供距离兜底使用）；位置直控用严格 3D 距离
                self._return_home_target = {"x": hx, "y": hy, "z": hz}
                self._return_home_dist_mode = "3d"
                self._return_home_dist_thresh = 0.4
                self._return_home_start_time = time.time()
                self._return_home_saw_exec = False
                notify(self, "返航中", "无人机正在返航（CERLAB 位置控制）…", "info")
                self.return_home_timer = QTimer()
                self.return_home_timer.timeout.connect(self.checkReturnHomeStatus)
                self.return_home_timer.start(500)
                return
            
            # 创建目标点消息 - 返回原点（与 navigation_config /航点对话框一致，多话题发布）
            goal_msg = PoseStamped()
            nav_cfg = self._navigation_config_dict()
            self._return_home_saw_exec = False
            self._return_home_start_time = time.time()

            goal_topics = nav_cfg.get("goal_topics") or ["/move_base_simple/goal"]
            goal_msg.header.frame_id = self._navigation_goal_frame_id()
            goal_msg.header.stamp = rospy.Time.now()

            goal_msg.pose.position.x = float(hx)
            goal_msg.pose.position.y = float(hy)
            goal_msg.pose.position.z = float(hz)
            goal_msg.pose.orientation.x = 0.0
            goal_msg.pose.orientation.y = 0.0
            goal_msg.pose.orientation.z = 0.0
            goal_msg.pose.orientation.w = 1.0

            self._return_home_target = {"x": float(hx), "y": float(hy), "z": float(hz)}

            pubs = [rospy.Publisher(t, PoseStamped, queue_size=10) for t in goal_topics]
            rospy.sleep(0.5)
            for p in pubs:
                p.publish(goal_msg)
            rospy.loginfo(
                "已发布返航目标点 (%.2f, %.2f, %.2f) frame=%s -> %s",
                hx,
                hy,
                hz,
                goal_msg.header.frame_id,
                goal_topics,
            )
            
            notify(self, "返航中", "无人机正在返回原点，请等待到达后自动降落…", "info")
            
            # 启动定时器监控FSM状态，等待到达后发送降落命令
            self.return_home_timer = QTimer()
            self.return_home_timer.timeout.connect(self.checkReturnHomeStatus)
            self.return_home_timer.start(500)  # 每500ms检查一次
            
        except Exception as e:
            notify_error(self, "返航错误", f"返航时出错: {str(e)}")
    
    def checkReturnHomeStatus(self):
        """检查返航状态：先见 EXEC_TRAJ 再见 WAIT_TARGET 才降落；无 FSM 时用里程计距离兜底。"""
        try:
            exec_s = getattr(self, "_return_home_fsm_exec", 4)
            wait_s = getattr(self, "_return_home_fsm_wait", 1)
            min_sec = getattr(self, "_return_home_min_sec", 2.5)

            fsm_active = False
            fsm_state = 0
            if hasattr(self, "topic_subscriber") and self.topic_subscriber:
                fsm_active = self.topic_subscriber.is_topic_active("fsm_state")
                fsm_data = self.topic_subscriber.get_data("fsm_state")
                if fsm_data:
                    fsm_state = fsm_data.get("state", 0)

            should_land = False

            if fsm_active:
                if fsm_state == exec_s:
                    self._return_home_saw_exec = True
                if self._return_home_saw_exec and fsm_state == wait_s:
                    should_land = True

            if not should_land:
                elapsed = time.time() - getattr(self, "_return_home_start_time", 0.0)
                odom = None
                if hasattr(self, "topic_subscriber") and self.topic_subscriber:
                    odom = self.topic_subscriber.get_data("odometry")
                if odom and elapsed >= min_sec:
                    pos = odom.get("position") or {}
                    tgt = getattr(self, "_return_home_target", None) or {"x": 0.0, "y": 0.0, "z": 0.0}
                    if self._return_home_position_reached(pos, tgt):
                        should_land = True
                    else:
                        # NavRL：插值阶段结束后若已回到目标水平附近，避免因 Z 跟踪误差长期卡在「返航中」
                        d = getattr(self, "_return_home_navrl", None)
                        if d:
                            grace = float(getattr(self, "_return_home_navrl_grace_sec", 2.0))
                            if (time.time() - float(d["t0"])) >= float(d["T"]) + grace:
                                dx = float(pos.get("x", 0.0)) - float(tgt.get("x", 0.0))
                                dy = float(pos.get("y", 0.0)) - float(tgt.get("y", 0.0))
                                xy = math.sqrt(dx * dx + dy * dy)
                                if xy < float(getattr(self, "_return_home_xy_thresh", 0.65)) * 1.35:
                                    should_land = True

            if should_land:
                self._set_mission_phase("idle")
                if hasattr(self, "return_home_timer") and self.return_home_timer:
                    self.return_home_timer.stop()
                if hasattr(self, "return_home_goal_timer") and self.return_home_goal_timer:
                    self.return_home_goal_timer.stop()
                self._return_home_saw_exec = False
                self._return_home_navrl = None
                QTimer.singleShot(1000, self.sendLandingCommand)

        except Exception as e:
            print(f"检查返航状态时出错: {e}")
    
    def sendLandingCommand(self):
        """发送降落命令"""
        try:
            # CERLAB / NavRL 仿真：std_msgs/Empty，勿用 quadrotor_msgs（未安装时会报错）
            if self._backend_uses_cerlab_quad_topics():
                from std_msgs.msg import Empty
                land_pub = rospy.Publisher("/CERLAB/quadcopter/land", Empty, queue_size=1)
                rospy.sleep(0.1)
                land_pub.publish(Empty())
                notify(self, "降落中", "无人机正在降落（CERLAB 仿真）…", "info")
                return

            import subprocess

            # PX4CTRL：发布降落命令（需已安装 quadrotor_msgs）
            cmd = 'rostopic pub -1 /px4ctrl/takeoff_land quadrotor_msgs/TakeoffLand "takeoff_land_cmd: 2"'
            process = subprocess.Popen(
                cmd,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _stdout, stderr = process.communicate(timeout=10)
            if process.returncode == 0:
                rospy.loginfo("已发送降落命令")
                notify(self, "降落中", "无人机正在降落…", "info")
            else:
                rospy.logerr(f"发送降落命令失败: {stderr.decode()}")
                notify(self, "降落失败", f"发送降落命令失败:\n{stderr.decode()}", "warning")
                
        except Exception as e:
            print(f"发送降落命令时出错: {e}")
            notify_error(self, "降落错误", f"发送降落命令时出错: {str(e)}")

    def _republish_return_home_goal(self):
        """返航：NavRL 时插值发布 move_base 目标；纯 CERLAB 时刷新 setpoint_pose。"""
        try:
            if getattr(self, "_return_home_navrl", None):
                self._tick_navrl_return_goal_publish()
                return
            pub = getattr(self, "_return_home_setpoint_pub", None)
            msg = getattr(self, "_return_home_goal_msg", None)
            if pub is None or msg is None:
                return
            msg.header.stamp = rospy.Time.now()
            pub.publish(msg)
        except Exception:
            pass
    
    def importPointCloud(self):
        """导入点云功能（暂未实现）"""
        notify(self, "功能提示", "导入点云功能暂未实现，敬请期待！", "info")

    # 手动控制回调函数
    def onManualStart(self):
        """手动控制启动按钮回调 - 启动基础程序"""
        try:
            print("手动控制：启动按钮被点击")

            # 创建日志目录
            log_dir = get_data_directory("log")
            timestamp = time.strftime("%Y%m%d_%H%M%S")

            # 显示正在启动的消息
            progress_dialog = QProgressDialog("正在启动基础系统，请稍候...", "取消", 0, 100, self)
            progress_dialog.setWindowTitle("基础系统启动")
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setCancelButton(None)  # 禁用取消按钮
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()

            # 定义工作空间路径
            fast_drone_ws = os.path.expanduser("~/GUET_UAV_Drone_v2")

            # 启动基础程序
            progress_dialog.setLabelText("正在启动基础系统...")
            progress_dialog.setValue(20)
            QApplication.processEvents()

            # 创建日志文件
            base_system_log = f"{log_dir}/base_system_{timestamp}.log"
            if not hasattr(self, 'log_files'):
                self.log_files = {}
            self.log_files["base_system"] = base_system_log
            print(f"基础系统日志文件: {base_system_log}")

            # 修改命令使用run_base.sh
            cmd1 = f"cd {fast_drone_ws} && source {fast_drone_ws}/devel/setup.bash && sh shfiles/run_base.sh"
            with open(base_system_log, 'w') as log_file:
                process = subprocess.Popen(cmd1, shell=True, stdout=log_file, stderr=log_file,
                                        executable='/bin/bash', text=True)

            # 等待25秒，确保基础节点启动完成
            timeout = 25
            start_time = time.time()

            # 非阻塞方式检查进程是否已结束
            while time.time() - start_time < timeout:
                returncode = process.poll()
                if returncode is not None:  # 进程已结束
                    if returncode != 0:
                        # 获取错误输出
                        _, stderr = process.communicate()
                        error_msg = f"启动基础系统失败，返回代码: {returncode}\n\n错误信息:\n{stderr[:500]}..."
                        notify_error(self, "启动错误", error_msg)
                        progress_dialog.close()
                        return
                    break

                # 更新进度条
                elapsed = time.time() - start_time
                progress = int(20 + min(60, (elapsed / timeout * 60)))
                progress_dialog.setValue(progress)

                # 显示剩余等待时间
                remaining = max(0, int(timeout - elapsed))
                progress_dialog.setLabelText(f"正在启动基础系统...（还需等待约{remaining}秒）")

                QApplication.processEvents()
                time.sleep(0.5)

            progress_dialog.setValue(100)
            progress_dialog.setLabelText("基础系统启动完成！")
            QApplication.processEvents()
            time.sleep(1)
            progress_dialog.close()

            print("基础系统启动完成")
            notify(self, "启动成功", "基础系统已成功启动！", "info")

        except Exception as e:
            notify_error(self, "启动错误", f"启动基础系统时出错: {str(e)}")
            print(f"手动控制启动错误: {str(e)}")

    def onManualTakeoff(self):
        """手动控制起飞按钮回调 - 发布起飞命令"""
        try:
            print("手动控制：起飞按钮被点击")
            if not self._guard_manual_control("起飞"):
                return
            self._ensure_control_backend_ready()

            # 优先使用控制后端（会做 OFFBOARD/解锁确认，避免假成功）
            if hasattr(self, "control_backend") and self.control_backend:
                progress_dialog = QProgressDialog(
                    f"正在执行起飞（后端: {getattr(self, 'control_backend_name', 'unknown')}）...",
                    None,
                    0,
                    100,
                    self,
                )
                progress_dialog.setWindowTitle("起飞命令")
                progress_dialog.setWindowModality(Qt.WindowModal)
                progress_dialog.setCancelButton(None)
                progress_dialog.setValue(30)
                progress_dialog.show()
                QApplication.processEvents()

                r = self.control_backend.takeoff()

                progress_dialog.setValue(100)
                QApplication.processEvents()
                time.sleep(0.2)
                progress_dialog.close()

                if r.ok:
                    notify(self, "起飞", r.message, "info")
                else:
                    extra = ""
                    if hasattr(self, "_last_health_details") and self._last_health_details:
                        extra = "\n\n对接自检:\n" + "\n".join(self._last_health_details[:10])
                    notify(self, "起飞失败/未确认", r.message + extra, "warning")
                return

            notify(
                self,
                "起飞不可用",
                "未检测到可用控制后端。当前工程的 RC 覆写仅对 MAVROS 有效，"
                "而本仿真应走 CERLAB(/CERLAB/quadcopter/*) 或 MAVROS/PX4 链路。",
                "warning",
            )

        except subprocess.TimeoutExpired:
            notify(self, "超时错误", "起飞命令执行超时，请检查ROS环境是否正常", "warning")
            print("起飞命令执行超时")
        except Exception as e:
            notify_error(self, "起飞错误", f"发送起飞命令时出错: {str(e)}")
            print(f"手动控制起飞错误: {str(e)}")

    def onManualSelfRescue(self):
        """手动页：仿真复位再起飞（CERLAB reset + takeoff 序列，依赖插件）。"""
        try:
            print("手动控制：仿真复位再起（自救）")
            if not self._guard_manual_control("仿真复位再起"):
                return
            setattr(self, "_hold_goal_last_accepted_xyz", None)
            self._ensure_control_backend_ready()

            if hasattr(self, "control_backend") and self.control_backend:
                progress_dialog = QProgressDialog(
                    f"正在执行仿真复位再起（后端: {getattr(self, 'control_backend_name', 'unknown')}）...",
                    None,
                    0,
                    100,
                    self,
                )
                progress_dialog.setWindowTitle("仿真复位再起")
                progress_dialog.setWindowModality(Qt.WindowModal)
                progress_dialog.setCancelButton(None)
                progress_dialog.setValue(20)
                progress_dialog.show()
                QApplication.processEvents()

                r = self.control_backend.self_rescue()

                progress_dialog.setValue(100)
                QApplication.processEvents()
                time.sleep(0.2)
                progress_dialog.close()

                if r.ok:
                    notify(self, "仿真复位再起", r.message, "info")
                else:
                    extra = ""
                    if hasattr(self, "_last_health_details") and self._last_health_details:
                        extra = "\n\n对接自检:\n" + "\n".join(self._last_health_details[:10])
                    notify(self, "仿真复位再起不可用", r.message + extra, "warning")
                return

            notify(
                self,
                "自救不可用",
                "未检测到可用控制后端；仿真复位需要 CERLAB/NavRL/混合链路或已配置的 reset 话题。",
                "warning",
            )
        except Exception as e:
            notify_error(self, "仿真复位再起错误", f"执行时出错: {str(e)}")
            print(f"手动控制仿真复位再起错误: {str(e)}")

    def onManualUp(self):
        """手动控制向上按钮回调 - 前进"""
        try:
            print("手动控制：向上按钮被点击 - 前进")
            if not self._guard_manual_control("前进"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.nudge("forward", 0.5)
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制前进错误: {str(e)}")

    def onManualDown(self):
        """手动控制向下按钮回调 - 后退"""
        try:
            print("手动控制：向下按钮被点击 - 后退")
            if not self._guard_manual_control("后退"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.nudge("backward", 0.5)
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制后退错误: {str(e)}")

    def onManualLeft(self):
        """手动控制向左按钮回调 - 左移"""
        try:
            print("手动控制：向左按钮被点击 - 左移")
            if not self._guard_manual_control("左移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.nudge("left", 0.5)
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制左移错误: {str(e)}")

    def onManualRight(self):
        """手动控制向右按钮回调 - 右移"""
        try:
            print("手动控制：向右按钮被点击 - 右移")
            if not self._guard_manual_control("右移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.nudge("right", 0.5)
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制右移错误: {str(e)}")

    # 持续控制回调函数 - 按下事件
    def onManualUpPressed(self):
        """手动控制向上按钮按下 - 开始前进"""
        try:
            print("手动控制：向上按钮按下 - 开始前进")
            if not self._guard_manual_control("持续前进"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.start_continuous("forward")
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制开始前进错误: {str(e)}")

    def onManualUpReleased(self):
        """手动控制向上按钮释放 - 停止前进"""
        try:
            print("手动控制：向上按钮释放 - 停止前进")
            if not self._guard_manual_control("停止前进"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.stop_continuous("forward")
                return
            notify(self, "控制不可用", "未检测到可用控制后端（请先确保仿真/飞控链路正常）。", "warning")
        except Exception as e:
            print(f"手动控制停止前进错误: {str(e)}")

    def onManualDownPressed(self):
        """手动控制向下按钮按下 - 开始后退"""
        try:
            print("手动控制：向下按钮按下 - 开始后退")
            if not self._guard_manual_control("持续后退"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.start_continuous("backward")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.start_continuous_command('backward')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制开始后退错误: {str(e)}")

    def onManualDownReleased(self):
        """手动控制向下按钮释放 - 停止后退"""
        try:
            print("手动控制：向下按钮释放 - 停止后退")
            if not self._guard_manual_control("停止后退"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.stop_continuous("backward")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.stop_continuous_command('backward')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制停止后退错误: {str(e)}")

    def onManualLeftPressed(self):
        """手动控制向左按钮按下 - 开始左移"""
        try:
            print("手动控制：向左按钮按下 - 开始左移")
            if not self._guard_manual_control("持续左移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.start_continuous("left")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.start_continuous_command('left')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制开始左移错误: {str(e)}")

    def onManualLeftReleased(self):
        """手动控制向左按钮释放 - 停止左移"""
        try:
            print("手动控制：向左按钮释放 - 停止左移")
            if not self._guard_manual_control("停止左移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.stop_continuous("left")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.stop_continuous_command('left')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制停止左移错误: {str(e)}")

    def onManualRightPressed(self):
        """手动控制向右按钮按下 - 开始右移"""
        try:
            print("手动控制：向右按钮按下 - 开始右移")
            if not self._guard_manual_control("持续右移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.start_continuous("right")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.start_continuous_command('right')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制开始右移错误: {str(e)}")

    def onManualRightReleased(self):
        """手动控制向右按钮释放 - 停止右移"""
        try:
            print("手动控制：向右按钮释放 - 停止右移")
            if not self._guard_manual_control("停止右移"):
                return
            self._ensure_control_backend_ready()
            if hasattr(self, "control_backend") and self.control_backend:
                self.control_backend.stop_continuous("right")
                return
            if hasattr(self, 'manual_controller') and self.manual_controller:
                self.manual_controller.stop_continuous_command('right')
            else:
                print("手动控制器未初始化")
        except Exception as e:
            print(f"手动控制停止右移错误: {str(e)}")

    def setupRVizOverlay(self):
        """创建悬浮在RViz上方的信息面板 - 独立窗口，但跟随RViz框架移动"""
        # 创建悬浮面板容器 - 独立窗口
        self.rviz_overlay = QWidget()
        self.rviz_overlay.setObjectName("rvizOverlay")
        
        # 设置窗口标志，使其作为工具窗口、无边框并置顶
        self.rviz_overlay.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        
        # 设置窗口背景透明
        self.rviz_overlay.setAttribute(Qt.WA_TranslucentBackground)
        
        # 使用浅黑色背景，30%不透明度，添加较大圆角
        self.rviz_overlay.setStyleSheet("""
            QWidget#rvizOverlay {
                background-color: rgba(26, 32, 44, 0.3);  /* 30%不透明度浅黑色 */
                border-radius: 15px;  /* 较大的圆角 */
            }
            QLabel {
                color: white;
                font-size: 12pt;
                background-color: transparent;
                padding: 2px;
            }
            QLabel.value {
                color: #3498DB;  /* 蓝色值 */
                font-weight: bold;
            }
        """)
        
        # 创建水平布局
        overlay_layout = QHBoxLayout(self.rviz_overlay)
        overlay_layout.setContentsMargins(12, 6, 12, 6)
        overlay_layout.setSpacing(3)  # 进一步减小间距
        
        # 定义要显示的信息项和对应图标
        info_items = [
            {"icon": ":/images/icons/flitghtmode.svg", "value_id": "mode_value"},
            {"icon": ":/images/icons/remotecontrol.svg", "value_id": "rc_value"}, 
            {"icon": ":/images/icons/h.svg", "value_id": "altitude_value", "unit": "m"},
            {"icon": ":/images/icons/d.svg", "value_id": "speed_value", "unit": "m/s"},
            {"icon": ":/images/icons/voltage.svg", "value_id": "voltage_value", "unit": "V"}, 
            {"icon": ":/images/icons/battery_100.svg", "value_id": "battery_value", "unit": "%"}
        ]
        
        # 创建图标和标签
        for i, item in enumerate(info_items):
            # 如果不是第一项，添加更小的间距，但不添加分隔线（保持透明效果）
            if i > 0:
                spacer = QSpacerItem(2, 10, QSizePolicy.Fixed, QSizePolicy.Minimum)
                overlay_layout.addItem(spacer)
            
            # 创建一个水平布局的容器来放置图标和值
            item_container = QWidget()
            item_layout = QHBoxLayout(item_container)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(2)  # 减小图标和值之间的间距
            
            # 图标
            icon_label = QLabel()
            icon_pixmap = QPixmap(item["icon"]).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)  # 略微减小图标
            icon_label.setPixmap(icon_pixmap)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setContentsMargins(0, 0, 0, 0)  # 移除内边距
            
            # 为特定图标设置对象名称，方便后续查找
            if "battery" in item["icon"]:
                icon_label.setObjectName("batteryIcon")
                icon_label.setProperty("icon_type", "battery")
            elif "voltage" in item["icon"]:
                icon_label.setObjectName("voltageIcon")
            
            item_layout.addWidget(icon_label)
            
            # 合并值和单位到一个标签
            value_label = QLabel("--" + (" " + item["unit"] if "unit" in item else ""))
            value_label.setProperty("class", "value")
            value_label.setProperty("unit", item.get("unit", ""))  # 保存单位信息
            value_label.setContentsMargins(0, 0, 0, 0)  # 移除内边距
            setattr(self, item["value_id"], value_label)
            item_layout.addWidget(value_label)
            
            overlay_layout.addWidget(item_container)
        
        # 设置固定高度和宽度
        self.rviz_overlay.setFixedHeight(40)
        self.rviz_overlay.setFixedWidth(750)  # 固定宽度为750像素
        
        # 更新位置的函数
        def updateOverlayPosition():
            try:
                if hasattr(self, 'frame') and self.frame and hasattr(self, 'rviz_overlay') and self.rviz_overlay:
                    # 确保RViz框架已经完成布局更新
                    self.frame.update()
                    QApplication.processEvents()

                    # 直接使用RViz框架的几何信息，因为它已经考虑了分割器的布局
                    frame_rect = self.frame.geometry()
                    frame_pos = self.frame.mapToGlobal(QPoint(0, 0))

                    # 检查几何信息是否有效
                    if frame_rect.width() > 0 and frame_rect.height() > 0:
                        # 居中显示在RViz框架上方
                        x_pos = frame_pos.x() + (frame_rect.width() - self.rviz_overlay.width()) // 2
                        y_pos = frame_pos.y() + 20

                        # 移动窗口
                        self.rviz_overlay.move(x_pos, y_pos)

                        # 确保窗口可见
                        if not self.rviz_overlay.isVisible():
                            self.rviz_overlay.show()
            except Exception as e:
                print(f"更新信息条位置时出错: {e}")
        
        # 将函数保存为类实例方法，以便后续修改
        self.updateOverlayPosition = updateOverlayPosition

        # 立即显示悬浮面板
        self.rviz_overlay.show()

        # 注意：悬浮组件的位置更新已合并到主更新循环中，减少定时器数量
        # 初始位置更新
        QTimer.singleShot(100, updateOverlayPosition)

    def updateOverlayData(self):
        """更新信息条数据"""
        if not all(hasattr(self, attr) for attr in ['mode_value', 'altitude_value', 'speed_value', 'battery_value', 'voltage_value', 'rc_value']):
            return  # 确保UI已初始化
        
        try:
            # 更新模式
            if hasattr(self, 'mode_label'):
                mode_text = self.mode_label.text().split(" ")[0] if " " in self.mode_label.text() else self.mode_label.text()
                self.mode_value.setText(mode_text)
            
            # 更新高度
            if hasattr(self, 'altitude_label'):
                # 从格式为"0.0000 m"的文本中提取数值部分
                height_text = self.altitude_label.text()
                if ' ' in height_text:
                    height_value = height_text.split(' ')[0]
                    # 格式化为最多2位小数
                    try:
                        height_value = f"{float(height_value):.2f}"
                    except:
                        pass
                    # 获取单位并添加到文本中
                    unit = self.altitude_value.property("unit") or ""
                    self.altitude_value.setText(f"{height_value} {unit}".strip())
                else:
                    # 获取单位并添加到文本中
                    unit = self.altitude_value.property("unit") or ""
                    self.altitude_value.setText(f"{height_text} {unit}".strip())
            
            # 更新速度
            if hasattr(self, 'ground_speed_label'):
                # 从格式为"0.0000 m/s"的文本中提取数值部分
                speed_text = self.ground_speed_label.text()
                if ' ' in speed_text:
                    speed_value = speed_text.split(' ')[0]
                    # 格式化为最多2位小数
                    try:
                        speed_value = f"{float(speed_value):.2f}"
                    except:
                        pass
                    # 获取单位并添加到文本中
                    unit = self.speed_value.property("unit") or ""
                    self.speed_value.setText(f"{speed_value} {unit}".strip())
                else:
                    # 获取单位并添加到文本中
                    unit = self.speed_value.property("unit") or ""
                    self.speed_value.setText(f"{speed_text} {unit}".strip())
            
            # 更新电池电量
            if hasattr(self, 'battery_percentage'):
                battery = f"{self.battery_percentage:.1f}" if isinstance(self.battery_percentage, (int, float)) else "--"
                # 获取单位并添加到文本中
                unit = self.battery_value.property("unit") or ""
                self.battery_value.setText(f"{battery} {unit}".strip())
                
                # 根据电量更新电池图标
                battery_value = float(battery) if battery != "--" else 100
                if battery_value <= 15:
                    icon_path = ":/images/icons/battery_0.svg"
                elif battery_value <= 50:
                    icon_path = ":/images/icons/battery_50.svg"
                elif battery_value <= 75:
                    icon_path = ":/images/icons/battery_75.svg"
                else:
                    icon_path = ":/images/icons/battery_100.svg"
                    
                # 直接通过对象名称查找电池图标并更新
                battery_icon = self.rviz_overlay.findChild(QLabel, "batteryIcon")
                if battery_icon:
                    battery_icon.setPixmap(QPixmap(icon_path).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    # 备用方法：搜索所有标签
                    for widget in self.rviz_overlay.findChildren(QLabel):
                        if widget.property("icon_type") == "battery" or "battery" in str(widget.objectName()):
                            widget.setPixmap(QPixmap(icon_path).scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            widget.setObjectName("batteryIcon")  # 确保设置了名称
                            break
            
            # 更新电压
            if hasattr(self, 'battery_voltage'):
                voltage = f"{self.battery_voltage:.2f}" if isinstance(self.battery_voltage, (int, float)) else "--"
                # 获取单位并添加到文本中
                unit = self.voltage_value.property("unit") or ""
                self.voltage_value.setText(f"{voltage} {unit}".strip())
            
            # 更新遥控器连接状态
            if hasattr(self, 'topic_subscriber') and self.topic_subscriber:
                # 检查遥控器话题是否活跃
                rc_active = self.topic_subscriber.is_topic_active('rc_input')
                # 检查最新数据
                rc_data = self.topic_subscriber.get_latest_data('rc_input')
                
                # 确定连接状态
                if rc_active and rc_data and 'channels' in rc_data and len(rc_data['channels']) > 0:
                    self.rc_value.setText("已连接")
                    self.rc_value.setStyleSheet("color: #2ECC71; font-weight: bold;")  # 绿色表示已连接
                else:
                    self.rc_value.setText("未连接")
                    self.rc_value.setStyleSheet("color: #E74C3C; font-weight: bold;")  # 红色表示未连接
                
        except Exception as e:
            print(f"更新信息面板数据时出错: {str(e)}")

    def silentStopDroneSystem(self):
        """静默关闭无人机系统，不显示任何对话框"""
        try:
            # 立即停止所有进程监控定时器，避免重复弹出错误消息
            for timer_attr in ['check_process_timer', 'check_process2_timer', 'check_process3_timer', 'process_monitor_timer']:
                if hasattr(self, timer_attr):
                    timer = getattr(self, timer_attr)
                    if timer and timer.isActive():
                        timer.stop()
                        print(f"已停止{timer_attr}")
            
            # 如果有任何话题订阅器在运行，先关闭它
            if self.topic_subscriber:
                try:
                    self.topic_subscriber.shutdown()
                    self.topic_subscriber = None
                    # 重置话题数据状态，确保下次启动时正确初始化
                    self.topics_with_data = {
                        "battery": False,
                        "status": False,
                        "odometry": False,
                        "velocity": False,
                        "camera": False,
                        "depth": False,
                        "bird_view": False,
                        "obstacle_states": False,
                    }

                    print("已关闭话题订阅器并重置话题数据状态")
                except Exception as e:
                    print(f"关闭话题订阅器时出错: {str(e)}")
            
            # 检查是否有单独启动的进程需要关闭
            if hasattr(self, 'processes') and self.processes:
                # 按照启动的相反顺序终止进程
                process_order = ["ball_tracker", "planner", "px4ctrl", "detector", "vins", "mavros", "camera"]
                
                for process_name in process_order:
                    if process_name in self.processes and self.processes[process_name]:
                        try:
                            # 终止进程
                            self.processes[process_name].terminate()
                            # 给进程一点时间自行退出
                            start_time = time.time()
                            while time.time() - start_time < 1:  # 最多等待1秒
                                if self.processes[process_name].poll() is not None:
                                    # 进程已结束
                                    break
                                time.sleep(0.1)
                            
                            # 如果进程仍未退出，强制杀死
                            if self.processes[process_name].poll() is None:
                                self.processes[process_name].kill()
                                
                            print(f"已停止{process_name}进程")
                        except Exception as e:
                            print(f"停止{process_name}进程时出错: {str(e)}")
                
                # 清空进程列表
                self.processes = {}
            
            # 使用强大的终止机制，确保所有相关进程都被终止
            # 使用全局常量避免重复定义
            process_patterns = PROCESS_PATTERNS
            
            # 使用pkill强制终止每个模式的进程
            for pattern in process_patterns:
                try:
                    # 使用pgrep检查进程是否存在
                    check_process = subprocess.run(
                        f"pgrep -f \"{pattern}\"", 
                        shell=True, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    
                    if check_process.returncode == 0:  # 进程存在
                        # 使用pkill -9 强制终止
                        kill_cmd = f"pkill -9 -f \"{pattern}\""
                        subprocess.run(kill_cmd, shell=True)
                        print(f"已终止进程：{pattern}")
                    else:
                        print(f"未找到进程：{pattern}")
                except Exception as e:
                    print(f"终止进程 {pattern} 时出错: {str(e)}")
            
            # 保留roscore，但清理其他所有ROS节点
            try:
                # 先检查ROS环境是否正常
                rosnode_check = subprocess.run(
                    "rosnode list", 
                    shell=True, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    timeout=5
                )
                
                if rosnode_check.returncode == 0:
                    # 获取节点列表
                    nodes = rosnode_check.stdout.strip().split('\n')
                    # 过滤掉rosout和master相关节点
                    nodes_to_kill = [node for node in nodes if not any(x in node for x in ['/rosout', '/master'])]
                    
                    if nodes_to_kill:
                        # 每个节点单独终止
                        for node in nodes_to_kill:
                            kill_cmd = f"rosnode kill {node}"
                            subprocess.run(kill_cmd, shell=True, timeout=2)
                            print(f"已清理节点: {node}")
                    
                    print("已清理所有非核心ROS节点")
                else:
                    print("ROS环境可能未启动或异常")
            except Exception as e:
                print(f"清理ROS节点时出错: {str(e)}")
                
        except Exception as e:
            print(f"静默停止无人机系统时出错: {str(e)}")
            
    def setupCompass(self):
        """创建指南针组件并添加到RViz右下角，独立窗口但跟随RViz框架移动"""
        # 导入指南针组件
        from dashboard import CompassWidget
        
        # 创建指南针组件
        self.compass = CompassWidget(parent=self)  # 传入self作为参考，但不作为父组件
        
        # 定义位置更新函数
        def updateCompassPosition():
            try:
                if hasattr(self, 'frame') and self.frame and hasattr(self, 'compass') and self.compass:
                    # 确保RViz框架已经完成布局更新
                    self.frame.update()
                    QApplication.processEvents()

                    # 直接使用RViz框架的几何信息
                    frame_rect = self.frame.geometry()
                    frame_pos = self.frame.mapToGlobal(QPoint(0, 0))

                    # 检查几何信息是否有效
                    if frame_rect.width() > 0 and frame_rect.height() > 0:
                        # 放在RViz框架的右下角，增加边距让它更靠左上方一些
                        margin_x = 60  # 增加水平边距
                        margin_y = 50  # 增加垂直边距
                        x_pos = frame_pos.x() + frame_rect.width() - self.compass.width() - margin_x
                        y_pos = frame_pos.y() + frame_rect.height() - self.compass.height() - margin_y

                        # 移动窗口
                        self.compass.move(x_pos, y_pos)

                        # 确保窗口可见
                        if not self.compass.isVisible():
                            self.compass.show()
            except Exception as e:
                print(f"更新指南针位置时出错: {e}")
        
        # 将函数保存为类实例方法，以便后续修改
        self.updateCompassPosition = updateCompassPosition
        
        # 注意：指南针的位置和数据更新已合并到主更新循环中
        # 初始位置更新
        QTimer.singleShot(100, updateCompassPosition)

    def setupAttitudeWidget(self):
        """创建姿态指示器组件并添加到RViz右下角，独立窗口但跟随RViz框架移动"""
        # 导入姿态指示器组件
        from dashboard import AttitudeIndicatorWidget
        
        # 创建姿态指示器组件
        self.attitude_widget = AttitudeIndicatorWidget(parent=self)  # 传入self作为参考，但不作为父组件
        
        # 定义位置更新函数 - 直接基于RViz框架位置计算
        def updateAttitudeWidgetPosition():
            try:
                if hasattr(self, 'frame') and self.frame and hasattr(self, 'attitude_widget') and self.attitude_widget:
                    # 确保RViz框架已经完成布局更新
                    self.frame.update()
                    QApplication.processEvents()

                    # 直接使用RViz框架的几何信息
                    frame_rect = self.frame.geometry()
                    frame_pos = self.frame.mapToGlobal(QPoint(0, 0))

                    # 检查几何信息是否有效
                    if frame_rect.width() > 0 and frame_rect.height() > 0:
                        # 放在RViz框架的右下角位置，与指南针并排
                        margin_x = 260  # 增加水平边距，放在指南针左侧
                        margin_y = 50   # 垂直边距与指南针相同
                        x_pos = frame_pos.x() + frame_rect.width() - self.attitude_widget.width() - margin_x
                        y_pos = frame_pos.y() + frame_rect.height() - self.attitude_widget.height() - margin_y

                        # 确保不会移出RViz框架左侧
                        min_x = frame_pos.x() + 20
                        if x_pos < min_x:
                            # 如果左侧空间不足，放在上方
                            x_pos = frame_pos.x() + frame_rect.width() - self.attitude_widget.width() - 60
                            y_pos = frame_pos.y() + frame_rect.height() - self.attitude_widget.height() - 240

                        # 移动窗口
                        self.attitude_widget.move(x_pos, y_pos)

                        # 确保窗口可见
                        if not self.attitude_widget.isVisible():
                            self.attitude_widget.show()
            except Exception as e:
                print(f"更新姿态指示器位置时出错: {e}")
        
        # 将函数保存为类实例方法，以便后续修改
        self.updateAttitudeWidgetPosition = updateAttitudeWidgetPosition

        # 注意：姿态指示器的位置更新已合并到主更新循环中，减少定时器数量
        # 初始位置更新
        QTimer.singleShot(100, updateAttitudeWidgetPosition)

    def setupAllOverlays(self):
        """同时创建所有悬浮窗口组件，确保它们同时显示"""
        # 暂时禁用鼠标跟踪，避免在创建悬浮窗口时触发左侧栏显示
        old_enable_state = getattr(self, 'enable_sidebar_hover', False)
        self.enable_sidebar_hover = False
        
        # 1. 创建RViz悬浮信息面板
        self.setupRVizOverlay()
        
        # 2. 创建指南针组件
        self.setupCompass()
        
        # 3. 创建姿态指示器组件
        self.setupAttitudeWidget()
        
        # 恢复原来的鼠标跟踪状态
        self.enable_sidebar_hover = old_enable_state
        
    # handleCloseEvent方法已移至closeEvent方法下实现

    def autoHideSidebar(self):
        """启动后自动隐藏左侧栏和右侧栏"""
        self.toggleSidebar(hide=True, animate=True)
        self.toggleRightSidebar(hide=True, animate=True)
        
    def checkMousePosition(self):
        """检查鼠标位置，根据位置自动显示或隐藏左右侧栏"""
        # 如果鼠标跟踪未启用，直接返回
        if not hasattr(self, 'enable_sidebar_hover') or not self.enable_sidebar_hover:
            return
            
        try:
            # 获取鼠标当前位置
            cursor_pos = QCursor.pos()
            # 将全局坐标转换为窗口坐标
            local_pos = self.mapFromGlobal(cursor_pos)
            
            # 定义左右侧敏感区域宽度
            sensitivity_width = 20
            
            # 获取窗口宽度
            window_width = self.width()
            
            # 检查是否在左侧敏感区域内
            in_left_sensitive_area = 0 <= local_pos.x() <= sensitivity_width
            
            # 检查是否在右侧敏感区域内
            in_right_sensitive_area = window_width - sensitivity_width <= local_pos.x() <= window_width
            
            # 检查是否在窗口内
            in_window = self.rect().contains(local_pos)
            
            # 计算左侧栏区域
            sidebar_width = self.left_sidebar.width() if self.left_sidebar.isVisible() else 0
            in_sidebar_area = 0 <= local_pos.x() <= sidebar_width and in_window
            
            # 计算右侧栏区域
            right_sidebar_width = self.right_sidebar.width() if self.right_sidebar.isVisible() else 0
            in_right_sidebar_area = window_width - right_sidebar_width <= local_pos.x() <= window_width and in_window
            
            # 处理左侧栏 - 仅在未固定时进行自动显示/隐藏
            if not self.left_sidebar_pinned:
                # 如果鼠标在窗口内的左侧敏感区域，显示左侧栏
                if in_window and in_left_sensitive_area and not self.sidebar_expanded:
                    self.toggleSidebar(hide=False, animate=True)
                
                # 如果鼠标不在左侧敏感区域且不在左侧栏内，隐藏左侧栏
                elif self.sidebar_expanded and not in_sidebar_area and not in_left_sensitive_area:
                    self.toggleSidebar(hide=True, animate=True)
            
            # 处理右侧栏 - 仅在未固定时进行自动显示/隐藏
            if not self.right_sidebar_pinned:
                # 如果鼠标在窗口内的右侧敏感区域，显示右侧栏
                if in_window and in_right_sensitive_area and not self.right_sidebar_expanded:
                    self.toggleRightSidebar(hide=False, animate=True)
                
                # 如果鼠标不在右侧敏感区域且不在右侧栏内，隐藏右侧栏
                elif self.right_sidebar_expanded and not in_right_sidebar_area and not in_right_sensitive_area:
                    self.toggleRightSidebar(hide=True, animate=True)
                
        except Exception as e:
            print(f"检查鼠标位置时出错: {str(e)}")
            # 错误时停止定时器以防止继续出错
            self.sidebar_hover_timer.stop()

    def setupAllOverlaysAndHideSidebar(self):
        """设置所有悬浮窗口并在完成后隐藏左右侧栏"""
        # 先设置所有悬浮窗口
        self.setupAllOverlays()
        
        # 延迟500ms后隐藏左右侧栏，确保悬浮窗口已完全显示
        QTimer.singleShot(500, self.finalizeStartup)
    
    def setupAllOverlaysAndOpenSidebars(self):
        """设置所有悬浮窗口并在完成后打开并锁定左右侧栏"""
        # 先设置所有悬浮窗口
        self.setupAllOverlays()
        
        # 延迟500ms后打开并锁定左右侧栏，确保悬浮窗口已完全显示
        QTimer.singleShot(500, self.startupOpenAndLockSidebars)
    
    def finalizeStartup(self):
        """完成启动过程，隐藏左右侧栏并启用鼠标跟踪"""
        # 隐藏左侧栏和右侧栏
        self.toggleSidebar(hide=True, animate=True)
        self.toggleRightSidebar(hide=True, animate=True)
        
        # 确保两侧的固定状态为未固定
        self.left_sidebar_pinned = False
        self.right_sidebar_pinned = False
        
        # 恢复按钮样式为默认
        self.toggle_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A202C;
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3498DB;
            }
            QPushButton:pressed {
                background-color: #2980B9;
            }
        """)
        self.toggle_right_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A202C;
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #3498DB;
            }
            QPushButton:pressed {
                background-color: #2980B9;
            }
        """)
        
        # 延迟300ms后启用鼠标跟踪，避免动画过程中触发鼠标跟踪
        QTimer.singleShot(300, self.enableMouseTracking)
    
    def startupOpenAndLockSidebars(self):
        """启动时打开并锁定左右侧栏"""
        print("开始启动侧栏打开动画...")
        
        # 确保侧栏开始时是隐藏状态
        self.sidebar_expanded = False
        self.right_sidebar_expanded = False
        
        # 先打开左侧栏（带动画）
        self.toggleSidebar(hide=False, animate=True)
        
        # 延迟200ms后打开右侧栏（错开动画时间以避免同时动画）
        QTimer.singleShot(200, lambda: self.toggleRightSidebar(hide=False, animate=True))
        
        # 延迟600ms后设置锁定状态（等待动画完成）
        QTimer.singleShot(600, self.lockSidebarsAfterOpen)
    
    def lockSidebarsAfterOpen(self):
        """在侧栏打开后设置锁定状态"""
        print("锁定左右侧栏...")
        
        # 设置左侧栏为锁定状态
        self.left_sidebar_pinned = True
        self.toggle_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;  /* 蓝色背景表示已固定 */
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2980B9;
            }
        """)
        
        # 设置右侧栏为锁定状态
        self.right_sidebar_pinned = True
        self.toggle_right_sidebar_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;  /* 蓝色背景表示已固定 */
                border: none;
                border-radius: 0;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #2980B9;
            }
        """)
        
        # 延迟100ms后启用鼠标跟踪
        QTimer.singleShot(100, self.enableMouseTracking)
    
    def enableMouseTracking(self):
        """启用鼠标跟踪"""
        self.enable_sidebar_hover = True
        print("鼠标跟踪已启用，左右侧栏已锁定并打开")




    # 注意：closeEvent方法已在上面优化实现，删除重复代码


## Start the Application
## ^^^^^^^^^^^^^^^^^^^^^
##
## That is just about it.  All that's left is the standard Qt
## top-level application code: create a QApplication, instantiate our
## class, and start Qt's main event loop (app.exec_()).
# 已移除check_rosdep_status函数，因为不需要检测rosdep

def check_and_start_roscore():
    """检查roscore是否运行，如果没有则启动它"""
    import subprocess
    import time
    import os
    
    # 检查roscore是否已在运行
    try:
        # 尝试使用rostopic list检查ROS master是否运行
        check_process = subprocess.Popen(['rostopic', 'list'], 
                                        stdout=subprocess.PIPE, 
                                        stderr=subprocess.PIPE)
        _, stderr = check_process.communicate(timeout=2)
        
        if check_process.returncode != 0:
            print("未检测到roscore运行，正在自动启动roscore...")
            
            # 启动 roscore：勿用 PIPE 承接 stdout/stderr，否则日志灌满缓冲区会导致 roscore 阻塞、整进程假死
            roscore_process = subprocess.Popen(
                ["roscore"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            
            # 等待roscore启动
            print("等待roscore启动...")
            time.sleep(3)  # 给roscore一些启动时间
            
            # 存储roscore进程ID以便在应用程序退出时关闭
            os.environ['ROSCORE_PID'] = str(roscore_process.pid)
            print(f"roscore已启动，PID: {roscore_process.pid}")
            return True
        else:
            print("已检测到roscore正在运行")
            return False
    except Exception as e:
        print(f"检查或启动roscore时出错: {str(e)}")
        return False

def set_serial_permissions():
    """尽力设置串口权限；无设备或无sudo权限时仅提示，不阻塞启动。"""
    try:
        import subprocess

        dev = "/dev/ttyACM0"
        if not os.path.exists(dev):
            print(f"串口设备不存在，跳过权限设置: {dev}")
            return False

        print("正在设置串口设备权限（非阻塞）...")
        # -n: 非交互；无 sudo 凭证时直接返回，避免卡在密码提示
        result = subprocess.run(
            ['sudo', '-n', 'chmod', '666', dev],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        if result.returncode == 0:
            print("串口设备权限设置成功")
            return True

        print(f"设置串口设备权限失败（已忽略，不影响仿真）: {result.stderr.strip()}")
        return False
    except Exception as e:
        print(f"设置串口设备权限时出错: {str(e)}")
        return False



if __name__ == '__main__':
    # 清理旧的 myviz 节点，避免“看的是旧窗口、状态不更新”的假未连接
    try:
        subprocess.run(
            "source /opt/ros/noetic/setup.bash && rosnode list | rg '^/myviz_' | xargs -r -n1 rosnode kill",
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        pass
    # 设置串口权限
    set_serial_permissions()
    
    app = QApplication(sys.argv)
    
    # 设置应用程序图标
    app_icon = QIcon("logo.png")
    app.setWindowIcon(app_icon)
    
    # 确保应用程序支持中文（如果QTextCodec可用）
    if QTextCodec is not None:
        try:
            QTextCodec.setCodecForLocale(QTextCodec.codecForName("UTF-8"))
        except Exception as e:
            print(f"设置编码时出错: {e}")
    
    # 检查并自动启动roscore
    check_and_start_roscore()
    
    # 初始化ROS节点
    try:
        rospy.init_node('myviz', anonymous=True)
        print("成功初始化ROS节点: myviz")
    except Exception as e:
        print(f"警告: ROS节点初始化失败: {str(e)}")
    
    # 创建主窗口
    try:
        myviz = MyViz()
        print("主窗口创建成功")
    except Exception as e:
        print(f"创建主窗口时出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 不要使用自定义布局，避免"already has a layout"错误
    # myviz.setLayout(main_layout) # 删除这一行

    # 获取可用屏幕区域（考虑任务栏/面板）
    desktop = QDesktopWidget()
    available_geometry = desktop.availableGeometry(desktop.primaryScreen())
    width = available_geometry.width()
    height = available_geometry.height()
    print(f"可用屏幕区域: {width}x{height}, 位置: ({available_geometry.x()}, {available_geometry.y()})")

    # 设置窗口为最大化模式启动（保留标题栏）
    myviz.showMaximized()  # 使用最大化模式，保留窗口控制按钮

    # 延迟设置分割器尺寸，确保窗口已完全显示
    QTimer.singleShot(500, myviz.setupAdaptiveSplitterSizes)
    
    # 启动Qt事件循环
    try:
        exit_code = app.exec_()
        
        # 关闭话题订阅器
        if hasattr(myviz, 'topic_subscriber') and myviz.topic_subscriber:
            myviz.topic_subscriber.shutdown()
            print("已关闭话题订阅器")
        
        # 关闭所有话题日志窗口
        try:
            from topic_logger import TopicLoggerDialog
            TopicLoggerDialog.close_all_windows()
            print("已关闭所有话题日志窗口")
        except Exception as e:
            print(f"关闭话题日志窗口时出错: {str(e)}")
        
        # 如果roscore是由本程序启动的，关闭它
        if 'ROSCORE_PID' in os.environ:
            try:
                roscore_pid = int(os.environ['ROSCORE_PID'])
                import signal
                import psutil
                
                print(f"正在关闭自动启动的roscore（PID: {roscore_pid}）...")
                try:
                    # 检查进程是否存在
                    if psutil.pid_exists(roscore_pid):
                        p = psutil.Process(roscore_pid)
                        # 发送SIGINT信号
                        p.send_signal(signal.SIGINT)
                        
                        # 使用psutil等待进程结束，设置较短的超时时间
                        try:
                            p.wait(timeout=3)  # 等待最多3秒
                            print("roscore已正常关闭")
                        except psutil.TimeoutExpired:
                            # 如果超时，强制结束进程
                            print("关闭roscore超时，强制终止...")
                            p.kill()
                            print("roscore已强制关闭")
                    else:
                        print(f"找不到PID为{roscore_pid}的进程，可能已关闭")
                except psutil.NoSuchProcess:
                    print(f"找不到PID为{roscore_pid}的进程，可能已关闭")
            except Exception as e:
                print(f"关闭roscore时出错: {str(e)}，继续执行退出流程")
            
        sys.exit(exit_code)
    except KeyboardInterrupt:
        # 处理Ctrl+C中断
        if hasattr(myviz, 'topic_subscriber') and myviz.topic_subscriber:
            myviz.topic_subscriber.shutdown()
            print("已关闭话题订阅器")
            
        # 关闭所有话题日志窗口
        try:
            from topic_logger import TopicLoggerDialog
            TopicLoggerDialog.close_all_windows()
            print("已关闭所有话题日志窗口")
        except Exception as e:
            print(f"关闭话题日志窗口时出错: {str(e)}")
        
        # 如果roscore是由本程序启动的，关闭它
        if 'ROSCORE_PID' in os.environ:
            try:
                roscore_pid = int(os.environ['ROSCORE_PID'])
                import signal
                import psutil
                
                print(f"正在关闭自动启动的roscore（PID: {roscore_pid}）...")
                try:
                    # 检查进程是否存在
                    if psutil.pid_exists(roscore_pid):
                        p = psutil.Process(roscore_pid)
                        # 发送SIGINT信号
                        p.send_signal(signal.SIGINT)
                        
                        # 使用psutil等待进程结束，设置较短的超时时间
                        try:
                            p.wait(timeout=3)  # 等待最多3秒
                            print("roscore已正常关闭")
                        except psutil.TimeoutExpired:
                            # 如果超时，强制结束进程
                            print("关闭roscore超时，强制终止...")
                            p.kill()
                            print("roscore已强制关闭")
                    else:
                        print(f"找不到PID为{roscore_pid}的进程，可能已关闭")
                except psutil.NoSuchProcess:
                    print(f"找不到PID为{roscore_pid}的进程，可能已关闭")
            except Exception as e:
                print(f"关闭roscore时出错: {str(e)}，继续执行退出流程")
            
        sys.exit(0)