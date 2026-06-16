import rospy
import numpy as np
import torch
from map_manager.srv import RayCast
from nav_msgs.msg import Odometry, Path
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point, PoseStamped, TwistStamped, Quaternion, Vector3
from mavros_msgs.msg import PositionTarget, State
from mavros_msgs.srv import CommandBool, CommandBoolRequest, SetMode, SetModeRequest
from navigation_runner.srv import GetSafeAction, GetSafeActionMap
from onboard_detector.srv import GetDynamicObstacles
from map_manager.srv import GetStaticObstacles
from ppo import PPO
from torchrl.data import CompositeSpec, UnboundedContinuousTensorSpec
from tensordict.tensordict import TensorDict
from torchrl.envs.utils import ExplorationType, set_exploration_type
from navigation_runner.srv import GetPolicyInference
from utils import vec_to_new_frame
import math
from std_srvs.srv import Empty
import tf.transformations
import time
import threading
import os
import sys

class Navigation:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lidar_hbeams = int(360/self.cfg.sensor.lidar_hres)
        self.raypoints = []
        _dn = self.cfg.algo.feature_extractor.dyn_obs_num
        _z = torch.zeros(_dn, 3, dtype=torch.float, device=self.cfg.device)
        self.dynamic_obstacles = (_z.clone(), _z.clone(), _z.clone())
        self.robot_size = 0.3 # radius
        self.raycast_vres = ((self.cfg.sensor.lidar_vfov[1] - self.cfg.sensor.lidar_vfov[0]))/(self.cfg.sensor.lidar_vbeams - 1) * np.pi/180.0
        self.raycast_hres = self.cfg.sensor.lidar_hres * np.pi/180.0

        self.goal = None
        self.goal_received = False
        self.target_received = False
        self.target_stamp = None
        self.target_dir = None
        self.stable_times = 0
        self.has_action = False
        self.laser_points_msg = None

        # 须在首个 odom 回调前初始化（订阅注册后可能立刻收到里程计）
        self.path_history = Path()
        self.path_history.header.frame_id = "map"
        self.last_path_stamp = rospy.Time.now()
        self.path_publish_interval = 0.1
        self.max_path_points = 2000

        # Optional tracking mode. Default keeps previous behavior.
        self.nav_mode = rospy.get_param("/rl/nav_mode", "goal_follow")
        self.target_timeout = float(rospy.get_param("/rl/target_timeout", 0.8))

        self.height_control = False 
        self.px4_control = rospy.get_param('rl/use_px4', True)

        self.use_policy_server = False

        self.odom_received = False
        if (self.px4_control):
            self.odom_sub = rospy.Subscriber("/mavros/local_position/odom", Odometry, self.odom_callback)
            self.state_sub = rospy.Subscriber("/mavros/state", State, self.state_callback)
            self.action_pub = rospy.Publisher("/mavros/setpoint_raw/local", PositionTarget, queue_size=10)
            self.pose_pub = rospy.Publisher("/mavros/setpoint_position/local", PoseStamped, queue_size=10)
            self.set_mode_client = rospy.ServiceProxy("mavros/set_mode", SetMode)
            self.arming_client = rospy.ServiceProxy("mavros/cmd/arming", CommandBool)

            self.mavros_state = None
            self.offb_set_mode = SetModeRequest()
            self.offb_set_mode.custom_mode = 'OFFBOARD'
            self.arm_cmd = CommandBoolRequest()
            self.arm_cmd.value = True
        else:
            self.odom_sub = rospy.Subscriber("/CERLAB/quadcopter/odom", Odometry, self.odom_callback)
            self.action_pub = rospy.Publisher("/CERLAB/quadcopter/cmd_vel", TwistStamped, queue_size=10)
            self.pose_pub = rospy.Publisher("/CERLAB/quadcopter/setpoint_pose", PoseStamped, queue_size=10)

        self.goal_sub = rospy.Subscriber("/move_base_simple/goal", PoseStamped, self.goal_callback)
        self.target_sub = rospy.Subscriber("/tracking/target_pose", PoseStamped, self.target_pose_callback)
        self.raycast_vis_pub = rospy.Publisher("/rl_navigation/raycast", MarkerArray, queue_size=10)
        self.cmd_vis_pub = rospy.Publisher("/rl_navigation/cmd", MarkerArray, queue_size=10)
        self.goal_vis_pub = rospy.Publisher("rl_navigation/goal", MarkerArray, queue_size=10)
        self.rollout_traj_pub = rospy.Publisher("/rollout_traj", Path, queue_size=10)
        self.dynamic_obstacle_vis_pub = rospy.Publisher("/rl_navigation/in_range_dynamic_obstacles", MarkerArray, queue_size=10)
        self.intent_path_pub = rospy.Publisher("/rl_navigation/intent_path", Path, queue_size=10)
        self.actual_path_pub = rospy.Publisher("/rl_navigation/actual_path", Path, queue_size=10)
        self.inflated_obstacle_vis_pub = rospy.Publisher("/rl_navigation/inflated_obstacles", MarkerArray, queue_size=10)

        self.vis_horizon = 1.5
        self.vis_dt = 0.1
        self.safety_inflation = rospy.get_param("/safe_action/safety_distance", 0.3)
        # Motion profile (tunable): improve sluggish stop-go behavior near goal
        self.max_nav_speed = float(rospy.get_param("/rl/max_nav_speed", 1.8))
        self.near_goal_speed = float(rospy.get_param("/rl/near_goal_speed", 1.2))
        self.slowdown_radius = float(rospy.get_param("/rl/slowdown_radius", 1.8))
        self.goal_reach_radius = float(rospy.get_param("/rl/goal_reach_radius", 0.25))
        self.heading_align_thresh = float(rospy.get_param("/rl/heading_align_thresh", 0.2))
        self.heading_align_stable_cycles = int(rospy.get_param("/rl/heading_align_stable_cycles", 3))

        if (not self.use_policy_server):
            self.policy = self.init_model()
            self.policy.eval()


        # Safety input thread needs interactive stdin. For nohup/background launch,
        # disable it to avoid EOFError from input().
        self.safety_stop = False
        enable_safety_input = os.environ.get("NAVRL_DISABLE_SAFETY_INPUT", "0") != "1" and sys.stdin.isatty()
        if enable_safety_input:
            safety_thread = threading.Thread(target=self.safety_check)
            safety_thread.daemon = True
            safety_thread.start()

        self.takeoff()

        # Gazebo 仿真行人 → 注入动态障碍张量（预测/避障用）
        # 旧逻辑仅匹配名称含 demo_person；常见 actor/male/female 等模型不会被注入，
        # 导致 UI 上 GT 框可见但策略侧 dyn_obs 全零、「看见人却不躲」。
        self._gz_ped_track = {}
        self._gz_ped_lock = threading.Lock()
        if rospy.get_param("/rl/ingest_gazebo_pedestrians", True) and (not self.px4_control):
            try:
                from gazebo_msgs.msg import ModelStates

                self._gz_ped_include = [
                    s.lower()
                    for s in rospy.get_param(
                        "/rl/gazebo_pedestrian_name_substrings",
                        [
                            "demo_person",
                            "person",
                            "human",
                            "actor",
                            "walker",
                            "ped",
                            "walking",
                            "male",
                            "female",
                            "casual",
                        ],
                    )
                ]
                self._gz_ped_exclude = [
                    s.lower()
                    for s in rospy.get_param(
                        "/rl/gazebo_pedestrian_name_exclude_substrings",
                        [
                            "quadcopter",
                            "cerlab",
                            "iris",
                            "uav",
                            "drone_",
                            "ground",
                            "plane",
                            "sky",
                            "camera",
                            "pillar",
                            "column",
                            "obstacle",
                            "wall",
                        ],
                    )
                ]
                rospy.Subscriber(
                    "/gazebo/model_states",
                    ModelStates,
                    self._gazebo_ped_states_cb,
                    queue_size=1,
                    buff_size=2**22,
                )
                rospy.loginfo(
                    "[nav-ros] 已订阅 /gazebo/model_states：行人 include 规则 %d 条、exclude %d 条",
                    len(self._gz_ped_include),
                    len(self._gz_ped_exclude),
                )
            except Exception as ex:
                rospy.logwarn_throttle(15.0, "[nav-ros] 无法订阅 Gazebo 行人状态: %s" % ex)
  
    def init_model(self):
        observation_dim = 8
        num_dim_each_dyn_obs_state = 10
        observation_spec = CompositeSpec({
            "agents": CompositeSpec({
                "observation": CompositeSpec({
                    "state": UnboundedContinuousTensorSpec((observation_dim,), device=self.cfg.device), 
                    "lidar": UnboundedContinuousTensorSpec((1, self.lidar_hbeams, self.cfg.sensor.lidar_vbeams), device=self.cfg.device),
                    "direction": UnboundedContinuousTensorSpec((1, 3), device=self.cfg.device),
                    "dynamic_obstacle": UnboundedContinuousTensorSpec((1, self.cfg.algo.feature_extractor.dyn_obs_num, num_dim_each_dyn_obs_state), device=self.cfg.device),
                }),
            }).expand(1)
        }, shape=[1], device=self.cfg.device)

        action_dim = 3
        action_spec = CompositeSpec({
            "agents": CompositeSpec({
                "action": UnboundedContinuousTensorSpec((action_dim,), device=self.cfg.device), 
            })
        }).expand(1, action_dim).to(self.cfg.device)

        policy = PPO(self.cfg.algo, observation_spec, action_spec, self.cfg.device)

        # Checkpoint search order:
        # 1) NAVRL_CHECKPOINT env var (explicit)
        # 2) navigation_runner/scripts/ckpts/navrl_checkpoint.pt (default)
        # 3) repo root: NavRL/navrl_checkpoint.pt (common in this repo)
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        ckpts_dir = os.path.join(scripts_dir, "ckpts")
        default_ckpt = os.path.join(ckpts_dir, "navrl_checkpoint.pt")
        repo_root_ckpt = os.path.abspath(os.path.join(scripts_dir, "..", "..", "..", "navrl_checkpoint.pt"))
        ckpt_candidates = [
            os.environ.get("NAVRL_CHECKPOINT", "").strip(),
            default_ckpt,
            repo_root_ckpt,
        ]
        ckpt_path = next((p for p in ckpt_candidates if p and os.path.isfile(p)), None)
        if ckpt_path is None:
            raise FileNotFoundError(
                "NavRL checkpoint not found. Tried:\n"
                + "\n".join([f"  - {p or '<empty>'}" for p in ckpt_candidates])
            )

        policy.load_state_dict(torch.load(ckpt_path, map_location=self.cfg.device))
        return policy

    def takeoff(self):
        takeoff_height = 1.0
        r = rospy.Rate(10)
        while (not rospy.is_shutdown() and self.odom_received == False):
            print("[nav-ros]: Wait for robot odom...")
            r.sleep()

        takeoff_pose = PoseStamped()
        takeoff_pose.pose.position.x = self.odom.pose.pose.position.x
        takeoff_pose.pose.position.y = self.odom.pose.pose.position.y
        takeoff_pose.pose.position.z = takeoff_height
        takeoff_pose.pose.orientation = self.odom.pose.pose.orientation
        self.takeoff_pose = takeoff_pose
        if (self.px4_control):
            pose = PoseStamped()

            pose.pose.position.x = 0
            pose.pose.position.y = 0
            pose.pose.position.z = 2
            rate = rospy.Rate(20)
            # Send a few setpoints before starting
            for i in range(100):
                if(rospy.is_shutdown()):
                    break
                self.pose_pub.publish(pose)
                rate.sleep()
            last_req = rospy.Time.now()
        # 一键启动时 Gazebo 可能仍处于 pause：机体无法物理爬升，里程计也可能与网格不同步，
        # 死等 z→takeoff_height 会长时间阻塞或产生「假到位」；CERLAB 仿真侧加超时，交给 unpause 后再爬升。
        _takeoff_t0 = time.time()
        _takeoff_wall = float(rospy.get_param("/rl/takeoff_height_converge_timeout_sec", 22.0))
        while (not rospy.is_shutdown() and not (np.abs(self.odom.pose.pose.position.z - takeoff_height) <= 0.2)):
            if (not self.px4_control) and (time.time() - _takeoff_t0 > _takeoff_wall):
                rospy.logwarn(
                    "[nav-ros] CERLAB takeoff 在 %.0fs 内未到目标高度（常见于 Gazebo 仍暂停或近地spawn）；"
                    "继续初始化，依赖 unpause 后控制爬升",
                    _takeoff_wall,
                )
                break
            if (self.px4_control):
                if (self.mavros_state.mode != "OFFBOARD" and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
                    if(self.set_mode_client.call(self.offb_set_mode).mode_sent == True):
                        print("[nav-ros]: OFFBOARD enabled.")

                    last_req = rospy.Time.now()
                else:
                    if(not self.mavros_state.armed and (rospy.Time.now() - last_req) > rospy.Duration(5.0)):
                        if(self.arming_client.call(self.arm_cmd).success == True):
                            print("[nav-ros]: Vehicle armed.")

                        last_req = rospy.Time.now()
            self.pose_pub.publish(takeoff_pose)
            r.sleep()
        print("[nav-ros]: take off completed at height: ", takeoff_height)


    def safety_check(self):
        while not rospy.is_shutdown():
            if (self.safety_stop == False):
                input("[nav-ros]: Press Enter to STOP motion!\n")
                self.safety_stop = True
                self.stop_pose = PoseStamped()
                while not rospy.is_shutdown() and not self.odom_received:
                    rospy.sleep(0.05)
                if rospy.is_shutdown():
                    return
                self.stop_pose.pose = self.odom.pose.pose
            else:
                input("[nav-ros]: Press Enter to CONTINUE motion!\n")
                self.safety_stop = False

    def get_raycast(self, pos: np.array , start_angle: float):
        raypoints = []
        try:
            raycast = rospy.ServiceProxy("occupancy_map/raycast", RayCast)
            pos_msg = Point()
            pos_msg.x = pos[0]
            pos_msg.y = pos[1]
            pos_msg.z = pos[2]
            response = raycast(pos_msg,
                               start_angle,
                               self.cfg.sensor.lidar_range, 
                               self.cfg.sensor.lidar_vfov[0], 
                               self.cfg.sensor.lidar_vfov[1], 
                               self.cfg.sensor.lidar_vbeams, 
                               self.cfg.sensor.lidar_hres
                               )
            num_points = int(len(response.points)/3)
            self.laser_points_msg = response.points
            for i in range(num_points):
                p = [response.points[3*i+0], response.points[3*i+1], response.points[3*i+2]]
                raypoints.append(p)
        except rospy.service.ServiceException as e:
            print("[nav-ros]: raycast func err!")        
        return raypoints

    def get_dynamic_obstacles(self, pos: np.array):
        dynamic_obstacle_pos = torch.zeros(self.cfg.algo.feature_extractor.dyn_obs_num, 3, dtype=torch.float, device=self.cfg.device)
        dynamic_obstacle_vel = torch.zeros(self.cfg.algo.feature_extractor.dyn_obs_num, 3, dtype=torch.float, device=self.cfg.device)
        dynamic_obstacle_size = torch.zeros(self.cfg.algo.feature_extractor.dyn_obs_num, 3, dtype=torch.float, device=self.cfg.device)
        try:
            distance_range = 4.0
            pos_msg = Point()
            pos_msg.x = pos[0]
            pos_msg.y = pos[1]
            pos_msg.z = pos[2]
            get_obstacle = rospy.ServiceProxy("onboard_detector/get_dynamic_obstacles", GetDynamicObstacles)
            response = get_obstacle(pos_msg, distance_range)
            total_obs_num = len(response.position)
            for i in range(self.cfg.algo.feature_extractor.dyn_obs_num):
                if (i < total_obs_num):
                    pos_vec = response.position[i]
                    vel_vec = response.velocity[i]
                    size_vec = response.size[i]
                    dynamic_obstacle_pos[i] = torch.tensor([pos_vec.x, pos_vec.y, pos_vec.z], dtype=torch.float, device=self.cfg.device)
                    dynamic_obstacle_vel[i] = torch.tensor([vel_vec.x, vel_vec.y, vel_vec.z], dtype=torch.float, device=self.cfg.device)
                    dynamic_obstacle_size[i] = torch.tensor([size_vec.x, size_vec.y, size_vec.z], dtype=torch.float, device=self.cfg.device)
        except rospy.service.ServiceException as e:
            print("[nav-ros]: dynamic obstacle func err!")   
        return dynamic_obstacle_pos, dynamic_obstacle_vel, dynamic_obstacle_size

    def get_static_obstacles(self):
        static_obstacle_pos = []
        static_obstacle_size = []
        static_obstacle_angle = []
        try:
            get_static_obstacles_server = rospy.ServiceProxy("occupancy_map/get_static_obstacles", GetStaticObstacles)
            static_obstacle_response = get_static_obstacles_server()
            static_obstacle_pos = static_obstacle_response.position
            static_obstacle_size = static_obstacle_response.size
            static_obstacle_angle = static_obstacle_response.angle
        except rospy.service.ServiceException as e:
            print("[nav-ros]: static obstacle func err!")
        return static_obstacle_pos, static_obstacle_size, static_obstacle_angle
           
    def raycast_callback(self, event):
        if not self.odom_received or not self.goal_received:
            return
        pos = np.array([self.odom.pose.pose.position.x, self.odom.pose.pose.position.y, self.odom.pose.pose.position.z])
        start_angle = np.arctan2(self.target_dir[1].cpu().numpy(), self.target_dir[0].cpu().numpy())
        self.raypoints = self.get_raycast(pos, start_angle)

    def _gz_ped_name_matches(self, name):
        n = (name or "").lower()
        for x in getattr(self, "_gz_ped_exclude", ()):
            if x in n:
                return False
        return any(s in n for s in getattr(self, "_gz_ped_include", ("demo_person",)))

    def _gazebo_ped_states_cb(self, msg):
        try:
            now = rospy.Time.now().to_sec()
            with self._gz_ped_lock:
                for i, name in enumerate(msg.name):
                    if not self._gz_ped_name_matches(name):
                        continue
                    try:
                        p = msg.pose[i].position
                        pos = (float(p.x), float(p.y), float(p.z))
                    except Exception:
                        continue
                    prev = self._gz_ped_track.get(
                        name, {"pos": pos, "t": now, "vel": (0.0, 0.0, 0.0)}
                    )
                    dt = max(1e-3, now - prev["t"])
                    px, py, pz = prev["pos"]
                    vx = (pos[0] - px) / dt
                    vy = (pos[1] - py) / dt
                    vz = (pos[2] - pz) / dt
                    self._gz_ped_track[name] = {"pos": pos, "t": now, "vel": (vx, vy, vz)}
        except Exception:
            pass

    def _inject_gazebo_pedestrians(self, drone_pos, dyn_pos, dyn_vel, dyn_size):
        """将 Gazebo 中匹配的行人模型（见 /rl/gazebo_pedestrian_name_substrings）合并进动态障碍张量。"""
        if not rospy.get_param("/rl/ingest_gazebo_pedestrians", True):
            return
        rng = float(rospy.get_param("/rl/gazebo_ped_inject_range_m", 14.0))
        max_ped = int(rospy.get_param("/rl/gazebo_ped_max_inject", 4))
        dz_c = float(rospy.get_param("/rl/gazebo_ped_z_center_offset", 0.9))
        with self._gz_ped_lock:
            items = sorted(self._gz_ped_track.items(), key=lambda kv: kv[0])
        n = self.cfg.algo.feature_extractor.dyn_obs_num
        used = 0
        for name, rec in items:
            if used >= max_ped:
                break
            ox, oy, oz = rec["pos"]
            dist = float(
                np.sqrt(
                    (ox - drone_pos[0]) ** 2
                    + (oy - drone_pos[1]) ** 2
                    + (oz - drone_pos[2]) ** 2
                )
            )
            if dist > rng:
                continue
            vx, vy, vz = rec["vel"]
            slot = None
            for i in range(n):
                if float(dyn_size[i, 0].item()) < 1e-3:
                    slot = i
                    break
            if slot is None:
                slot = n - 1
            dyn_pos[slot, 0] = float(ox)
            dyn_pos[slot, 1] = float(oy)
            dyn_pos[slot, 2] = float(oz) + dz_c
            dyn_vel[slot, 0] = float(vx)
            dyn_vel[slot, 1] = float(vy)
            dyn_vel[slot, 2] = float(vz)
            dyn_size[slot, 0] = float(rospy.get_param("/rl/gazebo_ped_size_xy", 0.48))
            dyn_size[slot, 1] = float(rospy.get_param("/rl/gazebo_ped_size_xy", 0.48))
            dyn_size[slot, 2] = float(rospy.get_param("/rl/gazebo_ped_size_z", 1.75))
            used += 1

    def dynamic_obstacle_callback(self, event):
        if not self.odom_received:
            return
        pos = np.array([self.odom.pose.pose.position.x, self.odom.pose.pose.position.y, self.odom.pose.pose.position.z])
        dynamic_obstacle_pos, dynamic_obstacle_vel, dynamic_obstacle_size = self.get_dynamic_obstacles(pos)
        self._inject_gazebo_pedestrians(pos, dynamic_obstacle_pos, dynamic_obstacle_vel, dynamic_obstacle_size)
        self.dynamic_obstacles = (dynamic_obstacle_pos, dynamic_obstacle_vel, dynamic_obstacle_size)

    def odom_callback(self, odom):
        self.odom = odom
        self.odom_received = True
        now = rospy.Time.now()
        if not hasattr(self, "last_path_stamp"):
            self.last_path_stamp = rospy.Time.now()
        if (now - self.last_path_stamp).to_sec() >= self.path_publish_interval:
            pose = PoseStamped()
            pose.header.frame_id = "map"
            pose.header.stamp = now
            pose.pose = odom.pose.pose
            self.path_history.header.stamp = now
            self.path_history.poses.append(pose)
            if len(self.path_history.poses) > self.max_path_points:
                self.path_history.poses = self.path_history.poses[-self.max_path_points:]
            self.actual_path_pub.publish(self.path_history)
            self.last_path_stamp = now
    
    def state_callback(self, state):
        self.mavros_state = state
    
    def goal_callback(self, goal):
        if not self.odom_received:
            return

        self.goal = goal
        self.goal.pose.position.z = self.takeoff_pose.pose.position.z
        dir_x = self.goal.pose.position.x - self.odom.pose.pose.position.x
        dir_y = self.goal.pose.position.y - self.odom.pose.pose.position.y
        dir_z = self.goal.pose.position.z - self.odom.pose.pose.position.z
        self.target_dir = torch.tensor([dir_x, dir_y, dir_z], device=self.cfg.device) 

        self.goal_received = True
        self.stable_times = 0

    def target_pose_callback(self, target_pose):
        self.target_received = True
        self.target_stamp = rospy.Time.now()
        if self.nav_mode == "target_follow":
            # Reuse existing goal-follow control path by mapping target pose to goal.
            self.goal_callback(target_pose)

    def quaternion_to_rotation_matrix(self, quaternion):
        # w, x, y, z = quaternion
        w = quaternion.w
        x = quaternion.x
        y = quaternion.y
        z = quaternion.z
        xx, xy, xz = x**2, x*y, x*z
        yy, yz = y**2, y*z
        zz = z**2
        wx, wy, wz = w*x, w*y, w*z
        
        return np.array([
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)]
        ])        
    
    def check_obstacle(self, lidar_scan, dyn_obs_states):
        # return true if there is obstacles in the range
        # has_static = not torch.all(lidar_scan == 0.)
        # has_static = not torch.all(lidar_scan[..., 1:] < 0.2) # hardcode to tune
        quarter_size = lidar_scan.shape[2] // 4
        first_quarter_check, last_quarter_check = torch.all(lidar_scan[:, :, :quarter_size, 1:] < 0.2), torch.all(lidar_scan[:, :, -quarter_size:, 1:] < 0.2)
        has_static = (not first_quarter_check) or (not last_quarter_check)
        has_dynamic = not torch.all(dyn_obs_states == 0.)
        return has_static or has_dynamic

    def get_safe_action(self, vel_world, action_vel_world):
        safe_action = np.zeros(3)
        try:
            pos_msg = Point(x=self.odom.pose.pose.position.x, y=self.odom.pose.pose.position.y, z=self.odom.pose.pose.position.z)
            get_safe_action = rospy.ServiceProxy("rl_navigation/get_safe_action", GetSafeAction)
            vel_msg = Vector3(x=vel_world[0].item(), y=vel_world[1].item(), z=vel_world[2].item())
            action_vel_msg = Vector3(x=action_vel_world[0], y=action_vel_world[1], z=action_vel_world[2])
            max_vel = np.sqrt(3. * self.cfg.algo.actor.action_limit**2)
            obstacle_pos_list = []
            obstacle_vel_list = []
            obstacle_size_list = []
            for i in range(len(self.dynamic_obstacles[0])):
                if (self.dynamic_obstacles[2][i][0] != 0):
                    obs_pos = Vector3(x=self.dynamic_obstacles[0][i][0].item(), y=self.dynamic_obstacles[0][i][1].item(), z=self.dynamic_obstacles[0][i][2].item())
                    obs_vel = Vector3(x=self.dynamic_obstacles[1][i][0].item(), y=self.dynamic_obstacles[1][i][1].item(), z=self.dynamic_obstacles[1][i][2].item())
                    obs_size = Vector3(x=self.dynamic_obstacles[2][i][0].item(), y=self.dynamic_obstacles[2][i][1].item(), z=self.dynamic_obstacles[2][i][2].item())
                    obstacle_pos_list.append(obs_pos)
                    obstacle_vel_list.append(obs_vel)
                    obstacle_size_list.append(obs_size)
            response = get_safe_action(pos_msg, vel_msg, self.robot_size, obstacle_pos_list, obstacle_vel_list,\
                                    obstacle_size_list, self.laser_points_msg, self.cfg.sensor.lidar_range,\
                                    max(self.raycast_vres, self.raycast_hres), max_vel, action_vel_msg)
            safe_action = np.array([response.safe_action.x, response.safe_action.y, response.safe_action.z])
            return safe_action
        except rospy.service.ServiceException as e:
            # print("[nav-ros]: no safety running!")
            return action_vel_world   

    def get_safe_action_map(self, vel_world, action_vel_world):
        safe_action = np.zeros(3)
        try:
            pos_msg = Point(x=self.odom.pose.pose.position.x, y=self.odom.pose.pose.position.y, z=self.odom.pose.pose.position.z)
            get_safe_action = rospy.ServiceProxy("rl_navigation/get_safe_action_map", GetSafeActionMap)
            vel_msg = Vector3(x=vel_world[0].item(), y=vel_world[1].item(), z=vel_world[2].item())
            action_vel_msg = Vector3(x=action_vel_world[0], y=action_vel_world[1], z=action_vel_world[2])
            max_vel = np.sqrt(3. * self.cfg.algo.actor.action_limit**2)
            
            # Dynamic Obstacles
            obstacle_pos_list = []
            obstacle_vel_list = []
            obstacle_size_list = []
            for i in range(len(self.dynamic_obstacles[0])):
                if (self.dynamic_obstacles[2][i][0] != 0):
                    obs_pos = Vector3(x=self.dynamic_obstacles[0][i][0].item(), y=self.dynamic_obstacles[0][i][1].item(), z=self.dynamic_obstacles[0][i][2].item())
                    obs_vel = Vector3(x=self.dynamic_obstacles[1][i][0].item(), y=self.dynamic_obstacles[1][i][1].item(), z=self.dynamic_obstacles[1][i][2].item())
                    obs_size = Vector3(x=self.dynamic_obstacles[2][i][0].item(), y=self.dynamic_obstacles[2][i][1].item(), z=self.dynamic_obstacles[2][i][2].item())
                    obstacle_pos_list.append(obs_pos)
                    obstacle_vel_list.append(obs_vel)
                    obstacle_size_list.append(obs_size)
            
            # Static Obstacles
            static_obstacle_pos, static_obstacle_size, static_obstacle_angle = self.get_static_obstacles()

            response = get_safe_action(pos_msg, vel_msg, self.robot_size, obstacle_pos_list, obstacle_vel_list,\
                                    obstacle_size_list, static_obstacle_pos, static_obstacle_size,\
                                    static_obstacle_angle, max_vel, action_vel_msg)
            safe_action = np.array([response.safe_action.x, response.safe_action.y, response.safe_action.z])
            return safe_action
        except rospy.service.ServiceException as e:
            # print("[nav-ros]: no safety running!")
            return action_vel_world   
    
    def get_action(self, pos: torch.Tensor, vel: torch.Tensor, goal: torch.Tensor): # use world velocity
        rpos = goal - pos
        distance = rpos.norm(dim=-1, keepdim=True)
        distance_2d = rpos[..., :2].norm(dim=-1, keepdim=True)
        distance_z = rpos[..., 2].unsqueeze(-1)


        target_dir_2d = self.target_dir.clone()
        target_dir_2d[2] = 0.

        rpos_clipped = rpos / distance.clamp(1e-6) # start to goal direction
        rpos_clipped_g = vec_to_new_frame(rpos_clipped, target_dir_2d).squeeze(0).squeeze(0)

        # "relative" velocity
        vel_g = vec_to_new_frame(vel, target_dir_2d).squeeze(0).squeeze(0) # goal velocity

        # drone_state = torch.cat([rpos_clipped, orientation, vel_g], dim=-1).squeeze(1)
        drone_state = torch.cat([rpos_clipped_g, distance_2d, distance_z, vel_g], dim=-1).unsqueeze(0)

        # Lidar States
        lidar_scan = torch.tensor(self.raypoints, device=self.cfg.device)
        lidar_scan = (lidar_scan - pos).norm(dim=-1).clamp_max(self.cfg.sensor.lidar_range).reshape(1, 1, self.lidar_hbeams, self.cfg.sensor.lidar_vbeams)
        lidar_scan = self.cfg.sensor.lidar_range - lidar_scan


        # dynamic obstacle states
        dynamic_obstacle_pos = self.dynamic_obstacles[0].clone()
        dynamic_obstacle_vel = self.dynamic_obstacles[1].clone()
        dynamic_obstacle_size = self.dynamic_obstacles[2].clone()
        closest_dyn_obs_rpos = dynamic_obstacle_pos - pos
        closest_dyn_obs_rpos[dynamic_obstacle_size[:, 2] == 0] = 0.
        closest_dyn_obs_rpos[:, 2][dynamic_obstacle_size[:, 2] > 1] = 0.
        closest_dyn_obs_rpos_g = vec_to_new_frame(closest_dyn_obs_rpos.unsqueeze(0), target_dir_2d).squeeze(0)
        closest_dyn_obs_distance = closest_dyn_obs_rpos.norm(dim=-1, keepdim=True)
        closest_dyn_obs_distance_2d = closest_dyn_obs_rpos_g[..., :2].norm(dim=-1, keepdim=True)
        closest_dyn_obs_distance_z = closest_dyn_obs_rpos_g[..., 2].unsqueeze(-1)
        closest_dyn_obs_rpos_gn = closest_dyn_obs_rpos_g / closest_dyn_obs_distance.clamp(1e-6)



        closest_dyn_obs_vel_g = vec_to_new_frame(dynamic_obstacle_vel.unsqueeze(0), target_dir_2d).squeeze(0)
        
        obs_res = 0.25
        closest_dyn_obs_width = torch.max(dynamic_obstacle_size[:, 0], dynamic_obstacle_size[:, 1])
        closest_dyn_obs_width += self.robot_size * 2.
        closest_dyn_obs_width = torch.clamp(torch.ceil(closest_dyn_obs_width / 0.25) - 1, min=0, max=1./obs_res - 1)
        closest_dyn_obs_width[dynamic_obstacle_size[:, 2] == 0] = 0.
        closest_dyn_obs_height = dynamic_obstacle_size[:, 2]
        closest_dyn_obs_height[(closest_dyn_obs_height <= 1) & (closest_dyn_obs_height != 0)] = 1.
        closest_dyn_obs_height[closest_dyn_obs_height > 1] = 0.
        # dyn_obs_states = torch.cat([closest_dyn_obs_rpos_g, closest_dyn_obs_vel_g, \
        #                             closest_dyn_obs_width.unsqueeze(1), closest_dyn_obs_height.unsqueeze(1)], dim=-1).unsqueeze(0).unsqueeze(0)
        dyn_obs_states = torch.cat([closest_dyn_obs_rpos_gn, closest_dyn_obs_distance_2d, closest_dyn_obs_distance_z, closest_dyn_obs_vel_g, \
                                    closest_dyn_obs_width.unsqueeze(1), closest_dyn_obs_height.unsqueeze(1)], dim=-1).unsqueeze(0).unsqueeze(0)
        # states
        obs = TensorDict({
            "agents": TensorDict({
                "observation": TensorDict({
                    "state": drone_state,
                    "lidar": lidar_scan,
                    "direction": target_dir_2d,
                    "dynamic_obstacle": dyn_obs_states
                })
            })
        })

        has_obstacle_in_range = self.check_obstacle(lidar_scan, dyn_obs_states)
        # if (False):
        if (has_obstacle_in_range):
            if (not self.use_policy_server):
                with set_exploration_type(ExplorationType.MEAN):
                    output = self.policy(obs)
                vel_world = output["agents", "action"]
            else:
                try:
                    get_policy_inference = rospy.ServiceProxy("rl_navigation/GetPolicyInference", GetPolicyInference)

                    response = get_policy_inference(obs["agents"]["observation"]["state"].cpu().numpy().flatten().tolist(),
                                                    obs["agents"]["observation"]["state"].size(),
                                                    obs["agents"]["observation"]["lidar"].cpu().numpy().flatten().tolist(),
                                                    obs["agents"]["observation"]["lidar"].size(), 
                                                    obs["agents"]["observation"]["direction"].cpu().numpy().flatten().tolist(),
                                                    obs["agents"]["observation"]["direction"].size(),
                                                    obs["agents"]["observation"]["dynamic_obstacle"].cpu().numpy().flatten().tolist(),
                                                    obs["agents"]["observation"]["dynamic_obstacle"].size())
                    vel_world = torch.tensor(response.action, device=self.cfg.device, dtype=torch.float).unsqueeze(0).unsqueeze(0)
                except rospy.service.ServiceException as e:
                    print("[nav-ros]: Policy server err!")
                    vel_world = torch.tensor([0., 0., 0.], device=self.cfg.device).unsqueeze(0).unsqueeze(0)
        else:
            vel_world =  (goal - pos)/torch.norm(goal - pos) * self.cfg.algo.actor.action_limit

        # 障碍区内接近目标时，增大「指向目标」几何速度分量，减轻 RL 在终点附近绕圈、外飘
        if has_obstacle_in_range:
            fp = float(rospy.get_param("/rl/final_pursuit_xy_m", 2.2))
            if fp > 1e-6:
                d2 = float(distance_2d.reshape(-1)[0].item())
                if d2 < fp and d2 > 1e-4:
                    blend = max(0.0, min(1.0, 1.0 - d2 / fp))
                    pursuit = (goal - pos) / distance.clamp(1e-6) * self.cfg.algo.actor.action_limit
                    vel_world = (1.0 - blend) * vel_world + blend * pursuit
        return vel_world


    def get_rollout_traj(self, pos: torch.Tensor, vel: torch.Tensor, goal: torch.Tensor, dt=0.1, horizon=3.0):
        traj = [pos.cpu().detach().numpy()]
        t = 0.
        while (t < horizon):
            vel_curr_world = self.get_action(pos, vel, goal)
            t += dt
            pos = (pos + dt * vel_curr_world).squeeze(0).squeeze(0)
            vel = vel_curr_world.squeeze(0).squeeze(0)
            traj.append(pos.cpu().detach().numpy())
        return np.array(traj)

    def publish_intent_traj(self, pos: torch.Tensor, vel: torch.Tensor, goal: torch.Tensor):
        traj = self.get_rollout_traj(pos, vel, goal, dt=self.vis_dt, horizon=self.vis_horizon)
        traj_msg = Path()
        traj_msg.header.frame_id = "map"
        traj_msg.header.stamp = rospy.Time.now()
        for i in range(len(traj)):
            p = PoseStamped()
            p.header.frame_id = "map"
            p.header.stamp = traj_msg.header.stamp
            p.pose.position.x = float(traj[i][0])
            p.pose.position.y = float(traj[i][1])
            p.pose.position.z = float(traj[i][2])
            traj_msg.poses.append(p)
        self.intent_path_pub.publish(traj_msg)

    def control_callback(self, event):
        if (not self.odom_received):
            return

        if self.nav_mode == "target_follow":
            if (not self.target_received) or (self.target_stamp is None):
                self.pose_pub.publish(self.takeoff_pose)
                return
            if (rospy.Time.now() - self.target_stamp).to_sec() > self.target_timeout:
                # Lost target: hold current safe pose instead of issuing stale commands.
                self.pose_pub.publish(self.takeoff_pose)
                return

        # 勿用 len(dynamic_obstacles)==0：初始为 [] 与填充后 (tensor,) 元组长度恒为 3，会导致偶发「不控飞 / 逻辑混乱」
        if (not self.goal_received or len(self.raypoints) == 0):
            self.pose_pub.publish(self.takeoff_pose)
            return

        if (self.safety_stop):
            self.pose_pub.publish(self.stop_pose)
            return

        # 每周期用「当前位置→目标」刷新 target_dir。仅在 goal_callback 设一次会导致
        # vec_to_new_frame / yaw 仍对准起飞瞬间的方位，机体漂移后出现乱飞、越飞越远。
        gpx = float(self.goal.pose.position.x - self.odom.pose.pose.position.x)
        gpy = float(self.goal.pose.position.y - self.odom.pose.pose.position.y)
        gpz = float(self.goal.pose.position.z - self.odom.pose.pose.position.z)
        self.target_dir = torch.tensor([gpx, gpy, gpz], device=self.cfg.device, dtype=torch.float32)
        
        start_time = time.time()
        # check for angle
        goal_angle = np.arctan2(self.target_dir[1].cpu().numpy(), self.target_dir[0].cpu().numpy())
        _, _, curr_angle = tf.transformations.euler_from_quaternion([self.odom.pose.pose.orientation.x, self.odom.pose.pose.orientation.y, self.odom.pose.pose.orientation.z, self.odom.pose.pose.orientation.w])
        angle_diff = np.abs(goal_angle - curr_angle)
        if (angle_diff > math.pi):
            angle_diff = np.abs(angle_diff - math.pi * 2)
        if (angle_diff >= self.heading_align_thresh):
            pose_msg = PoseStamped()
            pose_msg.header.stamp = rospy.Time.now()
            pose_msg.header.frame_id = (self.odom.header.frame_id or "map").strip() or "map"
            # 仅用 odom 的 xy 对齐航向；若把 z 也绑在 odom 上，机体下沉时会把 setpoint「跟」到地底，造成起飞后莫名坠地。
            pose_msg.pose.position.x = self.odom.pose.pose.position.x
            pose_msg.pose.position.y = self.odom.pose.pose.position.y
            pose_msg.pose.position.z = float(self.takeoff_pose.pose.position.z)
            quaternion = tf.transformations.quaternion_from_euler(0, 0, goal_angle)
            pose_msg.pose.orientation.w = quaternion[3]
            pose_msg.pose.orientation.x = quaternion[0]
            pose_msg.pose.orientation.y = quaternion[1]
            pose_msg.pose.orientation.z = quaternion[2]
            self.pose_pub.publish(pose_msg)
            return
        else:
            self.stable_times += 1
            if (self.stable_times <= self.heading_align_stable_cycles):
                return

        pos = torch.tensor([self.odom.pose.pose.position.x, self.odom.pose.pose.position.y, self.odom.pose.pose.position.z], device=self.cfg.device)
        goal = torch.tensor([self.goal.pose.position.x, self.goal.pose.position.y, self.goal.pose.position.z], device=self.cfg.device)
        orientation = torch.tensor([self.odom.pose.pose.orientation.w, self.odom.pose.pose.orientation.x, self.odom.pose.pose.orientation.y, self.odom.pose.pose.orientation.z], device=self.cfg.device)
        rot = self.quaternion_to_rotation_matrix(self.odom.pose.pose.orientation)
        vel_body = np.array([self.odom.twist.twist.linear.x, self.odom.twist.twist.linear.y, self.odom.twist.twist.linear.z])
        vel_world = torch.tensor(rot @ vel_body, device=self.cfg.device, dtype=torch.float) # world vel
        
        # get RL action from model
        cmd_vel_world = self.get_action(pos, vel_world, goal).squeeze(0).squeeze(0).detach().cpu().numpy()        
        self.cmd_vel_world = cmd_vel_world.copy()

        # get safe action
        safe_cmd_vel_world = self.get_safe_action(vel_world, cmd_vel_world)
        # safe_cmd_vel_world = self.get_safe_action_map(vel_world, cmd_vel_world)
        # safe_cmd_vel_world[2] = 0
        self.safe_cmd_vel_world = safe_cmd_vel_world.copy()
        quat_no_tilt = tf.transformations.quaternion_from_euler(0, 0, curr_angle)
        quat_msg = Quaternion()
        quat_msg.w = quat_no_tilt[3]
        quat_msg.x = quat_no_tilt[0]
        quat_msg.y = quat_no_tilt[1]
        quat_msg.z = quat_no_tilt[2]
        rot_no_tilt = self.quaternion_to_rotation_matrix(quat_msg)
        safe_cmd_vel_local = np.linalg.inv(rot_no_tilt) @ safe_cmd_vel_world

        # Goal condition and speed profile:
        # - far: allow faster cruise
        # - near: keep moving but slower
        # - reached: stop only in small radius
        distance = float((pos - goal).norm().item())
        cmd_norm_local = float(np.linalg.norm(safe_cmd_vel_local))
        cmd_norm_world = float(np.linalg.norm(safe_cmd_vel_world))

        if distance <= self.goal_reach_radius:
            safe_cmd_vel_local *= 0.0
            safe_cmd_vel_world *= 0.0
        elif distance <= self.slowdown_radius:
            if cmd_norm_local > 1e-6:
                target = min(self.near_goal_speed, self.max_nav_speed)
                safe_cmd_vel_local = target * safe_cmd_vel_local / cmd_norm_local
            if cmd_norm_world > 1e-6:
                target = min(self.near_goal_speed, self.max_nav_speed)
                safe_cmd_vel_world = target * safe_cmd_vel_world / cmd_norm_world
        else:
            if cmd_norm_local > self.max_nav_speed:
                safe_cmd_vel_local = self.max_nav_speed * safe_cmd_vel_local / cmd_norm_local
            if cmd_norm_world > self.max_nav_speed:
                safe_cmd_vel_world = self.max_nav_speed * safe_cmd_vel_world / cmd_norm_world

        # final action
        if (self.px4_control):
            final_cmd_vel = PositionTarget()
            final_cmd_vel.coordinate_frame = final_cmd_vel.FRAME_LOCAL_NED
            final_cmd_vel.header.stamp = rospy.Time.now()
            final_cmd_vel.header.frame_id = "map"
            if (self.height_control):
                final_cmd_vel.velocity.x = safe_cmd_vel_world[0]
                final_cmd_vel.velocity.y = safe_cmd_vel_world[1]
                final_cmd_vel.velocity.z = safe_cmd_vel_world[2]
                final_cmd_vel.yaw = goal_angle
                final_cmd_vel.type_mask = final_cmd_vel.IGNORE_PX + final_cmd_vel.IGNORE_PY + final_cmd_vel.IGNORE_PZ + \
                    final_cmd_vel.IGNORE_AFX + final_cmd_vel.IGNORE_AFY + final_cmd_vel.IGNORE_AFZ + final_cmd_vel.IGNORE_YAW_RATE
            else:
                final_cmd_vel.velocity.x = safe_cmd_vel_world[0]
                final_cmd_vel.velocity.y = safe_cmd_vel_world[1]
                final_cmd_vel.position.z = self.takeoff_pose.pose.position.z
                final_cmd_vel.yaw = goal_angle
                final_cmd_vel.type_mask = final_cmd_vel.IGNORE_PX + final_cmd_vel.IGNORE_PY + final_cmd_vel.IGNORE_VZ + \
                    final_cmd_vel.IGNORE_AFX + final_cmd_vel.IGNORE_AFY + final_cmd_vel.IGNORE_AFZ + final_cmd_vel.IGNORE_YAW_RATE                           
        else:
            final_cmd_vel = TwistStamped()
            final_cmd_vel.header.stamp = rospy.Time.now()
            final_cmd_vel.twist.linear.x = safe_cmd_vel_local[0]
            final_cmd_vel.twist.linear.y = safe_cmd_vel_local[1]
            if (self.height_control):
                final_cmd_vel.twist.linear.z = safe_cmd_vel_world[2]
            else:
                final_cmd_vel.twist.linear.z = 0
        self.action_pub.publish(final_cmd_vel)
        self.has_action = True
        self.publish_intent_traj(pos, vel_world, goal)

        # rollout_traj = self.get_rollout_traj(pos, vel_world, goal, dt=0.1, horizon=3.0)
        # traj_msg = Path()
        # traj_msg.header.frame_id = "map"
        # for i in range(len(rollout_traj)):
        #     p = PoseStamped()
        #     p.pose.position.x = rollout_traj[i][0]
        #     p.pose.position.y = rollout_traj[i][1]
        #     p.pose.position.z = rollout_traj[i][2]
        #     traj_msg.poses.append(p)
        # self.rollout_traj_pub.publish(traj_msg)
        end_time = time.time()
        # print("[nav-ros]: control time ", end_time - start_time)
        
    def pause_sim():
        rospy.wait_for_service('/gazebo/pause_physics')
        pause = rospy.ServiceProxy('/gazebo/pause_physics', Empty)
        pause()

    def unpause_sim():
        rospy.wait_for_service('/gazebo/unpause_physics')
        unpause = rospy.ServiceProxy('/gazebo/unpause_physics', Empty)
        unpause()

    def run(self):
        raycast_timer = rospy.Timer(rospy.Duration(0.05), self.raycast_callback)
        raycast_vis_timer = rospy.Timer(rospy.Duration(0.05), self.raycast_vis_callback)
        control_timer = rospy.Timer(rospy.Duration(0.05), self.control_callback)
        goal_vis_timer = rospy.Timer(rospy.Duration(0.05), self.goal_vis_callback)
        dynamic_obstacle_timer = rospy.Timer(rospy.Duration(0.05), self.dynamic_obstacle_callback)
        dynamic_obstacle_vis_timer = rospy.Timer(rospy.Duration(0.05), self.dynamic_obstacle_vis_callback)
        cmd_vis_timer = rospy.Timer(rospy.Duration(0.05), self.cmd_vis_callback)

    def raycast_vis_callback(self, event):
        if not self.odom_received and not self.goal_received:
            return
        msg = MarkerArray()
        pos = self.odom.pose.pose.position
        direction_init = None
        for i in range(len(self.raypoints)):
            point = Marker()
            point.header.frame_id = "map"
            point.header.stamp = rospy.get_rostime()
            point.ns = "raycast_points"
            point.id = i
            point.type = point.SPHERE
            point.action = point.ADD
            point.pose.position.x = self.raypoints[i][0]
            point.pose.position.y = self.raypoints[i][1]
            point.pose.position.z = self.raypoints[i][2]
            point.lifetime = rospy.Time(0.5)
            point.scale.x = 0.1
            point.scale.y = 0.1
            point.scale.z = 0.1
            point.color.a = 1.0
            point.color.r = 1.0
            msg.markers.append(point)

            line = Marker()
            line.header.frame_id = "map"
            line.header.stamp = rospy.get_rostime()
            line.ns = "raycast_lines"
            line.id = i
            line.type = line.LINE_LIST
            p = Point()
            p.x = self.raypoints[i][0]
            p.y = self.raypoints[i][1]
            p.z = self.raypoints[i][2]
            line.points.append(p)
            line.points.append(pos)
            line.scale.x = 0.03
            line.scale.y = 0.03
            line.scale.z = 0.03
            x_diff = (p.x - self.odom.pose.pose.position.x)
            y_diff = (p.y - self.odom.pose.pose.position.y)
            direction = np.array([x_diff, y_diff])
            direction = direction/np.linalg.norm(direction)
            if (i == 0 or (np.linalg.norm(direction - direction_init) <= 0.1)):
                line.color.b = 1.0
                line.color.a = 1.0
                if (i == 0):
                    direction_init = direction
            else:
                line.color.g = 1.0
                line.color.a = 0.5
            line.lifetime = rospy.Time(0.5)
            msg.markers.append(line)
        self.raycast_vis_pub.publish(msg)
    
    def goal_vis_callback(self, event):
        if not self.goal_received:
            return
        msg = MarkerArray()
        goal_point = Marker()
        goal_point.header.frame_id = "map"
        goal_point.header.stamp = rospy.get_rostime()
        goal_point.ns = "goal_point"
        goal_point.id = 1
        goal_point.type = goal_point.SPHERE
        goal_point.action = goal_point.ADD
        goal_point.pose.position.x = self.goal.pose.position.x
        goal_point.pose.position.y = self.goal.pose.position.y
        goal_point.pose.position.z = self.goal.pose.position.z
        goal_point.lifetime = rospy.Time(0.1)
        goal_point.scale.x = 0.3
        goal_point.scale.y = 0.3
        goal_point.scale.z = 0.3
        goal_point.color.r = 1.0
        goal_point.color.b = 1.0
        goal_point.color.a = 1.0
        msg.markers.append(goal_point)
        self.goal_vis_pub.publish(msg)

    def dynamic_obstacle_vis_callback(self, event):
        if not isinstance(self.dynamic_obstacles, tuple) or len(self.dynamic_obstacles) < 3:
            return
        dynamic_obstacle_pos = self.dynamic_obstacles[0]
        dynamic_obstacle_size = self.dynamic_obstacles[2]

        msg = MarkerArray()
        inflated_msg = MarkerArray()
        for i in range(dynamic_obstacle_pos.size(0)):
            pos = dynamic_obstacle_pos[i]
            size = dynamic_obstacle_size[i]

            # Increase the width
            width = torch.max(size[0], size[1])
            height = size[2]

            # Create the marker
            marker = Marker()
            marker.header.frame_id = "map"
            marker.header.stamp = rospy.Time.now()
            marker.ns = "dynamic_obstacles"
            marker.id = i
            marker.type = Marker.CUBE
            marker.action = Marker.ADD
            marker.pose.position.x = pos[0]
            marker.pose.position.y = pos[1]
            marker.pose.position.z = pos[2] 
            marker.pose.orientation.x = 0.0
            marker.pose.orientation.y = 0.0
            marker.pose.orientation.z = 0.0
            marker.pose.orientation.w = 1.0
            marker.scale.x = width
            marker.scale.y = width
            marker.scale.z = height 
            marker.color.a = 0.5  # Alpha value
            marker.color.r = 1.0  # Red color
            marker.color.g = 0.0
            marker.color.b = 0.0

            msg.markers.append(marker)

            inflated = Marker()
            inflated.header.frame_id = "map"
            inflated.header.stamp = rospy.Time.now()
            inflated.ns = "inflated_obstacles"
            inflated.id = i
            inflated.type = Marker.CYLINDER
            inflated.action = Marker.ADD
            inflated.pose.position.x = pos[0]
            inflated.pose.position.y = pos[1]
            inflated.pose.position.z = pos[2]
            inflated.pose.orientation.x = 0.0
            inflated.pose.orientation.y = 0.0
            inflated.pose.orientation.z = 0.0
            inflated.pose.orientation.w = 1.0
            inflated.scale.x = width + 2.0 * self.safety_inflation
            inflated.scale.y = width + 2.0 * self.safety_inflation
            inflated.scale.z = max(0.1, height)
            inflated.color.a = 0.25
            inflated.color.r = 1.0
            inflated.color.g = 0.2
            inflated.color.b = 0.2
            inflated_msg.markers.append(inflated)

        # Publish the marker array
        self.dynamic_obstacle_vis_pub.publish(msg)
        self.inflated_obstacle_vis_pub.publish(inflated_msg)

    def cmd_vis_callback(self, event):
        if (not self.has_action):
            return
        msg = MarkerArray()

        # rl action vis
        rl_action_arrow = Marker()
        rl_action_arrow.header.frame_id = "map"
        rl_action_arrow.header.stamp = rospy.get_rostime()
        rl_action_arrow.ns = "rl_action"
        rl_action_arrow.id = 0
        rl_action_arrow.type = rl_action_arrow.ARROW
        rl_action_arrow.action = rl_action_arrow.ADD

        # start
        agent_pos = Point()
        agent_pos.x = self.odom.pose.pose.position.x
        agent_pos.y = self.odom.pose.pose.position.y
        agent_pos.z = self.odom.pose.pose.position.z
        
        # end
        vel_end = Point()
        vel_end.x = self.cmd_vel_world[0] + agent_pos.x
        vel_end.y = self.cmd_vel_world[1] + agent_pos.y
        vel_end.z = self.cmd_vel_world[2] + agent_pos.z

        rl_action_arrow.points.append(agent_pos)
        rl_action_arrow.points.append(vel_end)
        rl_action_arrow.lifetime = rospy.Duration(0.1)
        rl_action_arrow.scale.x = 0.06
        rl_action_arrow.scale.y = 0.06
        rl_action_arrow.scale.z = 0.06
        rl_action_arrow.color.a = 1.0
        rl_action_arrow.color.r = 1.0
        rl_action_arrow.color.g = 0.0
        rl_action_arrow.color.b = 0.0
        msg.markers.append(rl_action_arrow)


        # safe action vis
        safe_action_arrow = Marker()
        safe_action_arrow.header.frame_id = "map"
        safe_action_arrow.header.stamp = rospy.get_rostime()
        safe_action_arrow.ns = "safe_action"
        safe_action_arrow.id = 1
        safe_action_arrow.type = safe_action_arrow.ARROW
        safe_action_arrow.action = safe_action_arrow.ADD

        # start
        agent_pos = Point()
        agent_pos.x = self.odom.pose.pose.position.x
        agent_pos.y = self.odom.pose.pose.position.y
        agent_pos.z = self.odom.pose.pose.position.z

        # end
        vel_end = Point()
        vel_end.x = self.safe_cmd_vel_world[0] + agent_pos.x
        vel_end.y = self.safe_cmd_vel_world[1] + agent_pos.y
        vel_end.z = self.safe_cmd_vel_world[2] + agent_pos.z

        safe_action_arrow.points.append(agent_pos)
        safe_action_arrow.points.append(vel_end)
        safe_action_arrow.lifetime = rospy.Duration(0.1)
        safe_action_arrow.scale.x = 0.06
        safe_action_arrow.scale.y = 0.06
        safe_action_arrow.scale.z = 0.06
        safe_action_arrow.color.a = 1.0
        safe_action_arrow.color.r = 0.0
        safe_action_arrow.color.g = 1.0
        safe_action_arrow.color.b = 0.0

        msg.markers.append(safe_action_arrow)
        self.cmd_vis_pub.publish(msg)