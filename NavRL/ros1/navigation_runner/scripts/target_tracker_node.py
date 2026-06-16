#!/usr/bin/env python3
"""
Lightweight target tracker node for fast demo integration.

Publishes:
- /tracking/target_pose (PoseStamped): selected moving target as navigation target
- /tracking/target_path (Path): target history for RViz

Selection policy:
- Query onboard_detector/get_dynamic_obstacles around the UAV
- Pick nearest detected dynamic obstacle
"""

import math
import rospy
from geometry_msgs.msg import Point, PoseStamped
from nav_msgs.msg import Odometry, Path
from onboard_detector.srv import GetDynamicObstacles


class TargetTrackerNode:
    def __init__(self):
        self.odom = None
        self.query_range = float(rospy.get_param("~query_range", 12.0))
        self.update_hz = float(rospy.get_param("~update_hz", 10.0))
        self.min_height = float(rospy.get_param("~min_height", 0.8))
        self.path_max_len = int(rospy.get_param("~path_max_len", 400))

        self.target_pub = rospy.Publisher("/tracking/target_pose", PoseStamped, queue_size=10)
        self.path_pub = rospy.Publisher("/tracking/target_path", Path, queue_size=10)
        self.path_msg = Path()
        self.path_msg.header.frame_id = "map"

        self.odom_sub = rospy.Subscriber("/CERLAB/quadcopter/odom", Odometry, self.odom_cb, queue_size=20)
        self.get_dyn_obs = rospy.ServiceProxy("onboard_detector/get_dynamic_obstacles", GetDynamicObstacles)

    def odom_cb(self, msg):
        self.odom = msg

    def run(self):
        rate = rospy.Rate(self.update_hz)
        while not rospy.is_shutdown():
            if self.odom is None:
                rate.sleep()
                continue
            try:
                curr = self.odom.pose.pose.position
                curr_msg = Point(x=curr.x, y=curr.y, z=curr.z)
                resp = self.get_dyn_obs(curr_msg, self.query_range)
                n = len(resp.position)
                if n == 0:
                    rate.sleep()
                    continue

                best_idx = 0
                best_d = float("inf")
                for i in range(n):
                    p = resp.position[i]
                    d = math.hypot(p.x - curr.x, p.y - curr.y)
                    if d < best_d:
                        best_d = d
                        best_idx = i

                p = resp.position[best_idx]
                pose = PoseStamped()
                pose.header.stamp = rospy.Time.now()
                pose.header.frame_id = "map"
                pose.pose.position.x = p.x
                pose.pose.position.y = p.y
                pose.pose.position.z = max(self.min_height, p.z)
                pose.pose.orientation.w = 1.0
                self.target_pub.publish(pose)

                self.path_msg.header.stamp = pose.header.stamp
                self.path_msg.poses.append(pose)
                if len(self.path_msg.poses) > self.path_max_len:
                    self.path_msg.poses = self.path_msg.poses[-self.path_max_len :]
                self.path_pub.publish(self.path_msg)
            except rospy.ServiceException:
                rospy.logwarn_throttle(2.0, "[target-tracker] dynamic obstacle service unavailable")
            rate.sleep()


if __name__ == "__main__":
    rospy.init_node("target_tracker_node", anonymous=False)
    TargetTrackerNode().run()
