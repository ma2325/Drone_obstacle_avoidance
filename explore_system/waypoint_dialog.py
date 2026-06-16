#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
目标点设置对话框模块
用于设置无人机导航目标点，支持多目标点添加和保存/加载
"""

import os
import json
import time
import rospy
from python_qt_binding.QtGui import *
from python_qt_binding.QtCore import *
try:
    from python_qt_binding.QtWidgets import *
except ImportError:
    pass

from geometry_msgs.msg import PoseStamped
from std_msgs.msg import Bool, Empty

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


def _load_navigation_config():
    path = os.path.join(os.path.dirname(__file__), "navigation_config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


try:
    from utils import hold_goal_odom_glitch_should_skip
except ImportError:
    hold_goal_odom_glitch_should_skip = None


class WaypointDialog(QDialog):
    """目标点设置对话框"""
    
    # 信号：当开始导航时发出
    navigationStarted = pyqtSignal(list)  # 发送目标点列表
    navigationEnded = pyqtSignal()  # 停止导航或全部航点完成

    def __init__(self, parent=None, topic_subscriber=None):
        super(WaypointDialog, self).__init__(parent)
        self.topic_subscriber = topic_subscriber
        self.waypoints = []  # 目标点列表
        self.current_waypoint_index = 0  # 当前目标点索引
        self.is_navigating = False  # 是否正在导航
        self.nav_cfg = _load_navigation_config()
        self._leg_saw_exec = False
        self._last_goal_publish_time = 0.0
        self._cerlab_goal_timer = QTimer(self)
        self._cerlab_goal_timer.timeout.connect(self._republish_cerlab_goal)
        self._cerlab_goal_msg = None
        self._using_planner_for_leg = False
        self._stuck_best_distance = None
        self._stuck_last_progress_time = 0.0
        self._stuck_recovery_count = 0
        self._recovery_active = False
        self._recovery_until_ts = 0.0
        self._vel_still_since = None
        self._hold_goal_glitch_prev_xyz = None

        # 设置窗口标志 - 非模态窗口，可以拖动和缩放
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # 关闭时不删除
        
        # 目标点发布者（ego / waypoint_generator 常订阅 /move_base_simple/goal；多机可能带前缀）
        self._goal_topics = self.nav_cfg.get("goal_topics") or ["/move_base_simple/goal"]
        self._goal_publishers = {}
        for gt in self._goal_topics:
            try:
                self._goal_publishers[gt] = rospy.Publisher(gt, PoseStamped, queue_size=10)
            except Exception as e:
                print(f"初始化目标点发布者失败 {gt}: {e}")

        # CERLAB 仿真直控：直接发布 setpoint_pose + posctrl（不依赖外部规划器）
        self._cerlab_setpoint_pub = None
        self._cerlab_posctrl_pub = None
        self._cerlab_velmode_pub = None
        self._cerlab_takeoff_pub = None
        try:
            self._cerlab_setpoint_pub = rospy.Publisher(
                "/CERLAB/quadcopter/setpoint_pose", PoseStamped, queue_size=10
            )
            self._cerlab_posctrl_pub = rospy.Publisher(
                "/CERLAB/quadcopter/posctrl", Bool, queue_size=1
            )
            self._cerlab_velmode_pub = rospy.Publisher(
                "/CERLAB/quadcopter/vel_mode", Bool, queue_size=1
            )
            self._cerlab_takeoff_pub = rospy.Publisher(
                "/CERLAB/quadcopter/takeoff", Empty, queue_size=1
            )
        except Exception:
            pass
        
        # FSM状态检查定时器
        self.fsm_check_timer = QTimer(self)
        self.fsm_check_timer.timeout.connect(self.checkFSMState)
        
        self.setupUI()
        self.loadDefaultWaypoints()
    
    def setupUI(self):
        """设置UI界面"""
        self.setWindowTitle("目标点设置")
        self.setMinimumSize(500, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E2330;
                color: #FFFFFF;
            }
            QLabel {
                color: #FFFFFF;
                font-size: 11pt;
            }
            QLineEdit {
                background-color: #2C3E50;
                color: #FFFFFF;
                border: 1px solid #3498DB;
                border-radius: 4px;
                padding: 5px;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #3498DB;
                color: white;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #1A5276;
            }
            QPushButton#addBtn {
                background-color: #27AE60;
            }
            QPushButton#addBtn:hover {
                background-color: #229954;
            }
            QPushButton#deleteBtn {
                background-color: #E74C3C;
            }
            QPushButton#deleteBtn:hover {
                background-color: #C0392B;
            }
            QPushButton#startBtn {
                background-color: #27AE60;
                min-height: 40px;
            }
            QPushButton#startBtn:hover {
                background-color: #229954;
            }
            QTableWidget {
                background-color: #2C3E50;
                color: #FFFFFF;
                border: 1px solid #3498DB;
                border-radius: 4px;
                gridline-color: #3498DB;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #3498DB;
            }
            QHeaderView::section {
                background-color: #1A202C;
                color: #FFFFFF;
                padding: 8px;
                border: 1px solid #3498DB;
                font-weight: bold;
            }
            QGroupBox {
                color: #3498DB;
                font-weight: bold;
                border: 1px solid #3498DB;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        # 状态显示区域
        status_group = QGroupBox("导航状态")
        status_layout = QHBoxLayout(status_group)
        
        self.status_label = QLabel("等待开始导航")
        self.status_label.setStyleSheet("color: #BDC3C7; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        
        self.fsm_label = QLabel("FSM: 未知")
        self.fsm_label.setStyleSheet("color: #F39C12;")
        status_layout.addWidget(self.fsm_label)
        
        main_layout.addWidget(status_group)
        
        # 坐标输入区域
        input_group = QGroupBox("添加目标点")
        input_layout = QHBoxLayout(input_group)
        
        # X坐标
        input_layout.addWidget(QLabel("X:"))
        self.x_input = QLineEdit("0.0")
        self.x_input.setMaximumWidth(80)
        self.x_input.setValidator(QDoubleValidator(-1000, 1000, 2))
        input_layout.addWidget(self.x_input)
        
        # Y坐标
        input_layout.addWidget(QLabel("Y:"))
        self.y_input = QLineEdit("0.0")
        self.y_input.setMaximumWidth(80)
        self.y_input.setValidator(QDoubleValidator(-1000, 1000, 2))
        input_layout.addWidget(self.y_input)
        
        # Z坐标
        input_layout.addWidget(QLabel("Z:"))
        self.z_input = QLineEdit("1.0")
        self.z_input.setMaximumWidth(80)
        self.z_input.setValidator(QDoubleValidator(-100, 100, 2))
        input_layout.addWidget(self.z_input)
        
        # 添加按钮
        self.add_btn = QPushButton("添加")
        self.add_btn.setObjectName("addBtn")
        self.add_btn.clicked.connect(self.addWaypoint)
        input_layout.addWidget(self.add_btn)
        
        main_layout.addWidget(input_group)
        
        # 目标点列表
        list_group = QGroupBox("目标点列表")
        list_layout = QVBoxLayout(list_group)
        
        self.waypoint_table = QTableWidget()
        self.waypoint_table.setColumnCount(4)
        self.waypoint_table.setHorizontalHeaderLabels(["序号", "X", "Y", "Z"])
        self.waypoint_table.horizontalHeader().setStretchLastSection(True)
        self.waypoint_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.waypoint_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.waypoint_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        list_layout.addWidget(self.waypoint_table)
        
        # 列表操作按钮
        list_btn_layout = QHBoxLayout()
        
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setObjectName("deleteBtn")
        self.delete_btn.clicked.connect(self.deleteSelectedWaypoint)
        list_btn_layout.addWidget(self.delete_btn)
        
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setObjectName("deleteBtn")
        self.clear_btn.clicked.connect(self.clearWaypoints)
        list_btn_layout.addWidget(self.clear_btn)
        
        self.move_up_btn = QPushButton("上移")
        self.move_up_btn.clicked.connect(self.moveWaypointUp)
        list_btn_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("下移")
        self.move_down_btn.clicked.connect(self.moveWaypointDown)
        list_btn_layout.addWidget(self.move_down_btn)
        
        list_layout.addLayout(list_btn_layout)
        main_layout.addWidget(list_group)
        
        # 文件操作按钮
        file_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存目标点")
        self.save_btn.clicked.connect(self.saveWaypoints)
        file_layout.addWidget(self.save_btn)
        
        self.load_btn = QPushButton("加载目标点")
        self.load_btn.clicked.connect(self.loadWaypoints)
        file_layout.addWidget(self.load_btn)
        
        main_layout.addLayout(file_layout)
        
        # 导航控制按钮
        nav_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("开始导航")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.startNavigation)
        nav_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止导航")
        self.stop_btn.setObjectName("deleteBtn")
        self.stop_btn.clicked.connect(self.stopNavigation)
        self.stop_btn.setEnabled(False)
        nav_layout.addWidget(self.stop_btn)
        
        main_layout.addLayout(nav_layout)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(close_btn)
    
    def addWaypoint(self):
        """添加目标点"""
        try:
            x = float(self.x_input.text())
            y = float(self.y_input.text())
            z = float(self.z_input.text())
            
            self.waypoints.append({'x': x, 'y': y, 'z': z})
            self.updateWaypointTable()
            
            # 清空输入框
            self.x_input.clear()
            self.y_input.clear()
            self.z_input.setText("1.0")
            
        except ValueError:
            notify(self, "输入错误", "请输入有效的坐标值", "warning")
    
    def updateWaypointTable(self):
        """更新目标点表格"""
        self.waypoint_table.setRowCount(len(self.waypoints))
        for i, wp in enumerate(self.waypoints):
            # 序号
            item_idx = QTableWidgetItem(str(i + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)
            self.waypoint_table.setItem(i, 0, item_idx)
            
            # X坐标
            item_x = QTableWidgetItem(f"{wp['x']:.2f}")
            item_x.setTextAlignment(Qt.AlignCenter)
            self.waypoint_table.setItem(i, 1, item_x)
            
            # Y坐标
            item_y = QTableWidgetItem(f"{wp['y']:.2f}")
            item_y.setTextAlignment(Qt.AlignCenter)
            self.waypoint_table.setItem(i, 2, item_y)
            
            # Z坐标
            item_z = QTableWidgetItem(f"{wp['z']:.2f}")
            item_z.setTextAlignment(Qt.AlignCenter)
            self.waypoint_table.setItem(i, 3, item_z)
            
            # 高亮当前正在执行的目标点
            if self.is_navigating and i == self.current_waypoint_index:
                for col in range(4):
                    self.waypoint_table.item(i, col).setBackground(QColor("#27AE60"))
    
    def deleteSelectedWaypoint(self):
        """删除选中的目标点"""
        selected_rows = set()
        for item in self.waypoint_table.selectedItems():
            selected_rows.add(item.row())
        
        for row in sorted(selected_rows, reverse=True):
            if row < len(self.waypoints):
                del self.waypoints[row]
        
        self.updateWaypointTable()
    
    def clearWaypoints(self):
        """清空目标点列表"""
        if self.waypoints:
            if confirm(
                self,
                "clear_waypoints",
                "确认清空",
                "确定要清空所有目标点吗？",
                default_no=True,
            ):
                self.waypoints.clear()
                self.updateWaypointTable()
    
    def moveWaypointUp(self):
        """上移选中的目标点"""
        current_row = self.waypoint_table.currentRow()
        if current_row > 0:
            self.waypoints[current_row], self.waypoints[current_row - 1] = \
                self.waypoints[current_row - 1], self.waypoints[current_row]
            self.updateWaypointTable()
            self.waypoint_table.selectRow(current_row - 1)
    
    def moveWaypointDown(self):
        """下移选中的目标点"""
        current_row = self.waypoint_table.currentRow()
        if current_row < len(self.waypoints) - 1:
            self.waypoints[current_row], self.waypoints[current_row + 1] = \
                self.waypoints[current_row + 1], self.waypoints[current_row]
            self.updateWaypointTable()
            self.waypoint_table.selectRow(current_row + 1)
    
    def saveWaypoints(self):
        """保存目标点到文件"""
        if not self.waypoints:
            notify(self, "保存失败", "没有可保存的目标点", "warning")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "保存目标点", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.waypoints, f, indent=2)
                notify(self, "保存成功", f"目标点已保存到:\n{filename}", "info")
            except Exception as e:
                notify_error(self, "保存失败", f"保存文件时出错:\n{str(e)}")
    
    def loadWaypoints(self):
        """从文件加载目标点"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "加载目标点", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    loaded_waypoints = json.load(f)
                
                # 验证数据格式
                for wp in loaded_waypoints:
                    if not all(key in wp for key in ['x', 'y', 'z']):
                        raise ValueError("目标点格式无效")
                
                self.waypoints = loaded_waypoints
                self.updateWaypointTable()
                notify(self, "加载成功", f"已加载 {len(self.waypoints)} 个目标点", "info")
            except Exception as e:
                notify_error(self, "加载失败", f"加载文件时出错:\n{str(e)}")
    
    def _reload_nav_cfg(self):
        """从磁盘重读 navigation_config.json（开始导航前调用，便于热更新阈值）。"""
        self.nav_cfg = _load_navigation_config()

    def _effective_goal_frame_id(self):
        """默认使用 navigation_config 的 goal_frame_id（常为 map，与 NavRL 一致）。
        仅当 sync_goal_frame_to_odom 为 true 时才改用里程计 header.frame_id（易与规划 TF 不一致，慎用）。"""
        cfg = self.nav_cfg or {}
        if cfg.get("sync_goal_frame_to_odom", False) and self.topic_subscriber:
            o = self.topic_subscriber.get_data("odometry") or {}
            fid = (o.get("frame_id") or "").strip()
            if fid:
                return fid
        return (cfg.get("goal_frame_id") or "map").strip()

    def loadDefaultWaypoints(self):
        """加载默认目标点文件"""
        default_file = os.path.join(os.path.dirname(__file__), "waypoints.json")
        if os.path.exists(default_file):
            try:
                with open(default_file, 'r') as f:
                    self.waypoints = json.load(f)
                self.updateWaypointTable()
            except Exception:
                pass
    
    def _publish_hold_goal_at_odom(self):
        """用当前里程计位置发布一次 goal，清除 NavRL 等对旧目标的内部状态（不开始航点导航也可调用）。"""
        if not self._goal_publishers or not self.topic_subscriber:
            return
        if not self.topic_subscriber.has_fresh_data("odometry", 5.0):
            return
        odom = self.topic_subscriber.get_data("odometry")
        if not odom:
            return
        pos = odom.get("position") or {}
        if hold_goal_odom_glitch_should_skip is not None:
            try:
                mx = float(rospy.get_param("/myviz/hold_goal_max_xy_jump_m", 9.0))
                mz = float(rospy.get_param("/myviz/hold_goal_max_z_jump_m", 3.0))
                oxy = float(rospy.get_param("/myviz/hold_goal_origin_snap_xy_m", 0.12))
                mpn = float(rospy.get_param("/myviz/hold_goal_origin_snap_min_prev_xy_norm_m", 3.0))
                zpp = float(rospy.get_param("/myviz/hold_goal_z_plunge_prev_min_m", 0.55))
                zpn = float(rospy.get_param("/myviz/hold_goal_z_plunge_new_max_m", 0.18))
                zpd = float(rospy.get_param("/myviz/hold_goal_z_plunge_min_drop_m", 0.95))
                zpr = float(rospy.get_param("/myviz/hold_goal_z_plunge_min_prev_xy_norm_m", 1.25))
            except Exception:
                mx, mz, oxy, mpn = 9.0, 3.0, 0.12, 3.0
                zpp, zpn, zpd, zpr = 0.55, 0.18, 0.95, 1.25
            skip_glitch, glitch_why = hold_goal_odom_glitch_should_skip(
                pos,
                getattr(self, "_hold_goal_glitch_prev_xyz", None),
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
                rospy.logwarn_throttle(
                    4.0,
                    "waypoint_dialog: 跳过 hold goal（里程计异常）: %s",
                    glitch_why,
                )
                return
        frame_id = self._effective_goal_frame_id()
        hold = PoseStamped()
        hold.header.frame_id = frame_id
        hold.header.stamp = rospy.Time.now()
        hold.pose.position.x = float(pos.get("x", 0.0))
        hold.pose.position.y = float(pos.get("y", 0.0))
        hold.pose.position.z = float(pos.get("z", 0.0))
        ort = odom.get("orientation") or {}
        if isinstance(ort, dict) and all(k in ort for k in ("x", "y", "z", "w")):
            hold.pose.orientation.x = float(ort.get("x", 0.0))
            hold.pose.orientation.y = float(ort.get("y", 0.0))
            hold.pose.orientation.z = float(ort.get("z", 0.0))
            hold.pose.orientation.w = float(ort.get("w", 1.0))
        else:
            hold.pose.orientation.w = 1.0
        try:
            for pub in self._goal_publishers.values():
                pub.publish(hold)
        except Exception:
            pass
        try:
            self._hold_goal_glitch_prev_xyz = (
                float(pos.get("x", 0.0)),
                float(pos.get("y", 0.0)),
                float(pos.get("z", 0.0)),
            )
        except Exception:
            pass

    def startNavigation(self):
        """开始导航"""
        if not self.waypoints:
            notify(self, "无法导航", "请先添加目标点", "warning")
            return
        
        if not confirm(
            self,
            "start_navigation",
            "确认导航",
            f"确定要开始导航到 {len(self.waypoints)} 个目标点吗？",
            default_no=True,
        ):
            return
        
        self.is_navigating = True
        self._hold_goal_glitch_prev_xyz = None
        self.current_waypoint_index = 0
        self._reload_nav_cfg()
        cfg = self.nav_cfg or {}

        # 先通知主窗口进入航点阶段：立刻停待机周期性 hold goal，避免与即将发布的航点竞争
        try:
            self.navigationStarted.emit(list(self.waypoints))
        except Exception:
            pass

        # NavRL 等：先发「当前位 hold」再发远点会让策略先在原地收敛再转弯，录屏像在起点挂机。
        # navigation_config.json 里 skip_hold_goal_before_navigation 默认 true，仅兼容旧栈时可设 false。
        if not cfg.get("skip_hold_goal_before_navigation", True):
            self._publish_hold_goal_at_odom()
            try:
                rospy.sleep(0.12)
            except Exception:
                pass

        # 更新UI状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.add_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._leg_saw_exec = False
        self._vel_still_since = None

        self.status_label.setText(f"正在导航到目标点 1/{len(self.waypoints)}")
        self.status_label.setStyleSheet("color: #27AE60; font-weight: bold;")

        # 发送第一个目标点（直接追航点，减少起点乱线）
        self.publishCurrentWaypoint()

        # 启动FSM状态检查定时器
        self.fsm_check_timer.start(500)  # 每500ms检查一次
        
        self.updateWaypointTable()
    
    def stopNavigation(self):
        """停止导航"""
        self.is_navigating = False
        self._publish_hold_goal_at_odom()
        self.fsm_check_timer.stop()
        self._cerlab_goal_timer.stop()
        self._cerlab_goal_msg = None
        self._using_planner_for_leg = False
        self._recovery_active = False
        self._recovery_until_ts = 0.0
        
        # 更新UI状态
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self._leg_saw_exec = False
        
        self.status_label.setText("导航已停止")
        self.status_label.setStyleSheet("color: #E74C3C; font-weight: bold;")
        
        self.updateWaypointTable()
        try:
            self.navigationEnded.emit()
        except Exception:
            pass
    
    def publishCurrentWaypoint(self):
        """发布当前目标点"""
        if not self.is_navigating or self.current_waypoint_index >= len(self.waypoints):
            return
        
        wp = self.waypoints[self.current_waypoint_index]
        frame_id = self._effective_goal_frame_id()
        
        # 创建目标点消息
        goal_msg = PoseStamped()
        goal_msg.header.frame_id = frame_id
        goal_msg.header.stamp = rospy.Time.now()
        
        goal_msg.pose.position.x = wp['x']
        goal_msg.pose.position.y = wp['y']
        goal_msg.pose.position.z = wp['z']
        
        # 设置朝向（默认向前）
        goal_msg.pose.orientation.x = 0.0
        goal_msg.pose.orientation.y = 0.0
        goal_msg.pose.orientation.z = 0.0
        goal_msg.pose.orientation.w = 1.0
        
        self._leg_saw_exec = False
        self._last_goal_publish_time = time.time()
        self._stuck_best_distance = None
        self._stuck_last_progress_time = self._last_goal_publish_time
        self._stuck_recovery_count = 0
        self._recovery_active = False
        self._recovery_until_ts = 0.0

        # CERLAB 仿真直控：若主窗口已启用 cerlab 后端，且外部规划器不可用时回退 setpoint_pose
        use_cerlab = False
        try:
            p = self.parent()
            bn = getattr(p, "control_backend_name", "") if p is not None else ""
            use_cerlab = "cerlab" in (bn or "").lower()
        except Exception:
            use_cerlab = False

        use_planner = False
        try:
            if self._goal_publishers and self.topic_subscriber:
                # 仅当 ego 等规划器 FSM 近期有更新时才走「规划器」分支；勿用 is_topic_active（曾订阅过会一直为 True，NavRL 场景下误判）
                use_planner = self.topic_subscriber.has_fresh_data("fsm_state", 2.0)
        except Exception:
            use_planner = False

        if use_planner and self._goal_publishers:
            try:
                self._using_planner_for_leg = True
                for topic, pub in self._goal_publishers.items():
                    pub.publish(goal_msg)
                print(
                    f"[Planner] 已发布目标点 {self.current_waypoint_index + 1}: "
                    f"({wp['x']}, {wp['y']}, {wp['z']}) -> {list(self._goal_publishers.keys())}"
                )
                return
            except Exception as e:
                print(f"[Planner] 发布目标点失败，将回退 CERLAB 直控: {e}")

        if use_cerlab and self._cerlab_setpoint_pub and self._cerlab_posctrl_pub:
            try:
                self._using_planner_for_leg = False
                if self._cerlab_takeoff_pub:
                    self._cerlab_takeoff_pub.publish(Empty())
                if self._cerlab_velmode_pub:
                    self._cerlab_velmode_pub.publish(Bool(data=False))
                self._cerlab_posctrl_pub.publish(Bool(data=True))

                goal_msg.header.frame_id = frame_id
                self._cerlab_setpoint_pub.publish(goal_msg)
                # CERLAB 位置控制在部分版本需要周期性刷新 setpoint 才会持续机动
                self._cerlab_goal_msg = goal_msg
                if not self._cerlab_goal_timer.isActive():
                    self._cerlab_goal_timer.start(100)  # 10Hz
                print(
                    f"[CERLAB] 已发布 setpoint_pose {self.current_waypoint_index + 1}: ({wp['x']}, {wp['y']}, {wp['z']})"
                )
                return
            except Exception as e:
                print(f"[CERLAB] 发布 setpoint_pose 失败，将回退 goal_topics: {e}")

        # 默认：发布到外部规划器 goal_topics
        if not self._goal_publishers:
            print("目标点发布者未初始化")
            return
        try:
            for topic, pub in self._goal_publishers.items():
                pub.publish(goal_msg)
            # True：避免在「仅 move_base / NavRL」时走 CERLAB setpoint 脱困（会与 RL 的 cmd_vel 抢控）
            self._using_planner_for_leg = True
            print(
                f"已发布目标点 {self.current_waypoint_index + 1}: ({wp['x']}, {wp['y']}, {wp['z']}) -> {list(self._goal_publishers.keys())}"
            )
        except Exception as e:
            print(f"发布目标点失败: {e}")

    def _republish_cerlab_goal(self):
        """导航期间持续刷新 CERLAB setpoint，避免单次消息丢失或控制器不保持目标。"""
        if not self.is_navigating:
            self._cerlab_goal_timer.stop()
            return
        if self._cerlab_goal_msg is None or self._cerlab_setpoint_pub is None:
            return
        try:
            self._cerlab_goal_msg.header.stamp = rospy.Time.now()
            self._cerlab_setpoint_pub.publish(self._cerlab_goal_msg)
        except Exception:
            pass
    
    def _waypoint_progress_metrics(self):
        """当前航点与机体的水平距、三维距、竖直偏差与合成速度；无里程计时返回 None。"""
        if not self.topic_subscriber or self.current_waypoint_index >= len(self.waypoints):
            return None
        odom = self.topic_subscriber.get_data("odometry")
        if not odom:
            return None
        pos = odom.get("position") or {}
        wp = self.waypoints[self.current_waypoint_index]
        dx = float(pos.get("x", 0.0)) - float(wp["x"])
        dy = float(pos.get("y", 0.0)) - float(wp["y"])
        dz = float(pos.get("z", 0.0)) - float(wp["z"])
        d_xy = (dx * dx + dy * dy) ** 0.5
        d_3d = (dx * dx + dy * dy + dz * dz) ** 0.5
        speed = self._estimate_odom_speed_m_s()
        return {"d_xy": d_xy, "d_z": abs(dz), "d_3d": d_3d, "speed": speed}

    def _estimate_odom_speed_m_s(self):
        ts = self.topic_subscriber
        if not ts:
            return None
        v = ts.get_data("velocity")
        if not v:
            return None
        lin = v.get("linear") or {}
        lx = float(lin.get("x", 0.0))
        ly = float(lin.get("y", 0.0))
        lz = float(lin.get("z", 0.0))
        return (lx * lx + ly * ly + lz * lz) ** 0.5

    def _distance_to_current_waypoint(self):
        """与当前航点的“标量距离”，与 waypoint_advance.distance_mode 一致，供脱困等逻辑使用。"""
        wa = self.nav_cfg.get("waypoint_advance") or {}
        m = self._waypoint_progress_metrics()
        if m is None:
            return None
        mode = (wa.get("distance_mode") or "horizontal").lower()
        if mode == "3d":
            return m["d_3d"]
        if mode == "hybrid":
            xy_th = float(wa.get("distance_fallback_xy_m", wa.get("distance_fallback_m", 0.55)))
            z_th = float(wa.get("distance_fallback_z_m", 0.55))
            if m["d_xy"] < xy_th and m["d_z"] < z_th:
                return 0.0
            return max(m["d_xy"] - xy_th, m["d_z"] - z_th, 0.0) + 0.01
        return m["d_xy"]

    def checkFSMState(self):
        """检查FSM状态，判断是否需要发送下一个目标点"""
        if not self.is_navigating:
            return
        
        wa = self.nav_cfg.get("waypoint_advance") or {}
        exec_state = int(wa.get("exec_state", 4))
        wait_state = int(wa.get("wait_state", 1))
        dist_th_default = float(wa.get("distance_fallback_m", 0.35))
        min_sec = float(wa.get("min_seconds_before_distance_check", 2.5))
        mode = (wa.get("distance_mode") or "horizontal").lower()
        vel_cap = float(wa.get("require_velocity_below_m_s", 0.0))
        vel_dur = float(wa.get("velocity_below_required_seconds", 0.45))
        
        # 获取FSM状态
        fsm_state = 0
        fsm_state_name = "UNKNOWN"
        fsm_active = False
        
        if self.topic_subscriber:
            fsm_active = self.topic_subscriber.has_fresh_data("fsm_state", 2.0)
            fsm_data = self.topic_subscriber.get_data("fsm_state")
            if fsm_data:
                fsm_state = fsm_data.get("state", 0)
                fsm_state_name = fsm_data.get("state_name", "UNKNOWN")
        
        if fsm_active:
            self.fsm_label.setText(f"FSM: {fsm_state_name}")
            if fsm_state == 1:
                self.fsm_label.setStyleSheet("color: #27AE60;")
            elif fsm_state == 4:
                self.fsm_label.setStyleSheet("color: #3498DB;")
            elif fsm_state == 5:
                self.fsm_label.setStyleSheet("color: #E74C3C;")
            else:
                self.fsm_label.setStyleSheet("color: #F39C12;")
        else:
            self.fsm_label.setText("FSM: 无近期数据（NavRL 用距离/速度判定到达）")
            self.fsm_label.setStyleSheet("color: #95A5A6;")
        
        should_advance = False
        if fsm_active:
            if fsm_state == exec_state:
                self._leg_saw_exec = True
            if self._leg_saw_exec and fsm_state == wait_state:
                should_advance = True
        
        metrics = self._waypoint_progress_metrics()
        d = self._distance_to_current_waypoint()
        elapsed = time.time() - self._last_goal_publish_time

        dist_ok = False
        if metrics is not None:
            if mode == "hybrid":
                xy_th = float(wa.get("distance_fallback_xy_m", wa.get("distance_fallback_m", 0.55)))
                z_th = float(wa.get("distance_fallback_z_m", 0.55))
                dist_ok = metrics["d_xy"] < xy_th and metrics["d_z"] < z_th
            elif mode == "3d":
                dist_ok = metrics["d_3d"] < dist_th_default
            else:
                dist_ok = metrics["d_xy"] < dist_th_default
        vel_ok = True
        if vel_cap > 0 and metrics is not None and metrics.get("speed") is not None:
            if metrics["speed"] < vel_cap:
                if self._vel_still_since is None:
                    self._vel_still_since = time.time()
            else:
                self._vel_still_since = None
            vel_ok = (
                self._vel_still_since is not None
                and (time.time() - self._vel_still_since) >= vel_dur
            )
        else:
            self._vel_still_since = None

        if not should_advance and metrics is not None:
            if dist_ok and vel_ok and elapsed >= min_sec:
                should_advance = True
            elif elapsed >= min_sec:
                self._maybe_recover_from_stuck(d, dist_th_default)

        if self.is_navigating and metrics is not None:
            spd = metrics.get("speed")
            sp_str = f"{spd:.2f}" if spd is not None else "--"
            self.status_label.setText(
                f"目标 {self.current_waypoint_index + 1}/{len(self.waypoints)} | "
                f"水平 {metrics['d_xy']:.2f}m 三维 {metrics['d_3d']:.2f}m | "
                f"速 {sp_str}m/s | 判定:{mode}"
            )
            self.status_label.setStyleSheet("color: #27AE60; font-weight: bold;")

        if should_advance:
            self.current_waypoint_index += 1
            if self.current_waypoint_index < len(self.waypoints):
                self.status_label.setText(
                    f"正在导航到目标点 {self.current_waypoint_index + 1}/{len(self.waypoints)}"
                )
                self.publishCurrentWaypoint()
                self.updateWaypointTable()
            else:
                self.navigationComplete()
    
    def navigationComplete(self):
        """导航完成"""
        self.is_navigating = False
        self.fsm_check_timer.stop()
        self._cerlab_goal_timer.stop()
        self._cerlab_goal_msg = None
        self._using_planner_for_leg = False
        self._recovery_active = False
        self._recovery_until_ts = 0.0
        
        # 更新UI状态
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        
        self.status_label.setText("所有目标点已完成!")
        self.status_label.setStyleSheet("color: #27AE60; font-weight: bold;")
        self._leg_saw_exec = False
        
        self.updateWaypointTable()
        
        notify(self, "导航完成", "已成功到达所有目标点！", "info")
        try:
            self.navigationEnded.emit()
        except Exception:
            pass

    def _maybe_recover_from_stuck(self, distance_to_goal, dist_threshold):
        """CERLAB 直控下的自动脱困：卡住时临时抬升+侧移，然后回到原目标。"""
        if self._using_planner_for_leg:
            return
        if self._cerlab_setpoint_pub is None or self.topic_subscriber is None:
            return
        if distance_to_goal is None:
            return

        now = time.time()
        if self._stuck_best_distance is None:
            self._stuck_best_distance = distance_to_goal
            self._stuck_last_progress_time = now
            return

        # 有明显进展就刷新“最后进展时间”
        if distance_to_goal < self._stuck_best_distance - 0.08:
            self._stuck_best_distance = distance_to_goal
            self._stuck_last_progress_time = now
            return

        # 恢复阶段结束后，重新下发原目标
        if self._recovery_active and now >= self._recovery_until_ts:
            self._recovery_active = False
            self.publishCurrentWaypoint()
            return
        if self._recovery_active:
            return

        wa = self.nav_cfg.get("waypoint_advance") or {}
        stuck_sec = float(wa.get("stuck_no_progress_sec", 5.5))
        # 卡住判定：离目标还远 + 数秒无进展
        no_progress_sec = now - self._stuck_last_progress_time
        if distance_to_goal <= dist_threshold + 0.15 or no_progress_sec < stuck_sec:
            return
        if self._stuck_recovery_count >= 6:
            return

        odom = self.topic_subscriber.get_data("odometry") or {}
        pos = odom.get("position") or {}
        if self.current_waypoint_index >= len(self.waypoints):
            return
        wp = self.waypoints[self.current_waypoint_index]

        cx = float(pos.get("x", 0.0))
        cy = float(pos.get("y", 0.0))
        cz = float(pos.get("z", 1.0))
        gx = float(wp.get("x", cx))
        gy = float(wp.get("y", cy))
        gz = float(wp.get("z", 1.0))

        dx = gx - cx
        dy = gy - cy
        norm = (dx * dx + dy * dy) ** 0.5
        if norm < 1e-3:
            return

        # 交替左右侧移，叠加抬升，避开局部卡死点
        side_sign = -1.0 if (self._stuck_recovery_count % 2 == 0) else 1.0
        px = side_sign * (-dy / norm)
        py = side_sign * (dx / norm)

        escape = PoseStamped()
        escape.header.frame_id = self._effective_goal_frame_id()
        escape.header.stamp = rospy.Time.now()
        escape.pose.position.x = cx + 0.9 * px
        escape.pose.position.y = cy + 0.9 * py
        escape.pose.position.z = max(cz + 0.55, gz + 0.25, 1.2)
        escape.pose.orientation.w = 1.0

        try:
            self._cerlab_setpoint_pub.publish(escape)
            self._cerlab_goal_msg = escape
            if not self._cerlab_goal_timer.isActive():
                self._cerlab_goal_timer.start(100)
            self._recovery_active = True
            self._recovery_until_ts = now + 1.8
            self._stuck_recovery_count += 1
            self._stuck_last_progress_time = now
            self.status_label.setText(
                f"检测到卡住，执行自救机动 {self._stuck_recovery_count}/6..."
            )
            self.status_label.setStyleSheet("color: #F39C12; font-weight: bold;")
            print(
                f"[RECOVERY] leg={self.current_waypoint_index+1} dist={distance_to_goal:.2f} "
                f"escape=({escape.pose.position.x:.2f},{escape.pose.position.y:.2f},{escape.pose.position.z:.2f})"
            )
        except Exception as ex:
            print(f"[RECOVERY] 发布自救点失败: {ex}")
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.is_navigating:
            if not confirm(
                self,
                "close_while_navigating",
                "确认关闭",
                "正在导航中，确定要关闭吗？",
                default_no=True,
            ):
                event.ignore()
                return
            
            self.stopNavigation()
        
        event.accept()
