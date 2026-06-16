#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import sys
from collections import deque
import pathlib
import rospy
from sensor_msgs.msg import BatteryState, Image, Imu, CameraInfo, PointField, PointCloud2
import sensor_msgs.point_cloud2 as pc2
import numpy as np
from mavros_msgs.msg import State, RCIn
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import TwistStamped, PoseStamped
from std_msgs.msg import Float32, Float64, Int32
from visualization_msgs.msg import Marker, MarkerArray
import threading
import time
import math
import cv2
from cv_bridge import CvBridge, CvBridgeError

class TopicsSubscriber:
    def __init__(self, config_file="topics_config.json"):
        # 初始化数据存储字典
        self.data = {
            "battery": {
                "voltage": 0.0,
                "current": 0.0, 
                "percentage": 0.0,
                "temperature": 0.0
            },
            "status": {
                "connected": False,
                "armed": False,
                "guided": False,
                "mode": ""
            },
            "odometry": {
                "position": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0
                },
                "frame_id": "",
                "orientation": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "w": 0.0
                }
            },
            "velocity": {
                "linear": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0
                },
                "angular": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0
                },
                "speed": 0.0  # 合成的线速度
            },
            "camera": {
                "image": None,  # 存储OpenCV格式的图像
                "width": 0,
                "height": 0,
                "encoding": ""
            },
            "depth": {
                "image": None,  # 存储OpenCV格式的深度图像
                "width": 0,
                "height": 0,
                "encoding": ""
            },
            "bird_view": {
                "image": None,
                "width": 0,
                "height": 0,
                "encoding": ""
            },
            "attitude": {
                "pitch": 0.0,       # 俯仰角
                "roll": 0.0,        # 滚转角
                "yaw": 0.0,         # 偏航角
                "timestamp": 0.0    # 时间戳
            },
            "rc_input": {
                "channels": [],
                "rssi": 0
            },
            "fsm_state": {
                "state": 0,  # FSM状态码
                "state_name": "INIT",  # 状态名称
                "timestamp": 0.0
            },
            "obstacle_states": {
                "obstacles": [],  # 障碍物列表，每个包含 position, velocity, acceleration, size
                "count": 0,  # 障碍物数量
                "timestamp": 0.0
            },
            # 由深度图中心 ROI 估计前向最近距离（GT/Marker 未报行人时仍可做粗预警）
            "depth_proximity": {
                "ok": False,
                "near_m": -1.0,
                "min_m": -1.0,
                "median_m": -1.0,
                "valid_frac": 0.0,
                "timestamp": 0.0,
            },
        }
        
        # 回调函数字典
        self.callbacks = {}
        
        # 订阅者字典，用于跟踪订阅状态
        self.subscribers = {}
        
        # 话题是否活跃状态
        self.topics_active = {
            "battery": False,
            "status": False,
            "odometry": False,
            "velocity": False,
            "camera": False,
            "depth": False,
            "bird_view": False,
            "attitude": False,
            "rc_input": False,
            "fsm_state": False,
            "obstacle_states": False
        }

        # 最近一次收到各话题数据的时间戳（用于“连接状态”动态判定）
        self.last_message_time = {k: 0.0 for k in self.topics_active.keys()}
        
        # 初始化cv_bridge
        self.bridge = CvBridge()

        # 中部 RViz：飞行轨迹（由里程计累积，话题供 rviz/Path 订阅）
        self._flight_path_pub = rospy.Publisher(
            "/myviz/flight_path", Path, queue_size=1, latch=False
        )
        self._path_trail = deque(maxlen=1600)
        self._last_path_publish_wall = 0.0
        self._last_odom_stamp = None
        self._last_trail_pos = None  # 上次写入轨迹的空间点，用于降采样
        self._flight_path_frame = rospy.get_param("/myviz/flight_path_frame", "map")
        # 与里程计 header.frame_id 对齐，避免 Path 用 map、Marker 用 world 导致中部机体 TF 错误而不显示
        self._sync_viz_frame_to_odom = rospy.get_param(
            "/myviz/sync_visualization_frame_to_odom", True
        )
        self._announced_odom_frame = False
        self._flight_path_min_step_m = float(rospy.get_param("/myviz/flight_path_min_step_m", 0.32))
        self._flight_path_min_step_slow_m = float(
            rospy.get_param("/myviz/flight_path_min_step_slow_m", 0.72)
        )
        self._flight_path_slow_speed_mps = float(
            rospy.get_param("/myviz/flight_path_slow_speed_mps", 0.14)
        )
        self._flight_path_z_step_m = float(rospy.get_param("/myviz/flight_path_z_step_m", 0.38))
        self._drone_marker_pub = rospy.Publisher(
            "/myviz/drone_marker", Marker, queue_size=1, latch=True
        )
        self._depth_cloud_pub = rospy.Publisher(
            "/myviz/depth_cloud", PointCloud2, queue_size=1, latch=False
        )
        self._depth_cam_info = None
        self._last_drone_marker_wall = 0.0
        self._last_depth_cloud_wall = 0.0
        # 更密的深度投影：stride 越小云越厚（CPU 越高）；可用 rosparam 调回
        self._depth_cloud_stride = int(rospy.get_param("/myviz/depth_cloud_stride", 3))
        self._depth_cloud_max_z = float(rospy.get_param("/myviz/depth_cloud_max_range_m", 26.0))
        self._depth_cloud_max_points = int(rospy.get_param("/myviz/depth_cloud_max_points", 120000))
        self._depth_cloud_min_interval = float(
            rospy.get_param("/myviz/depth_cloud_min_interval", 0.42)
        )
        # 默认开启：中部 RViz「myviz depth cloud」依赖 /myviz/depth_cloud；若卡顿可
        # rosparam set /myviz/enable_depth_cloud false 或加大 depth_cloud_stride /
        # depth_cloud_max_points 以减负
        self._depth_cloud_enabled = rospy.get_param("/myviz/enable_depth_cloud", True)
        self._drone_marker_min_interval = float(
            rospy.get_param("/myviz/drone_marker_min_interval", 0.075)
        )
        self._drone_mesh_resolved = False
        self._drone_mesh_uri = ""
        self._drone_mesh_warned = False
        self._drone_mesh_lock = threading.Lock()
        self._last_imu_attitude_wall = 0.0
        self._last_depth_proximity_wall = 0.0

        # 加载配置文件
        self.load_config(config_file)
        
        # 初始化ROS订阅者(异步方式)
        self.running = True
        self.subscriber_thread = threading.Thread(target=self.monitor_topics)
        self.subscriber_thread.daemon = True
        self.subscriber_thread.start()
    
    def load_config(self, config_file):
        """加载话题订阅配置文件"""
        try:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
            rospy.loginfo(f"成功加载配置文件: {config_file}")
        except Exception as e:
            rospy.logerr(f"加载配置文件失败: {str(e)}")
            self.config = {}
    
    def monitor_topics(self):
        """异步监控话题，当话题可用时自动订阅"""
        while self.running and not rospy.is_shutdown():
            try:
                # 检查并订阅可用的话题
                self.check_and_subscribe_topics()
                
                # 每秒检查一次
                time.sleep(1.0)
            except Exception as e:
                rospy.logerr(f"监控话题时出错: {str(e)}")
                time.sleep(2.0)
    
    def _topic_candidates(self, key):
        cfg = self.config.get(key) or {}
        out = []
        p = (cfg.get("topic") or "").strip()
        if p:
            out.append(p)
        for a in cfg.get("alt_topics") or []:
            a = (a or "").strip()
            if a and a not in out:
                out.append(a)
        return out

    def _first_matching_topic(self, key, published_topics):
        for t in self._topic_candidates(key):
            if t in published_topics:
                return t
        return ""

    def check_and_subscribe_topics(self):
        """检查并订阅可用的话题"""
        # 获取当前发布的所有话题
        published_topics = dict(rospy.get_published_topics())

        # 每轮都根据“是否存在发布者”刷新基础活跃态，避免仿真重启后状态粘住
        for key in ("battery", "status", "odometry", "velocity", "camera", "depth", "attitude", "rc_input", "fsm_state"):
            try:
                if key in ("battery", "status", "attitude"):
                    self.topics_active[key] = bool(self._first_matching_topic(key, published_topics))
                else:
                    t = self.config.get(key, {}).get("topic", "")
                    self.topics_active[key] = bool(t and t in published_topics)
            except Exception:
                self.topics_active[key] = False
        
        batt_topic = self._first_matching_topic("battery", published_topics)
        if "battery" in self.config and batt_topic:
            if "battery" not in self.subscribers or not self.subscribers["battery"]:
                try:
                    self.subscribers["battery"] = rospy.Subscriber(
                        batt_topic,
                        BatteryState,
                        self.battery_callback,
                    )
                    self.topics_active["battery"] = True
                    rospy.loginfo(f"成功订阅电池话题: {batt_topic}")
                except Exception as e:
                    rospy.logerr(f"订阅电池话题失败: {str(e)}")
        
        st_topic = self._first_matching_topic("status", published_topics)
        if "status" in self.config and st_topic:
            if "status" not in self.subscribers or not self.subscribers["status"]:
                try:
                    self.subscribers["status"] = rospy.Subscriber(
                        st_topic,
                        State,
                        self.state_callback,
                    )
                    self.topics_active["status"] = True
                    rospy.loginfo(f"成功订阅状态话题: {st_topic}")
                except Exception as e:
                    rospy.logerr(f"订阅状态话题失败: {str(e)}")
        
        # 检查并订阅位置话题
        if "odometry" in self.config and self.config["odometry"]["topic"] in published_topics:
            if "odometry" not in self.subscribers or not self.subscribers["odometry"]:
                try:
                    self.subscribers["odometry"] = rospy.Subscriber(
                        self.config["odometry"]["topic"],
                        Odometry,
                        self.odometry_callback
                    )
                    self.topics_active["odometry"] = True
                    rospy.loginfo(f"成功订阅位置话题: {self.config['odometry']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅位置话题失败: {str(e)}")
        
        # 检查并订阅速度话题
        if "velocity" in self.config and self.config["velocity"]["topic"] in published_topics:
            if "velocity" not in self.subscribers or not self.subscribers["velocity"]:
                try:
                    self.subscribers["velocity"] = rospy.Subscriber(
                        self.config["velocity"]["topic"],
                        TwistStamped,
                        self.velocity_callback
                    )
                    self.topics_active["velocity"] = True
                    rospy.loginfo(f"成功订阅速度话题: {self.config['velocity']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅速度话题失败: {str(e)}")
                    
        # 检查并订阅图像话题
        if "camera" in self.config and self.config["camera"]["topic"] in published_topics:
            if "camera" not in self.subscribers or not self.subscribers["camera"]:
                try:
                    self.subscribers["camera"] = rospy.Subscriber(
                        self.config["camera"]["topic"],
                        Image,
                        self.camera_callback
                    )
                    self.topics_active["camera"] = True
                    rospy.loginfo(f"成功订阅图像话题: {self.config['camera']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅图像话题失败: {str(e)}")
                    
        # 检查并订阅深度图像话题
        if "depth" in self.config and self.config["depth"]["topic"] in published_topics:
            if "depth" not in self.subscribers or not self.subscribers["depth"]:
                try:
                    self.subscribers["depth"] = rospy.Subscriber(
                        self.config["depth"]["topic"],
                        Image,
                        self.depth_callback
                    )
                    self.topics_active["depth"] = True
                    rospy.loginfo(f"成功订阅深度图像话题: {self.config['depth']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅深度图像话题失败: {str(e)}")

            info_topic = self._derive_depth_camera_info_topic()
            if info_topic and (
                "depth_camera_info" not in self.subscribers or not self.subscribers["depth_camera_info"]
            ):
                try:
                    self.subscribers["depth_camera_info"] = rospy.Subscriber(
                        info_topic,
                        CameraInfo,
                        self.depth_camera_info_callback,
                        queue_size=1,
                    )
                    rospy.loginfo(f"已订阅深度相机内参: {info_topic}（无发布者时仍可用近似内参生成点云）")
                except Exception as e:
                    rospy.logerr(f"订阅深度相机内参失败: {str(e)}")
        
        # 检查并订阅鸟瞰图话题
        if "bird_view" in self.config:
            # 尝试强制订阅鸟瞰图话题，不管是否在已发布话题列表中
            if "bird_view" not in self.subscribers or not self.subscribers["bird_view"]:
                try:
                    print(f"尝试订阅鸟瞰图话题: {self.config['bird_view']['topic']}")
                    self.subscribers["bird_view"] = rospy.Subscriber(
                        self.config["bird_view"]["topic"],
                        Image,
                        self.bird_view_callback,
                        queue_size=1
                    )
                    rospy.loginfo(f"成功订阅鸟瞰图话题: {self.config['bird_view']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅鸟瞰图话题失败: {str(e)}")
                    print(f"订阅鸟瞰图话题时出错: {str(e)}")
                    self.topics_active["bird_view"] = False
        
        att_topic = self._first_matching_topic("attitude", published_topics)
        if "attitude" in self.config and att_topic:
            if "attitude" not in self.subscribers or not self.subscribers["attitude"]:
                try:
                    from sensor_msgs.msg import Imu
                    self.subscribers["attitude"] = rospy.Subscriber(
                        att_topic,
                        Imu,
                        self.attitude_callback,
                    )
                    self.topics_active["attitude"] = True
                    rospy.loginfo(f"成功订阅姿态数据话题: {att_topic}")
                except Exception as e:
                    rospy.logerr(f"订阅姿态数据话题失败: {str(e)}")
                    
        # 检查并订阅RC输入话题
        if "rc_input" in self.config and self.config["rc_input"]["topic"] in published_topics:
            if "rc_input" not in self.subscribers or not self.subscribers["rc_input"]:
                try:
                    self.subscribers["rc_input"] = rospy.Subscriber(
                        self.config["rc_input"]["topic"],
                        RCIn,
                        self.rc_input_callback
                    )
                    self.topics_active["rc_input"] = True
                    rospy.loginfo(f"成功订阅RC输入话题: {self.config['rc_input']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅RC输入话题失败: {str(e)}")
        
        # 检查并订阅FSM状态话题
        if "fsm_state" in self.config and self.config["fsm_state"]["topic"] in published_topics:
            if "fsm_state" not in self.subscribers or not self.subscribers["fsm_state"]:
                try:
                    self.subscribers["fsm_state"] = rospy.Subscriber(
                        self.config["fsm_state"]["topic"],
                        Int32,
                        self.fsm_state_callback
                    )
                    self.topics_active["fsm_state"] = True
                    rospy.loginfo(f"成功订阅FSM状态话题: {self.config['fsm_state']['topic']}")
                except Exception as e:
                    rospy.logerr(f"订阅FSM状态话题失败: {str(e)}")
        
        # 检查并订阅障碍物状态话题（支持多话题回退）
        configured_obstacle_topic = self.config.get("obstacle_states", {}).get("topic", "")
        obstacle_candidates = [configured_obstacle_topic] if configured_obstacle_topic else []
        obstacle_candidates.extend([
            "/onboard_detector/GT_obstacle_bbox",
            "/onboard_detector/states_markers",
            "/states_markers",
            "/onboard_detector/dynamic_bboxes",
        ])
        # 去重并保持顺序
        obstacle_candidates = [t for i, t in enumerate(obstacle_candidates) if t and t not in obstacle_candidates[:i]]

        obstacle_topic = None
        for topic in obstacle_candidates:
            if topic in published_topics:
                obstacle_topic = topic
                break

        if obstacle_topic and ("obstacle_states" not in self.subscribers or not self.subscribers["obstacle_states"]):
            try:
                obstacle_msg_type = self.config.get("obstacle_states", {}).get("msg_type", "")
                # 兼容两种障碍物消息：
                # 1) obj_state_msgs/ObjectsStates（原始工程）
                # 2) visualization_msgs/MarkerArray（当前仿真工程）
                if obstacle_msg_type == "visualization_msgs/MarkerArray":
                    self.subscribers["obstacle_states"] = rospy.Subscriber(
                        obstacle_topic,
                        MarkerArray,
                        self.obstacle_markers_callback
                    )
                else:
                    from obj_state_msgs.msg import ObjectsStates
                    self.subscribers["obstacle_states"] = rospy.Subscriber(
                        obstacle_topic,
                        ObjectsStates,
                        self.obstacle_states_callback
                    )
                rospy.loginfo(f"成功订阅障碍物状态话题: {obstacle_topic}")
            except ImportError as e:
                rospy.logerr(f"导入obj_state_msgs失败: {str(e)}")
            except Exception as e:
                rospy.logerr(f"订阅障碍物状态话题失败: {str(e)}")

        if self.subscribers.get("bird_view"):
            self.topics_active["bird_view"] = self.has_fresh_data("bird_view", 5.0)
        else:
            self.topics_active["bird_view"] = False
        if self.subscribers.get("obstacle_states"):
            self.topics_active["obstacle_states"] = self.has_fresh_data("obstacle_states", 5.0)
        else:
            self.topics_active["obstacle_states"] = False

    def _derive_depth_camera_info_topic(self):
        cfg = (self.config.get("depth_camera_info") or {}).get("topic", "")
        if cfg and str(cfg).strip():
            return str(cfg).strip()
        depth_topic = (self.config.get("depth") or {}).get("topic", "/camera/depth/image_raw")
        if "/image_raw" in depth_topic:
            return depth_topic.replace("/image_raw", "/camera_info")
        if "/" in depth_topic:
            return depth_topic.rsplit("/", 1)[0] + "/camera_info"
        return "/camera/depth/camera_info"

    def depth_camera_info_callback(self, msg):
        self._depth_cam_info = msg

    def _intrinsics_for_image(self, w, h):
        ci = self._depth_cam_info
        if ci is None or not getattr(ci, "K", None) or len(ci.K) < 9:
            fx = 0.9 * float(max(w, h))
            return fx, fx, 0.5 * float(w), 0.5 * float(h)
        K = list(ci.K)
        return float(K[0]), float(K[4]), float(K[2]), float(K[5])

    @staticmethod
    def _depth_pixel_to_meters(raw, arr_dtype):
        if np.issubdtype(arr_dtype, np.integer):
            return float(raw) * 0.001
        v = float(raw)
        if math.isnan(v) or math.isinf(v):
            return -1.0
        return v

    def _build_depth_point_cloud(self, depth_msg, cv_image):
        if cv_image is None or cv_image.size == 0:
            return None
        if len(cv_image.shape) == 3:
            cv_image = cv_image[:, :, 0]
        h, w = int(cv_image.shape[0]), int(cv_image.shape[1])
        fx, fy, cx, cy = self._intrinsics_for_image(w, h)
        stride = max(1, self._depth_cloud_stride)
        max_z = self._depth_cloud_max_z
        max_pts = max(2000, int(self._depth_cloud_max_points))

        sub = np.ascontiguousarray(cv_image[::stride, ::stride])
        hh, ww = sub.shape
        if hh == 0 or ww == 0:
            return None
        v_coords = np.arange(0, h, stride, dtype=np.float32)[:hh]
        u_coords = np.arange(0, w, stride, dtype=np.float32)[:ww]
        V, U = np.meshgrid(v_coords, u_coords, indexing="ij")

        if np.issubdtype(sub.dtype, np.integer):
            zm = sub.astype(np.float32) * 0.001
        else:
            zm = np.nan_to_num(sub.astype(np.float32), nan=-1.0, posinf=-1.0, neginf=-1.0)

        m = (zm > 0.05) & (zm <= max_z) & np.isfinite(zm)
        if not np.any(m):
            return None
        Uf = U[m].astype(np.float32).ravel()
        Vf = V[m].astype(np.float32).ravel()
        zm = zm[m].astype(np.float32).ravel()
        x = (Uf - float(cx)) * zm / float(fx)
        y = (Vf - float(cy)) * zm / float(fy)
        z = zm
        pts_arr = np.column_stack((x, y, z))
        n = int(pts_arr.shape[0])
        if n > max_pts:
            step = int(np.ceil(float(n) / float(max_pts)))
            pts_arr = pts_arr[::step]
        pts_arr = np.ascontiguousarray(pts_arr, dtype=np.float32)
        pts = pts_arr.tolist()
        fid = depth_msg.header.frame_id or "camera_depth_optical_frame"
        header = rospy.Header(stamp=depth_msg.header.stamp, frame_id=fid)
        fields = [
            PointField("x", 0, PointField.FLOAT32, 1),
            PointField("y", 4, PointField.FLOAT32, 1),
            PointField("z", 8, PointField.FLOAT32, 1),
        ]
        return pc2.create_cloud(header, fields, pts)

    def _maybe_publish_depth_cloud(self, depth_msg, cv_image):
        if not self._depth_cloud_enabled:
            return
        now = time.time()
        if now - self._last_depth_cloud_wall < self._depth_cloud_min_interval:
            return
        self._last_depth_cloud_wall = now
        try:
            cloud = self._build_depth_point_cloud(depth_msg, cv_image)
            if cloud is not None:
                self._depth_cloud_pub.publish(cloud)
        except Exception as ex:
            rospy.logdebug_throttle(5.0, "depth cloud: %s" % ex)

    def _maybe_update_depth_proximity(self, cv_image):
        """中心视场深度统计：仿真里行人常不在 GT_obstacle_bbox，用深度补一层粗预警。"""
        now = time.time()
        if now - self._last_depth_proximity_wall < 0.22:
            return
        self._last_depth_proximity_wall = now
        try:
            st = self._compute_depth_roi_proximity(cv_image)
            if not st:
                self.data["depth_proximity"]["ok"] = False
                return
            self.data["depth_proximity"].update(st)
            self.data["depth_proximity"]["ok"] = True
            self.data["depth_proximity"]["timestamp"] = now
        except Exception:
            self.data["depth_proximity"]["ok"] = False

    def _compute_depth_roi_proximity(self, cv_image):
        if cv_image is None or cv_image.size == 0:
            return None
        arr = np.asarray(cv_image)
        if len(arr.shape) == 3:
            arr = arr[:, :, 0]
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h < 8 or w < 8:
            return None
        hf = float(rospy.get_param("/myviz/depth_warn_roi_h_frac", 0.42))
        wf = float(rospy.get_param("/myviz/depth_warn_roi_w_frac", 0.52))
        hf = max(0.12, min(0.9, hf))
        wf = max(0.12, min(0.95, wf))
        cy, cx = h // 2, w // 2
        rh = max(4, int(h * hf * 0.5))
        rw = max(4, int(w * wf * 0.5))
        roi = arr[max(0, cy - rh) : min(h, cy + rh), max(0, cx - rw) : min(w, cx + rw)]
        if roi.size < 80:
            return None
        if np.issubdtype(roi.dtype, np.integer):
            z = roi.astype(np.float64) * 0.001
        else:
            z = roi.astype(np.float64)
        z = z[np.isfinite(z)]
        zmax = float(rospy.get_param("/myviz/depth_warn_max_m", 22.0))
        z = z[(z > 0.18) & (z < zmax)]
        if z.size < 24:
            return None
        d_min = float(np.min(z))
        d_near = float(np.percentile(z, 4.0))
        d_med = float(np.median(z))
        valid_frac = float(z.size) / float(roi.size)
        return {
            "min_m": d_min,
            "near_m": d_near,
            "median_m": d_med,
            "valid_frac": valid_frac,
        }

    def invalidate_drone_mesh_cache(self):
        """Catkin 工作空间解析完成后调用，使下次发布重新解析网格路径。"""
        with self._drone_mesh_lock:
            self._drone_mesh_resolved = False
            self._drone_mesh_uri = ""
            self._drone_mesh_warned = False
        self._last_drone_marker_wall = 0.0

    def _resolve_drone_marker_mesh_uri(self):
        """
        RViz Marker 网格 URI：优先 file:// 绝对路径（不依赖 ROS_PACKAGE_PATH），
        其次 package://；参数 /myviz/drone_marker_mesh、/myviz/drone_mesh_file 可覆盖。

        须在锁内完成解析后再标记 resolved：里程计回调在子线程且 /myviz/drone_marker 为 latch，
        若过早置 resolved=True，另一线程会读到空 URI 并先发布球体，latched 后模型再也无法显示。
        """
        with self._drone_mesh_lock:
            if self._drone_mesh_resolved:
                return self._drone_mesh_uri

            uri = ""
            source = ""

            custom = str(rospy.get_param("/myviz/drone_marker_mesh", "") or "").strip()
            if custom:
                if custom.startswith("package://") or custom.startswith("file://"):
                    uri, source = custom, "参数 drone_marker_mesh"
                else:
                    exp = os.path.expanduser(custom)
                    if os.path.isfile(exp):
                        uri = pathlib.Path(exp).resolve().as_uri()
                        source = "参数 drone_marker_mesh 本地路径"

            if not uri:
                mesh_file = str(rospy.get_param("/myviz/drone_mesh_file", "") or "").strip()
                if mesh_file:
                    exp = os.path.expanduser(mesh_file)
                    if os.path.isfile(exp):
                        uri = pathlib.Path(exp).resolve().as_uri()
                        source = "参数 drone_mesh_file"

            if not uri:
                hint = str(rospy.get_param("/myviz/catkin_workspace", "") or "").strip()
                try:
                    _here = os.path.dirname(os.path.abspath(__file__))
                    if _here not in sys.path:
                        sys.path.insert(0, _here)
                    from utils import find_uav_quadcopter_mesh_dae

                    abs_mesh = find_uav_quadcopter_mesh_dae(hint or None)
                    if abs_mesh and os.path.isfile(abs_mesh):
                        uri = pathlib.Path(abs_mesh).resolve().as_uri()
                        source = "磁盘检索"
                except Exception as ex:
                    rospy.logwarn("中部无人机网格磁盘检索异常（可忽略若无需模型）: %s", ex)

            if not uri:
                try:
                    import rospkg

                    root = rospkg.RosPack().get_path("uav_simulator")
                    for name in ("CERLAB_quadcopter.dae", "quadcopter.dae"):
                        p = os.path.join(root, "urdf", "quadcopter", "meshes", name)
                        if os.path.isfile(p):
                            uri = "package://uav_simulator/urdf/quadcopter/meshes/" + name
                            source = "rospack"
                            break
                except Exception:
                    pass

            self._drone_mesh_uri = uri
            self._drone_mesh_resolved = True
            if uri:
                rospy.loginfo("中部无人机模型: %s（%s）", uri, source)
            elif not self._drone_mesh_warned:
                self._drone_mesh_warned = True
                rospy.logwarn(
                    "未找到四旋翼网格（已试磁盘检索与 rospack）。"
                    "中部仍显示球体；可设置参数 /myviz/drone_mesh_file 为 .dae 绝对路径，"
                    "或确保 ~/catkin_ws/src/uav_simulator 下存在 CERLAB_quadcopter.dae。"
                )
            return self._drone_mesh_uri

    def _publish_drone_marker(self, msg):
        try:
            now = time.time()
            if now - self._last_drone_marker_wall < self._drone_marker_min_interval:
                return
            self._last_drone_marker_wall = now
            m = Marker()
            m.header.frame_id = self._frame_for_odom_visualization(msg)
            m.header.stamp = msg.header.stamp
            m.ns = "myviz"
            m.id = 1
            m.action = Marker.ADD
            m.pose = msg.pose.pose
            mesh_uri = self._resolve_drone_marker_mesh_uri()
            if mesh_uri:
                m.type = Marker.MESH_RESOURCE
                m.mesh_resource = mesh_uri
                m.mesh_use_embedded_materials = bool(
                    rospy.get_param("/myviz/drone_mesh_use_embedded_materials", True)
                )
                sc = float(rospy.get_param("/myviz/drone_marker_mesh_scale", 1.35))
                m.scale.x = m.scale.y = m.scale.z = sc
                m.color.a = 1.0
                m.color.r = m.color.g = m.color.b = 1.0
            else:
                # 无网格时：薄方块比球体更像机体轮廓（易与规划栈体素区分）
                m.type = Marker.CUBE
                s = float(rospy.get_param("/myviz/drone_marker_scale", 0.52))
                m.scale.x = m.scale.y = s
                m.scale.z = max(0.06, float(rospy.get_param("/myviz/drone_marker_thickness", 0.11)))
                m.color.a = 0.95
                m.color.r = 1.0
                m.color.g = 0.55
                m.color.b = 0.08
            m.lifetime = rospy.Duration(0)
            self._drone_marker_pub.publish(m)
        except Exception as ex:
            rospy.logwarn_throttle(5.0, "发布机体 Marker 失败: %s", ex)

    
    def battery_callback(self, msg):
        """电池状态话题回调函数"""
        try:
            pct = float(getattr(msg, "percentage", -1.0))
            if pct < 0.0 or math.isnan(pct):
                return
            self.last_message_time["battery"] = time.time()
            self.topics_active["battery"] = True
            self.data["battery"]["voltage"] = msg.voltage
            self.data["battery"]["current"] = msg.current
            self.data["battery"]["percentage"] = pct
            self.data["battery"]["temperature"] = msg.temperature
            
            # 触发注册的回调函数
            if "battery" in self.callbacks:
                for callback in self.callbacks["battery"]:
                    try:
                        callback(self.data["battery"])
                    except Exception as e:
                        rospy.logerr(f"执行电池回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理电池数据时出错: {str(e)}")
    
    def state_callback(self, msg):
        """无人机状态话题回调函数"""
        try:
            self.last_message_time["status"] = time.time()
            self.topics_active["status"] = True
            self.data["status"]["connected"] = msg.connected
            self.data["status"]["armed"] = msg.armed
            self.data["status"]["guided"] = msg.guided
            self.data["status"]["mode"] = msg.mode
            
            # 触发注册的回调函数
            if "status" in self.callbacks:
                for callback in self.callbacks["status"]:
                    try:
                        callback(self.data["status"])
                    except Exception as e:
                        rospy.logerr(f"执行状态回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理状态数据时出错: {str(e)}")
                
    def odometry_callback(self, msg):
        """无人机位置话题回调函数"""
        try:
            self.last_message_time["odometry"] = time.time()
            self.topics_active["odometry"] = True
            if self._sync_viz_frame_to_odom and not self._announced_odom_frame:
                fid = (msg.header.frame_id or "").strip()
                if fid:
                    rospy.set_param("/myviz/_live_odom_frame", fid)
                    self._announced_odom_frame = True
            # 更新位置信息
            self.data["odometry"]["position"]["x"] = msg.pose.pose.position.x
            self.data["odometry"]["position"]["y"] = msg.pose.pose.position.y
            self.data["odometry"]["position"]["z"] = msg.pose.pose.position.z
            self.data["odometry"]["frame_id"] = (msg.header.frame_id or "").strip()
            
            # 更新方向信息
            self.data["odometry"]["orientation"]["x"] = msg.pose.pose.orientation.x
            self.data["odometry"]["orientation"]["y"] = msg.pose.pose.orientation.y
            self.data["odometry"]["orientation"]["z"] = msg.pose.pose.orientation.z
            self.data["odometry"]["orientation"]["w"] = msg.pose.pose.orientation.w

            self._maybe_attitude_from_odom(msg.pose.pose.orientation)
            self._append_odom_to_flight_path(msg)
            self._publish_drone_marker(msg)

            # 如果速度话题未激活，也可以从里程计消息中提取速度
            if not self.topics_active["velocity"]:
                # 提取线速度
                self.data["velocity"]["linear"]["x"] = msg.twist.twist.linear.x
                self.data["velocity"]["linear"]["y"] = msg.twist.twist.linear.y
                self.data["velocity"]["linear"]["z"] = msg.twist.twist.linear.z
                
                # 提取角速度
                self.data["velocity"]["angular"]["x"] = msg.twist.twist.angular.x
                self.data["velocity"]["angular"]["y"] = msg.twist.twist.angular.y
                self.data["velocity"]["angular"]["z"] = msg.twist.twist.angular.z
                
                # 计算合成速度(cm/s)
                linear_x = self.data["velocity"]["linear"]["x"]
                linear_y = self.data["velocity"]["linear"]["y"]
                linear_z = self.data["velocity"]["linear"]["z"]
                speed = math.sqrt(linear_x**2 + linear_y**2 + linear_z**2) * 100  # 转换为厘米/秒
                self.data["velocity"]["speed"] = speed
                
                # 触发速度回调
                if "velocity" in self.callbacks:
                    for callback in self.callbacks["velocity"]:
                        try:
                            callback(self.data["velocity"])
                        except Exception as e:
                            rospy.logerr(f"执行速度回调函数时出错: {str(e)}")
            
            # 触发注册的回调函数
            if "odometry" in self.callbacks:
                for callback in self.callbacks["odometry"]:
                    try:
                        callback(self.data["odometry"])
                    except Exception as e:
                        rospy.logerr(f"执行位置回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理位置数据时出错: {str(e)}")

    def _maybe_attitude_from_odom(self, orient):
        """IMU 无数据或超过阈值未更新时，用里程计 pose 四元数推导姿态（真值，非 UI 造假）。"""
        try:
            gap = float(rospy.get_param("/myviz/attitude_odom_after_imu_gap_sec", 0.35))
            if (time.time() - self._last_imu_attitude_wall) < gap:
                return
            import tf

            q = [orient.x, orient.y, orient.z, orient.w]
            euler = tf.transformations.euler_from_quaternion(q)
            self.data["attitude"]["roll"] = math.degrees(euler[0])
            self.data["attitude"]["pitch"] = math.degrees(euler[1])
            self.data["attitude"]["yaw"] = math.degrees(euler[2])
            self.data["attitude"]["timestamp"] = rospy.Time.now().to_sec()
            self.last_message_time["attitude"] = time.time()
            self.topics_active["attitude"] = True
            if "attitude" in self.callbacks:
                for callback in self.callbacks["attitude"]:
                    try:
                        callback(dict(self.data["attitude"]))
                    except Exception as e:
                        rospy.logerr(f"执行姿态回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logdebug_throttle(10.0, "attitude from odom: %s", e)

    def _frame_for_odom_visualization(self, msg):
        """Path/Marker 与里程计使用同一坐标系，避免 RViz Fixed Frame 与消息 frame 不一致时机体消失。"""
        if self._sync_viz_frame_to_odom:
            fid = (msg.header.frame_id or "").strip()
            if fid:
                return fid
        return (rospy.get_param("/myviz/flight_path_frame", self._flight_path_frame) or "map").strip()

    def _append_odom_to_flight_path(self, msg):
        """累积里程计位姿并发布 nav_msgs/Path，供嵌入 RViz 显示轨迹。"""
        try:
            if self._last_odom_stamp is not None:
                dt = (msg.header.stamp - self._last_odom_stamp).to_sec()
                if dt < 0.0 or dt > 2.0:
                    self._path_trail.clear()
                    self._last_trail_pos = None
            self._last_odom_stamp = msg.header.stamp

            p = msg.pose.pose.position
            tw = msg.twist.twist.linear
            speed = math.sqrt(tw.x ** 2 + tw.y ** 2 + tw.z ** 2)
            min_step = (
                self._flight_path_min_step_slow_m
                if speed < self._flight_path_slow_speed_mps
                else self._flight_path_min_step_m
            )
            if self._last_trail_pos is not None:
                lx, ly, lz = self._last_trail_pos
                d_xy = math.hypot(p.x - lx, p.y - ly)
                d_z = abs(p.z - lz)
                # 悬停时里程计在 XY 上小幅抖动会连成“乱线”，用水平阈值 + 低速更大步长抑制
                if d_xy < min_step and d_z < self._flight_path_z_step_m:
                    return
            self._last_trail_pos = (p.x, p.y, p.z)

            vfid = self._frame_for_odom_visualization(msg)
            ps = PoseStamped()
            ps.header.stamp = msg.header.stamp
            ps.header.frame_id = vfid
            ps.pose = msg.pose.pose
            self._path_trail.append(ps)

            now = time.time()
            if now - self._last_path_publish_wall < 0.28:
                return
            self._last_path_publish_wall = now

            path = Path()
            path.header.stamp = msg.header.stamp
            path.header.frame_id = vfid
            path.poses = list(self._path_trail)
            self._flight_path_pub.publish(path)
        except Exception as ex:
            rospy.logdebug_throttle(5.0, "flight path: %s" % ex)

    def clear_flight_path(self):
        """清空 RViz 橙色轨迹（开始航点时调用，避免起点徘徊段残留在录屏里）。"""
        try:
            self._path_trail.clear()
            self._last_trail_pos = None
            self._last_odom_stamp = None
            vfid = (
                rospy.get_param("/myviz/flight_path_frame", self._flight_path_frame) or "map"
            ).strip()
            path = Path()
            path.header.stamp = rospy.Time.now()
            path.header.frame_id = vfid
            path.poses = []
            self._flight_path_pub.publish(path)
        except Exception:
            pass

    def velocity_callback(self, msg):
        """无人机速度话题回调函数"""
        try:
            self.last_message_time["velocity"] = time.time()
            self.topics_active["velocity"] = True
            # 更新线速度
            self.data["velocity"]["linear"]["x"] = msg.twist.linear.x
            self.data["velocity"]["linear"]["y"] = msg.twist.linear.y
            self.data["velocity"]["linear"]["z"] = msg.twist.linear.z
            
            # 更新角速度
            self.data["velocity"]["angular"]["x"] = msg.twist.angular.x
            self.data["velocity"]["angular"]["y"] = msg.twist.angular.y
            self.data["velocity"]["angular"]["z"] = msg.twist.angular.z
            
            # 计算合成速度(cm/s)
            linear_x = self.data["velocity"]["linear"]["x"]
            linear_y = self.data["velocity"]["linear"]["y"]
            linear_z = self.data["velocity"]["linear"]["z"]
            speed = math.sqrt(linear_x**2 + linear_y**2 + linear_z**2) * 100  # 转换为厘米/秒
            self.data["velocity"]["speed"] = speed
            
            # 触发注册的回调函数
            if "velocity" in self.callbacks:
                for callback in self.callbacks["velocity"]:
                    try:
                        callback(self.data["velocity"])
                    except Exception as e:
                        rospy.logerr(f"执行速度回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理速度数据时出错: {str(e)}")
    
    def camera_callback(self, msg):
        """摄像头图像话题回调函数"""
        try:
            self.last_message_time["camera"] = time.time()
            self.topics_active["camera"] = True
            # 将ROS图像消息转换为OpenCV格式
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            
            # 更新图像数据
            self.data["camera"]["image"] = cv_image
            self.data["camera"]["width"] = msg.width
            self.data["camera"]["height"] = msg.height
            self.data["camera"]["encoding"] = msg.encoding
            
            # 触发注册的回调函数
            if "camera" in self.callbacks:
                for callback in self.callbacks["camera"]:
                    try:
                        callback(self.data["camera"])
                    except Exception as e:
                        rospy.logerr(f"执行图像回调函数时出错: {str(e)}")
        except CvBridgeError as e:
            rospy.logerr(f"转换图像数据时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理图像数据时出错: {str(e)}")
    
    def depth_callback(self, msg):
        """深度图像话题回调函数"""
        try:
            self.last_message_time["depth"] = time.time()
            self.topics_active["depth"] = True
            # 将ROS图像消息转换为OpenCV图像
            cv_image = self.bridge.imgmsg_to_cv2(msg)
            
            # 存储图像和相关信息
            self.data["depth"]["image"] = cv_image
            self.data["depth"]["width"] = msg.width
            self.data["depth"]["height"] = msg.height
            self.data["depth"]["encoding"] = msg.encoding

            self._maybe_publish_depth_cloud(msg, cv_image)
            self._maybe_update_depth_proximity(cv_image)

            # 触发注册的回调函数
            if "depth" in self.callbacks:
                for callback in self.callbacks["depth"]:
                    callback(self.data["depth"])
                    
        except CvBridgeError as e:
            rospy.logerr(f"转换深度图像失败: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理深度图像时出错: {str(e)}")
            
    def bird_view_callback(self, msg):
        """鸟瞰图话题回调函数"""
        try:            
            self.last_message_time["bird_view"] = time.time()
            self.topics_active["bird_view"] = True
            # 将ROS图像消息转换为OpenCV图像
            cv_image = self.bridge.imgmsg_to_cv2(msg)
            
            # 检查图像是否有效
            if cv_image is None or cv_image.size == 0:
                return
            
            # 存储图像和相关信息
            self.data["bird_view"]["image"] = cv_image
            self.data["bird_view"]["width"] = msg.width
            self.data["bird_view"]["height"] = msg.height
            self.data["bird_view"]["encoding"] = msg.encoding
            
            # 触发注册的回调函数
            if "bird_view" in self.callbacks:
                for callback in self.callbacks["bird_view"]:
                    callback(self.data["bird_view"])
                    
        except CvBridgeError as e:
            print(f"转换鸟瞰图失败: {str(e)}")
        except Exception as e:
            print(f"处理鸟瞰图话题时出错: {str(e)}")
    
    def attitude_callback(self, msg):
        """处理姿态数据，从IMU四元数转换为欧拉角"""
        try:
            self._last_imu_attitude_wall = time.time()
            self.last_message_time["attitude"] = time.time()
            self.topics_active["attitude"] = True
            # 从四元数转换为欧拉角
            orientation = msg.orientation
            quaternion = [orientation.x, orientation.y, orientation.z, orientation.w]
            
            # 使用tf转换库计算欧拉角
            import tf
            euler = tf.transformations.euler_from_quaternion(quaternion)
            
            # 欧拉角是按照roll, pitch, yaw的顺序
            roll = math.degrees(euler[0])
            pitch = math.degrees(euler[1])
            yaw = math.degrees(euler[2])
            
            # 更新姿态数据
            self.data["attitude"]["roll"] = roll
            self.data["attitude"]["pitch"] = pitch
            self.data["attitude"]["yaw"] = yaw
            self.data["attitude"]["timestamp"] = rospy.Time.now().to_sec()
            
            # 调用注册的回调函数
            if "attitude" in self.callbacks:
                # 检查callbacks是否是列表类型
                if isinstance(self.callbacks["attitude"], list):
                    for callback in self.callbacks["attitude"]:
                        try:
                            callback(self.data["attitude"])
                        except Exception as e:
                            rospy.logerr(f"执行姿态回调函数时出错: {str(e)}")
                else:
                    # 向后兼容，如果不是列表则直接调用
                    try:
                        self.callbacks["attitude"](self.data["attitude"])
                    except Exception as e:
                        rospy.logerr(f"执行姿态回调函数时出错: {str(e)}")
                
        except Exception as e:
            rospy.logerr(f"处理姿态数据时出错: {str(e)}")
    
    def register_callback(self, topic_name, callback):
        """注册回调函数，当话题数据更新时触发"""
        if topic_name not in self.callbacks:
            self.callbacks[topic_name] = []
        self.callbacks[topic_name].append(callback)
    
    def get_data(self, topic_name):
        """获取指定话题的最新数据"""
        if topic_name in self.data:
            return self.data[topic_name]
        return None
        
    def get_latest_data(self, topic_name):
        """获取指定话题的最新数据，与get_data相同，为了API统一性"""
        return self.get_data(topic_name)
    
    def is_topic_active(self, topic_name):
        """检查指定话题是否活跃"""
        if topic_name in self.topics_active:
            return self.topics_active[topic_name]
        return False

    def has_fresh_data(self, topic_name, max_age_sec=2.0):
        """
        话题是否“最近仍在更新”。
        仅靠 is_topic_active 无法区分“曾经连上但当前无数据”。
        """
        try:
            ts = float(self.last_message_time.get(topic_name, 0.0))
            return ts > 0.0 and (time.time() - ts) <= float(max_age_sec)
        except Exception:
            return False
    
    def shutdown(self):
        """关闭订阅者线程"""
        self.running = False
        if self.subscriber_thread.is_alive():
            self.subscriber_thread.join(1.0)
        
        # 取消所有订阅
        for topic_name, subscriber in self.subscribers.items():
            if subscriber:
                subscriber.unregister()
                
    def rc_input_callback(self, msg):
        """处理RC遥控器输入数据"""
        try:
            self.last_message_time["rc_input"] = time.time()
            # 更新RC数据
            self.data["rc_input"]["channels"] = list(msg.channels)
            self.data["rc_input"]["rssi"] = msg.rssi
            
            # 设置话题活跃状态
            self.topics_active["rc_input"] = True
            
            # 触发注册的回调函数
            if "rc_input" in self.callbacks:
                for callback in self.callbacks["rc_input"]:
                    try:
                        callback(self.data["rc_input"])
                    except Exception as e:
                        rospy.logerr(f"执行RC输入回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理RC输入数据时出错: {str(e)}")
    
    def fsm_state_callback(self, msg):
        """处理FSM状态数据"""
        try:
            self.last_message_time["fsm_state"] = time.time()
            # FSM状态码名称映射
            FSM_STATE_NAMES = {
                0: "INIT",
                1: "WAIT_TARGET",
                2: "GEN_NEW_TRAJ",
                3: "REPLAN_TRAJ",
                4: "EXEC_TRAJ",
                5: "EMERGENCY_STOP",
                6: "SEQUENTIAL_START"
            }
            
            state_code = msg.data
            state_name = FSM_STATE_NAMES.get(state_code, f"UNKNOWN({state_code})")
            
            # 更新FSM状态数据
            self.data["fsm_state"]["state"] = state_code
            self.data["fsm_state"]["state_name"] = state_name
            self.data["fsm_state"]["timestamp"] = rospy.Time.now().to_sec()
            
            # 设置话题活跃状态
            self.topics_active["fsm_state"] = True
            
            # 触发注册的回调函数
            if "fsm_state" in self.callbacks:
                for callback in self.callbacks["fsm_state"]:
                    try:
                        callback(self.data["fsm_state"])
                    except Exception as e:
                        rospy.logerr(f"执行FSM状态回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理FSM状态数据时出错: {str(e)}")
    
    def obstacle_states_callback(self, msg):
        """处理障碍物状态数据"""
        try:
            obstacles = []
            for idx, state in enumerate(msg.states):
                obstacle = {
                    "id": idx + 1,
                    "position": {
                        "x": state.position.x,
                        "y": state.position.y,
                        "z": state.position.z
                    },
                    "velocity": {
                        "x": state.velocity.x,
                        "y": state.velocity.y,
                        "z": state.velocity.z
                    },
                    "acceleration": {
                        "x": state.acceleration.x,
                        "y": state.acceleration.y,
                        "z": state.acceleration.z
                    },
                    "size": {
                        "x": state.size.x,
                        "y": state.size.y,
                        "z": state.size.z
                    },
                    # 计算速度和加速度的模
                    "speed": math.sqrt(state.velocity.x**2 + state.velocity.y**2 + state.velocity.z**2),
                    "accel": math.sqrt(state.acceleration.x**2 + state.acceleration.y**2 + state.acceleration.z**2)
                }
                obstacles.append(obstacle)
            
            # 更新障碍物状态数据
            self.data["obstacle_states"]["obstacles"] = obstacles
            self.data["obstacle_states"]["count"] = len(obstacles)
            self.data["obstacle_states"]["timestamp"] = rospy.Time.now().to_sec()
            self.last_message_time["obstacle_states"] = time.time()
            self.topics_active["obstacle_states"] = True
            
            # 触发注册的回调函数
            if "obstacle_states" in self.callbacks:
                for callback in self.callbacks["obstacle_states"]:
                    try:
                        callback(self.data["obstacle_states"])
                    except Exception as e:
                        rospy.logerr(f"执行障碍物状态回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理障碍物状态数据时出错: {str(e)}")

    def obstacle_markers_callback(self, msg):
        """处理MarkerArray障碍物数据（仿真工程兼容）"""
        try:
            by_id = {}
            for marker in msg.markers:
                if marker.action in (Marker.DELETE, Marker.DELETEALL):
                    continue
                mid = int(marker.id)
                by_id[mid] = marker
            obstacles = []
            for mid in sorted(by_id.keys()):
                marker = by_id[mid]
                obstacle = {
                    "id": mid,
                    "position": {
                        "x": marker.pose.position.x,
                        "y": marker.pose.position.y,
                        "z": marker.pose.position.z,
                    },
                    "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "size": {
                        "x": marker.scale.x if marker.scale.x > 0 else 0.2,
                        "y": marker.scale.y if marker.scale.y > 0 else 0.2,
                        "z": marker.scale.z if marker.scale.z > 0 else 0.2,
                    },
                    "speed": 0.0,
                    "accel": 0.0,
                }
                obstacles.append(obstacle)

            self.data["obstacle_states"]["obstacles"] = obstacles
            self.data["obstacle_states"]["count"] = len(obstacles)
            self.data["obstacle_states"]["timestamp"] = rospy.Time.now().to_sec()
            self.last_message_time["obstacle_states"] = time.time()
            self.topics_active["obstacle_states"] = True

            if "obstacle_states" in self.callbacks:
                for callback in self.callbacks["obstacle_states"]:
                    try:
                        callback(self.data["obstacle_states"])
                    except Exception as e:
                        rospy.logerr(f"执行障碍物状态回调函数时出错: {str(e)}")
        except Exception as e:
            rospy.logerr(f"处理MarkerArray障碍物数据时出错: {str(e)}")