#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F410无人机 WebSocket 桥接服务
功能：接收MAVLink数据，通过WebSocket实时推送到Vue前端
"""

import asyncio
import json
import time
from datetime import datetime
from pymavlink import mavutil
from websockets.server import serve

# ==================== 配置区 ====================
MAVLINK_CONNECTION = 'udpin:127.0.0.1:14551'  # 从MAVProxy接收数据
WEBSOCKET_PORT = 8765                          # WebSocket端口
# ================================================

# 全局变量
drone_data = {
    'connected': False,
    'heartbeat': None,
    'position': {'lat': 0, 'lon': 0, 'alt': 0, 'relative_alt': 0, 'heading': 0},  # 添加航向
    'attitude': {'roll': 0, 'pitch': 0, 'yaw': 0},
    'battery': {'voltage': 0, 'current': 0, 'remaining': 100},
    'gps': {'fix_type': 0, 'satellites': 0},
    'mode': 'UNKNOWN',
    'armed': False,
    'velocity': {'vx': 0, 'vy': 0, 'vz': 0},
    'ground_speed': 0,  # 🎯 地面速度
    'rangefinder': {'distance': 0, 'available': False},  # 🎯 激光测距仪（更精确的离地高度）
    'last_update': None
}

clients = set()  # 已连接的WebSocket客户端
master = None


def connect_drone():
    """连接无人机"""
    global master
    print(f"\n[连接] 正在连接到 {MAVLINK_CONNECTION}...")
    try:
        master = mavutil.mavlink_connection(MAVLINK_CONNECTION)
        print("[等待] 等待心跳信号...")
        master.wait_heartbeat(timeout=10)
        drone_data['connected'] = True
        print(f"✅ [成功] 连接到系统ID: {master.target_system}, 组件ID: {master.target_component}")
        return True
    except Exception as e:
        print(f"❌ [错误] 连接失败: {e}")
        drone_data['connected'] = False
        return False


def process_mavlink_messages():
    """处理MAVLink消息（后台线程）"""
    global master, drone_data
    
    if not master:
        return
    
    # 非阻塞接收消息
    msg = master.recv_match(blocking=False)
    if not msg:
        return
    
    msg_type = msg.get_type()
    drone_data['last_update'] = datetime.now().isoformat()
    
    # 解析不同类型的消息
    if msg_type == 'HEARTBEAT':
        drone_data['heartbeat'] = time.time()
        drone_data['mode'] = mavutil.mode_string_v10(msg)
        drone_data['armed'] = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
        
    elif msg_type == 'GLOBAL_POSITION_INT':
        drone_data['position'] = {
            'lat': msg.lat / 1e7,
            'lon': msg.lon / 1e7,
            'alt': msg.alt / 1000.0,  # 毫米转米
            'relative_alt': msg.relative_alt / 1000.0,  # 🎯 相对地面高度
            'heading': msg.hdg / 100.0  # 航向角（度）
        }
        drone_data['velocity'] = {
            'vx': msg.vx / 100.0,  # cm/s 转 m/s
            'vy': msg.vy / 100.0,
            'vz': msg.vz / 100.0
        }
        # 添加地面速度
        import math
        drone_data['ground_speed'] = math.sqrt(
            (msg.vx/100.0)**2 + (msg.vy/100.0)**2
        )
        
    elif msg_type == 'ATTITUDE':
        import math
        drone_data['attitude'] = {
            'roll': math.degrees(msg.roll),
            'pitch': math.degrees(msg.pitch),
            'yaw': math.degrees(msg.yaw)
        }
        
    elif msg_type == 'SYS_STATUS':
        drone_data['battery'] = {
            'voltage': msg.voltage_battery / 1000.0,  # mV 转 V
            'current': msg.current_battery / 100.0,   # cA 转 A
            'remaining': msg.battery_remaining
        }
        
    elif msg_type == 'GPS_RAW_INT':
        drone_data['gps'] = {
            'fix_type': msg.fix_type,
            'satellites': msg.satellites_visible
        }
    
    # 🎯 激光测距仪数据（更精确的离地高度）
    elif msg_type == 'RANGEFINDER':
        drone_data['rangefinder'] = {
            'distance': msg.distance,  # 测距仪距离（米）
            'available': True
        }
    
    # 🎯 距离传感器（备用）
    elif msg_type == 'DISTANCE_SENSOR':
        if msg.orientation == 25:  # 朝下的传感器
            drone_data['rangefinder'] = {
                'distance': msg.current_distance / 100.0,  # cm转m
                'available': True
            }


async def websocket_handler(websocket):
    """处理WebSocket连接"""
    client_addr = websocket.remote_address
    print(f"[WebSocket] 新客户端连接: {client_addr}")
    clients.add(websocket)
    
    try:
        # 发送欢迎消息
        await websocket.send(json.dumps({
            'type': 'welcome',
            'message': 'F410桥接服务已连接',
            'timestamp': datetime.now().isoformat()
        }))
        
        # 保持连接，接收客户端消息（如果有的话）
        async for message in websocket:
            # 可以在这里处理前端发来的指令
            print(f"[收到消息] {client_addr}: {message}")
            
    except Exception as e:
        print(f"[WebSocket] 客户端 {client_addr} 异常: {e}")
    finally:
        clients.remove(websocket)
        print(f"[WebSocket] 客户端断开: {client_addr}")


async def broadcast_drone_data():
    """定期广播无人机数据到所有客户端"""
    while True:
        if clients:
            message = json.dumps({
                'type': 'drone_data',
                'data': drone_data,
                'timestamp': datetime.now().isoformat()
            })
            
            # 发送给所有连接的客户端
            disconnected = set()
            for client in clients:
                try:
                    await client.send(message)
                except Exception:
                    disconnected.add(client)
            
            # 移除断开的客户端
            clients.difference_update(disconnected)
        
        await asyncio.sleep(0.1)  # 10Hz更新频率


async def mavlink_loop():
    """MAVLink数据接收循环"""
    while True:
        process_mavlink_messages()
        await asyncio.sleep(0.01)  # 100Hz检查频率


async def main():
    """主程序"""
    print("=" * 60)
    print("      F410无人机 WebSocket 桥接服务")
    print("=" * 60)
    print(f"MAVLink连接: {MAVLINK_CONNECTION}")
    print(f"WebSocket端口: {WEBSOCKET_PORT}")
    print("=" * 60)
    
    # 连接无人机
    if not connect_drone():
        print("\n❌ 无法连接到无人机，请检查：")
        print("  1. MAVProxy是否正在运行？")
        print("  2. 端口14551是否正确？")
        print("  3. 无人机数传是否连接？")
        return
    
    print(f"\n✅ 桥接服务准备就绪!")
    print(f"📡 前端请连接: ws://localhost:{WEBSOCKET_PORT}")
    print("=" * 60)
    
    # 启动WebSocket服务器
    async with serve(websocket_handler, "0.0.0.0", WEBSOCKET_PORT):
        # 同时运行MAVLink接收和数据广播
        await asyncio.gather(
            mavlink_loop(),
            broadcast_drone_data()
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[退出] 服务已停止")
    except Exception as e:
        print(f"\n❌ [错误] {e}")
        import traceback
        traceback.print_exc()

