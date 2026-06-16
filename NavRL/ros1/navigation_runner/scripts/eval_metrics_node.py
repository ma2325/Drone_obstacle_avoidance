#!/usr/bin/env python3
"""
Online evaluator for NavRL ROS1 demos.

Metrics (single run):
- success (reach goal within threshold)
- time_to_goal_sec
- min_clearance_m (from /rl_navigation/raycast points)
- mean_speed_mps
- mean_acc_cmd_mps2 and max_acc_cmd_mps2 (from cmd_vel finite difference)

Usage:
  rosrun navigation_runner eval_metrics_node.py _run_name:=ours_run1
"""

import csv
import math
import os
from datetime import datetime

import rospy
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Odometry
from visualization_msgs.msg import MarkerArray


class EvalMetricsNode:
    def __init__(self):
        self.run_name = rospy.get_param("~run_name", "navrl_run")
        self.goal_reach_threshold = float(rospy.get_param("~goal_reach_threshold", 1.0))
        self.stop_on_success = bool(rospy.get_param("~stop_on_success", True))
        self.csv_path = rospy.get_param("~csv_path", "")
        self.save_period = float(rospy.get_param("~save_period", 1.0))

        # State
        self.curr_pos = None
        self.curr_vel = None
        self.goal = None
        self.goal_active = False
        self.run_started = False
        self.start_time = None
        self.end_time = None
        self.success = False
        self.min_clearance = float("inf")
        self.speed_sum = 0.0
        self.speed_count = 0
        self.acc_sum = 0.0
        self.acc_count = 0
        self.acc_max = 0.0
        self.last_cmd = None
        self.last_cmd_stamp = None

        # Subscriptions (non-PX4 topics)
        self.odom_sub = rospy.Subscriber("/CERLAB/quadcopter/odom", Odometry, self.odom_cb, queue_size=10)
        self.goal_sub = rospy.Subscriber("/move_base_simple/goal", PoseStamped, self.goal_cb, queue_size=10)
        self.raycast_sub = rospy.Subscriber("/rl_navigation/raycast", MarkerArray, self.raycast_cb, queue_size=10)
        self.cmd_sub = rospy.Subscriber("/CERLAB/quadcopter/cmd_vel", TwistStamped, self.cmd_cb, queue_size=20)

        self.timer = rospy.Timer(rospy.Duration(self.save_period), self.timer_cb)
        rospy.on_shutdown(self.on_shutdown)
        rospy.loginfo("[eval] started: run_name=%s", self.run_name)

    def odom_cb(self, msg: Odometry):
        p = msg.pose.pose.position
        v = msg.twist.twist.linear
        self.curr_pos = (p.x, p.y, p.z)
        self.curr_vel = (v.x, v.y, v.z)

        speed = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
        self.speed_sum += speed
        self.speed_count += 1

        if self.goal_active and self.goal is not None:
            d = self.dist3(self.curr_pos, self.goal)
            if d <= self.goal_reach_threshold and not self.success:
                self.success = True
                self.end_time = rospy.Time.now()
                rospy.loginfo("[eval] success reached. distance=%.3f", d)
                self.flush_csv()
                if self.stop_on_success:
                    rospy.signal_shutdown("goal reached")

    def goal_cb(self, msg: PoseStamped):
        g = msg.pose.position
        self.goal = (g.x, g.y, g.z)
        self.goal_active = True
        if not self.run_started:
            self.run_started = True
            self.start_time = rospy.Time.now()
        rospy.loginfo("[eval] new goal: (%.2f, %.2f, %.2f)", g.x, g.y, g.z)

    def raycast_cb(self, msg: MarkerArray):
        if self.curr_pos is None:
            return
        px, py, pz = self.curr_pos
        local_min = float("inf")
        for mk in msg.markers:
            # raycast_points markers store one point; lines store two points
            for pt in mk.points:
                d = math.sqrt((pt.x - px) ** 2 + (pt.y - py) ** 2 + (pt.z - pz) ** 2)
                if d < local_min:
                    local_min = d
        if local_min < self.min_clearance:
            self.min_clearance = local_min

    def cmd_cb(self, msg: TwistStamped):
        t = msg.header.stamp if msg.header.stamp != rospy.Time(0) else rospy.Time.now()
        cmd = (msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z)
        if self.last_cmd is not None and self.last_cmd_stamp is not None:
            dt = (t - self.last_cmd_stamp).to_sec()
            if dt > 1e-4:
                ax = (cmd[0] - self.last_cmd[0]) / dt
                ay = (cmd[1] - self.last_cmd[1]) / dt
                az = (cmd[2] - self.last_cmd[2]) / dt
                acc = math.sqrt(ax * ax + ay * ay + az * az)
                self.acc_sum += acc
                self.acc_count += 1
                if acc > self.acc_max:
                    self.acc_max = acc
        self.last_cmd = cmd
        self.last_cmd_stamp = t

    def timer_cb(self, _event):
        # Periodic progress logging only.
        if not self.run_started:
            return
        t_now = rospy.Time.now()
        elapsed = (t_now - self.start_time).to_sec() if self.start_time else 0.0
        rospy.loginfo_throttle(
            2.0,
            "[eval] elapsed=%.1fs success=%s min_clearance=%.3f",
            elapsed,
            str(self.success),
            self.min_clearance if self.min_clearance < 1e8 else float("nan"),
        )

    def metrics_row(self):
        if self.end_time is None and self.start_time is not None:
            t_goal = (rospy.Time.now() - self.start_time).to_sec()
        elif self.end_time is not None and self.start_time is not None:
            t_goal = (self.end_time - self.start_time).to_sec()
        else:
            t_goal = float("nan")

        mean_speed = self.speed_sum / self.speed_count if self.speed_count > 0 else float("nan")
        mean_acc = self.acc_sum / self.acc_count if self.acc_count > 0 else float("nan")
        min_clearance = self.min_clearance if self.min_clearance < 1e8 else float("nan")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [
            stamp,
            self.run_name,
            int(self.success),
            t_goal,
            min_clearance,
            mean_speed,
            mean_acc,
            self.acc_max,
        ]

    def flush_csv(self):
        out = self.csv_path
        if not out:
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
            out_dir = os.path.abspath(out_dir)
            os.makedirs(out_dir, exist_ok=True)
            out = os.path.join(out_dir, "eval_metrics.csv")
        out = os.path.abspath(out)
        os.makedirs(os.path.dirname(out), exist_ok=True)

        header = [
            "timestamp",
            "run_name",
            "success",
            "time_to_goal_sec",
            "min_clearance_m",
            "mean_speed_mps",
            "mean_acc_cmd_mps2",
            "max_acc_cmd_mps2",
        ]
        row = self.metrics_row()
        write_header = not os.path.exists(out)
        with open(out, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(header)
            w.writerow(row)
        rospy.loginfo("[eval] metrics saved -> %s", out)
        rospy.loginfo("[eval] row=%s", row)

    def on_shutdown(self):
        if self.run_started:
            self.flush_csv()

    @staticmethod
    def dist3(a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


if __name__ == "__main__":
    rospy.init_node("eval_metrics_node", anonymous=False)
    EvalMetricsNode()
    rospy.spin()
