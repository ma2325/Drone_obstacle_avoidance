# 🚁 无人机地面站连接使用手册

> **项目说明**：基于Vue 3开发的Web无人机地面站，支持F410无人机实时数据监控

---

## 📋 快速开始（3步）

### 第1步：启动系统

# 🔄 手动启动（调试用）

### 终端1：MAVProxy
```bash
conda activate drone_f410//这是我的环境，记得配置成你的
python -m MAVProxy.mavproxy --master=udp:0.0.0.0:8080 --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
```

### 终端2：Python桥接
```bash
conda activate drone_f410
python drone_bridge.py
```

### 终端3：Vue前端
```bash
npm run dev

```
器）


---

### 第2步：访问地面站

浏览器自动打开，或手动访问：
```
http://localhost:5173
```

**主界面左侧会显示无人机实时数据面板**

---

### 第3步：连接无人机

**前置条件**：
- ✅ 无人机已开机
- ✅ 遥控器已连接到电脑（网线或WiFi）
- ✅ 数传端口设置为 **UDP 8080**

**连接成功标志**：
- MAVProxy窗口显示：`Received 512 parameters`
- 浏览器左侧数据面板显示：**已连接**
- 数据开始实时更新（每秒10次）

---

## 🎯 核心功能

### 主界面数据面板（左侧）

实时显示6组关键数据：

| 数据组 | 包含内容 | 说明 |
|--------|---------|------|
| **飞行状态** | 模式、电机状态 | 显示当前飞行模式和解锁状态 |
| **🎯 离地高度** | 测距仪/GPS高度 | **重点数据**，优先显示测距仪 |
| **GPS位置** | 定位状态、卫星数、坐标 | 室外飞行必看 |
| **🎯 飞行速度** | 地面速度、垂直速度 | **重点数据**，实时速度 |
| **姿态角度** | 横滚、俯仰、航向 | 无人机倾斜和方向 |
| **电池状态** | 电压、电流、剩余% | 及时返航判断 |

### 测试页面（详细数据）

访问：`http://localhost:5173/drone-test`

**用途**：查看完整数据、调试、测试连接

---

## 🔧 系统架构（技术说明）

```
┌─────────────┐  MAVLink  ┌──────────┐  WebSocket  ┌──────────┐
│ F410无人机   │ ────────→ │ Python   │ ──────────→ │ Vue前端   │
│  (飞控)     │   UDP     │ 桥接服务  │    JSON     │ (浏览器)  │
└─────────────┘           └──────────┘             └──────────┘
     ↓                          ↓                        ↓
  MAVLink协议            协议转换中心              可视化界面
  (二进制)               drone_bridge.py          DroneDataPanel.vue
```

**为什么需要桥接服务？**
- ❌ 浏览器无法直接访问UDP/串口
- ❌ 浏览器无法解析MAVLink二进制协议
- ✅ Python桥接服务负责"翻译"成浏览器能理解的JSON

---

## 📂 项目结构

```
demo_page_0924/
│
├── drone_bridge.py              ← 核心：Python桥接服务
├── start_drone_system.bat       ← 一键启动脚本
│
├── src/
│   ├── components/
│   │   ├── Home/
│   │   │   └── DroneDataPanel.vue   ← 主界面数据面板
│   │   └── DroneTest.vue            ← 测试页面（完整数据）
│   │
│   └── router/index.js          ← 路由配置
│
└── package.json                 ← 前端依赖
```

---

## ⚙️ 端口说明

| 端口 | 用途 | 说明 |
|------|------|------|
| **8080** | 数传地面端 | 无人机数据入口（QGC默认端口） |
| **14550** | MAVProxy输出1 | 可选：给QGC用（多地面站） |
| **14551** | MAVProxy输出2 | 给Python桥接服务 |
| **8765** | WebSocket | Python → Vue前端通信 |
| **5173** | Vue开发服务器 | 浏览器访问地址 |

---

## 🚨 常见问题

### Q1：数据面板显示"等待数据"？

**原因**：MAVProxy还没收到无人机心跳信号

**检查**：
1. 无人机是否开机？
2. 遥控器网线是否连接？
3. MAVProxy窗口是否显示 `link 1 down`？

**解决**：
- 检查数传端口是否真的是8080（可能是8081）
- 如果是8081，在MAVProxy窗口按 `Ctrl+C`，重新运行：
  ```bash
  python -m MAVProxy.mavproxy --master=udp:0.0.0.0:8081 --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
  ```

---

### Q2：和QGC冲突？

**原因**：一个端口同时只能被一个程序监听

**解决方案1**：关闭QGC，用本系统（推荐）

**解决方案2**：同时使用
1. 关闭QGC
2. 启动本系统（MAVProxy会占用8080）
3. 在QGC中设置连接到 **UDP 14550**（从MAVProxy接收）

---




#
---

## 📊 数据说明

### 重点数据（🎯标识）

1. **离地高度**：
   - **测距仪**：0-10米范围，厘米级精度（优先）
   - **GPS高度**：无限高度，米级精度（备用）

2. **地面速度**：
   - 水平方向移动速度
   - 计算公式：`sqrt(vx² + vy²)`

### 所有可用数据

| 类别 | 数据项 | 单位 |
|------|--------|------|
| **位置** | GPS纬度/经度 | 度 |
|  | 海拔高度 | 米 |
|  | 离地高度（测距仪/GPS） | 米 |
| **速度** | 地面速度（水平） | m/s |
|  | 垂直速度 | m/s |
|  | X/Y/Z轴速度 | m/s |
| **姿态** | 横滚角（Roll） | 度 |
|  | 俯仰角（Pitch） | 度 |
|  | 航向角（Yaw） | 度 |
| **电池** | 电压 | V |
|  | 电流 | A |
|  | 剩余电量 | % |
| **GPS** | 定位类型 | 0=无, 3=3D, 4=RTK |
|  | 卫星数量 | 颗 |
| **状态** | 飞行模式 | MANUAL/STABILIZE/AUTO等 |
|  | 电机状态 | 已解锁/已锁定 |

---

## 🛠️ 修改与扩展

### 添加新数据

1. **修改后端**：`drone_bridge.py`
   ```python
   elif msg_type == '新消息类型':
       drone_data['新字段'] = msg.数据
   ```

2. **修改前端**：`src/components/Home/DroneDataPanel.vue`
   ```vue
   <div class="data-row">
     <span class="label">新数据:</span>
     <span class="value">{{ droneData.新字段 }}</span>
   </div>
   ```

3. **重启服务**：
   - Python桥接：`Ctrl+C` → `python drone_bridge.py`
   - 前端：刷新浏览器

### 数据来源

所有数据来自MAVLink协议：
- 官方文档：https://mavlink.io/en/messages/common.html
- ArduPilot支持的消息类型查看：在MAVProxy输入 `status`

---

## 📱 环境要求

### Python环境（conda）
```bash
conda activate drone_f410
pip list | grep -E "pymavlink|websockets|MAVProxy"
```

**应该看到**：
- pymavlink 2.4.49
- websockets 15.0+
- MAVProxy 1.8.74

### Node.js环境
```bash
node -v  # v16+
npm -v   # v8+
```

---

## ✅ 成功检查清单

连接成功后应该看到：

- [ ] MAVProxy窗口显示：`Received 512 parameters`, `Flight Mode: MANUAL`
- [ ] Python桥接显示：`✅ 连接到系统ID: 1`
- [ ] 浏览器左侧面板显示：**已连接**（绿色）
- [ ] 离地高度显示：**0.09 m**（或其他非0值）
- [ ] 电池电压显示：**14.9 V**（或实际电压）
- [ ] 姿态角实时变化（晃动无人机会看到数字变化）
- [ ] 更新时间每秒刷新

---

## 📞 技术支持

**问题排查顺序**：
1. 检查无人机是否开机
2. 检查MAVProxy窗口是否显示 `link 1 down`
3. 检查Python桥接是否显示 `系统ID: 0`（说明没连上）
4. 检查端口是否正确（8080 vs 8081）
5. 尝试关闭QGC，避免端口冲突

**日志位置**：
- MAVProxy：终端窗口输出
- Python桥接：终端窗口输出
- 前端：浏览器 F12 → Console

---

## 🎉 快速测试

### 1分钟快速测试流程

1. ✅ 双击 `start_drone_system.bat`
2. ✅ 等待15秒
3. ✅ 访问 `http://localhost:5173`
4. ✅ 查看左侧数据面板
5. ✅ 晃动无人机，观察姿态角变化

**测试通过标准**：能看到实时数据更新

---

## 📚 学习资源

- **Vue 3文档**：https://cn.vuejs.org/
- **Cesium地图**：https://cesium.com/learn/
- **MAVLink协议**：https://mavlink.io/en/
- **ArduPilot文档**：https://ardupilot.org/copter/

---

**最后更新**：2025年10月28日  
**版本**：v1.0  
**作者**：大创项目组

