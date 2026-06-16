# 无人机自主导航系统

基于 **ROS Noetic** 的无人机自主导航 **地面站**：集成 **RViz** 三维显示、实时数据监控、动态障碍物跟踪、航点巡航与手动操控。

### 技术栈与约束

- **ROS 1 Noetic** + **python_qt_binding**（或 PyQt5）+ **rviz** Python 绑定。
- 推荐 **Ubuntu 20.04**；**22.04** 建议 Docker 跑 20.04+Noetic 或独立环境。
- 地面站**不内置**飞控/规划 C++ 代码；通过 **话题与服务** 对接用户 `catkin_ws` 里的仿真与算法包。

## 主要功能

- **导航控制**：按 `processes_config.json` 一键启动多进程；航点对话框多目标巡航；一键返航与降落流程（FSM 滞回 + 距离兜底）。
- **控制中心**：自主圆盘（启动 / 前往目标 / 停止 / 返航 / 导入点云占位）与手动页（起飞、方向键连续控制）。
- **实时图像**：右侧 RGB / 深度切换；鸟瞰图（若话题存在）。
- **障碍物**：表格展示动态障碍物（MarkerArray 或 ObjectsStates）。
- **RViz**：中部全高嵌入，`my_config.rviz` 配置点云、轨迹、预测 Marker 等。
- **话题日志**：`topic_logger.py`。
- **UI 体验**：`ui_notify.py` Toast + 可选录屏自动确认。

---

## 启动方式

```bash
source /opt/ros/noetic/setup.bash
source ~/catkin_ws_dyn/devel/setup.bash

cd ~/projects/explore_system
python3 start.py
```

安装脚本（若存在）：`quick_install.sh` — 在 **Ubuntu 22.04** 上可能直接退出并提示换 20.04/Docker，属预期行为。

---

## Ubuntu 22.04（Jammy）说明

ROS1 Noetic 官方主要针对 **20.04**。在 22.04 上建议：

- **Docker**：`ubuntu:20.04` + Noetic；或  
- **原生 20.04**（双系统 / 虚拟机 / 另一台机）。

不建议在 22.04 强行混装 Noetic + 重编 PX4/Gazebo 全插件（易依赖/内存问题）。


---

## 项目结构

```
explore_system/
├── start.py                 # 主程序
├── dashboard.py             # 滑动控制中心（自主 + 手动）
├── topics_subscriber.py     # ROS 话题订阅
├── topics_config.json       # 话题配置
├── waypoint_dialog.py       # 航点对话框（读 navigation_config 多话题发布）
├── navigation_config.json   # 目标话题、FSM/距离参数、预测 Marker 列表
├── control_backends.py      # px4ctrl / mavros / hybrid
├── control_config.json      # 控制后端开关与参数
├── integration_health.py    # 对接健康检查摘要
├── ui_notify.py             # Toast / confirm / notify_error
├── ui_config.json           # Toast 与 auto_confirm_actions
├── processes_config.json    # 一键启停进程与 stop_pattern
├── utils.py                 # 路径、load_processes_config、默认配置
├── manual_controller.py     # RC 覆写式手动（后备）
├── topic_logger.py          # 话题日志窗口
├── images_rc.py             # Qt 资源
├── my_config.rviz           # RViz 配置（按工程替换）
├── resource/                # 图标与 qrc
└── README.md
```

## 依赖要求

- Ubuntu **20.04**（推荐）
- ROS **Noetic**
- Python **3.8+**
- `python_qt_binding`、`rviz`、OpenCV、`numpy`、`psutil` 等

```bash
pip3 install numpy opencv-python psutil
# PyQt / python_qt_binding 以 apt/ros 依赖为准
```

---

## 操作说明（自主页 / 手动页）

| 操作 | 功能 |
|------|------|
| 一键启动 | 按 `processes_config.json` 顺序启动进程 |
| 前往目标 | 打开航点对话框：添加/导入航点、「开始导航」 |
| 停止程序 | 逆序终止已启动进程 + 按配置 pkill + 清理 rosnode（保留 roscore 策略见代码） |
| 一键返航 | 向 `goal_topics` 发 (0,0,0.8)，FSM/距离就绪后发送降落 |
| 手动页 | 起飞走后端；Hybrid 下方向键为 MAVROS OFFBOARD 速度 |
| 导入点云 | 占位（Toast 提示未实现） |

