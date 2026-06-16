#!/usr/bin/env python3
"""
Publish fixed 2D Nav Goals automatically for repeatable experiments.

Example:
  python3 auto_goal_runner.py
"""

import math
import rospy
from geometry_msgs.msg import PoseStamped, Quaternion
from nav_msgs.msg import Odometry
import tf.transformations


class AutoGoalRunner:
    def __init__(self):
        self.frame_id = rospy.get_param("~frame_id", "map")
        self.reach_thresh = float(rospy.get_param("~reach_thresh", 1.0))
        self.goal_timeout = float(rospy.get_param("~goal_timeout", 60.0))
        self.loop = bool(rospy.get_param("~loop", False))
        self.start_delay = float(rospy.get_param("~start_delay", 3.0))
        # default square-style goal set
        self.goals = rospy.get_param(
            "~goals",
            [
                [-6.0, 0.0, 0.0],
                [0.0, 6.0, 1.57],
                [6.0, 0.0, 3.14],
                [0.0, -6.0, -1.57],
            ],
        )

        self.odom = None
        self.goal_idx = 0
        self.goal_sent_time = None
        self.active = False

        self.goal_pub = rospy.Publisher("/move_base_simple/goal", PoseStamped, queue_size=10, latch=True)
        self.odom_sub = rospy.Subscriber("/CERLAB/quadcopter/odom", Odometry, self.odom_cb, queue_size=10)
        self.timer = rospy.Timer(rospy.Duration(0.1), self.tick)
        rospy.loginfo("[auto-goal] waiting %.1fs before first goal", self.start_delay)
        rospy.sleep(self.start_delay)
        self.send_goal(self.goal_idx)

    def odom_cb(self, msg):
        self.odom = msg

    def send_goal(self, idx):
        if idx >= len(self.goals):
            if self.loop:
                self.goal_idx = 0
                idx = 0
            else:
                rospy.loginfo("[auto-goal] all goals completed")
                rospy.signal_shutdown("all goals completed")
                return
        gx, gy, gyaw = self.goals[idx]
        q = tf.transformations.quaternion_from_euler(0, 0, gyaw)
        msg = PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = self.frame_id
        msg.pose.position.x = gx
        msg.pose.position.y = gy
        msg.pose.position.z = 0.0
        msg.pose.orientation = Quaternion(x=q[0], y=q[1], z=q[2], w=q[3])
        self.goal_pub.publish(msg)
        self.goal_sent_time = rospy.Time.now()
        self.active = True
        rospy.loginfo("[auto-goal] publish goal %d -> (%.2f, %.2f, %.2f)", idx + 1, gx, gy, gyaw)

    def tick(self, _):
        if not self.active or self.odom is None:
            return
        gx, gy, _ = self.goals[self.goal_idx]
        px = self.odom.pose.pose.position.x
        py = self.odom.pose.pose.position.y
        dist = math.sqrt((gx - px) ** 2 + (gy - py) ** 2)
        if dist <= self.reach_thresh:
            rospy.loginfo("[auto-goal] reached goal %d (dist=%.2f)", self.goal_idx + 1, dist)
            self.active = False
            self.goal_idx += 1
            rospy.sleep(1.0)
            self.send_goal(self.goal_idx)
            return
        if self.goal_sent_time is not None:
            if (rospy.Time.now() - self.goal_sent_time).to_sec() >= self.goal_timeout:
                rospy.logwarn("[auto-goal] goal %d timeout, switch to next", self.goal_idx + 1)
                self.active = False
                self.goal_idx += 1
                self.send_goal(self.goal_idx)


if __name__ == "__main__":
    rospy.init_node("auto_goal_runner", anonymous=False)
    AutoGoalRunner()
    rospy.spin()
