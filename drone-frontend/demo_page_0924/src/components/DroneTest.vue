<template>
  <div class="drone-test-container">
    <el-card class="header-card">
      <template #header>
        <div class="card-header">
          <h2>🚁 F410无人机实时数据测试</h2>
          <el-tag :type="connectionStatus.type" size="large">
            {{ connectionStatus.text }}
          </el-tag>
        </div>
      </template>
      
      <div class="connection-info">
        <el-space>
          <el-button 
            :type="isConnected ? 'danger' : 'primary'" 
            @click="toggleConnection"
            :loading="isConnecting"
          >
            {{ isConnected ? '断开连接' : '连接无人机' }}
          </el-button>
          <span>WebSocket地址: ws://localhost:8765</span>
          <span v-if="droneData.last_update" class="last-update">
            最后更新: {{ formatTime(droneData.last_update) }}
          </span>
        </el-space>
      </div>
    </el-card>

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- 基础状态 -->
      <el-col :span="8">
        <el-card>
          <template #header>
            <h3>📡 基础状态</h3>
          </template>
          <div class="data-item">
            <span class="label">飞行模式:</span>
            <el-tag :type="droneData.armed ? 'danger' : 'info'">
              {{ droneData.mode }}
            </el-tag>
          </div>
          <div class="data-item">
            <span class="label">电机状态:</span>
            <el-tag :type="droneData.armed ? 'danger' : 'success'">
              {{ droneData.armed ? '已解锁 ⚠️' : '已锁定 ✓' }}
            </el-tag>
          </div>
          <div class="data-item">
            <span class="label">GPS卫星:</span>
            <span class="value">{{ droneData.gps.satellites }} 颗</span>
          </div>
          <div class="data-item">
            <span class="label">GPS定位:</span>
            <el-tag :type="getGpsFixType().type">
              {{ getGpsFixType().text }}
            </el-tag>
          </div>
        </el-card>
      </el-col>

      <!-- GPS位置 -->
      <el-col :span="8">
        <el-card>
          <template #header>
            <h3>🌍 GPS位置</h3>
          </template>
          <div class="data-item">
            <span class="label">纬度:</span>
            <span class="value">{{ droneData.position.lat.toFixed(7) }}°</span>
          </div>
          <div class="data-item">
            <span class="label">经度:</span>
            <span class="value">{{ droneData.position.lon.toFixed(7) }}°</span>
          </div>
          <div class="data-item">
            <span class="label">海拔高度:</span>
            <span class="value">{{ droneData.position.alt.toFixed(2) }} m</span>
          </div>
          <div class="data-item">
            <span class="label">相对高度 (GPS):</span>
            <span class="value">{{ droneData.position.relative_alt.toFixed(2) }} m</span>
          </div>
          <div class="data-item" v-if="droneData.rangefinder">
            <span class="label">🎯 离地距离 (测距仪):</span>
            <span class="value" :style="{color: droneData.rangefinder.distance > 0 ? '#67C23A' : '#909399'}">
              {{ droneData.rangefinder.distance.toFixed(3) }} m
            </span>
          </div>
        </el-card>
      </el-col>

      <!-- 电池状态 -->
      <el-col :span="8">
        <el-card>
          <template #header>
            <h3>🔋 电池状态</h3>
          </template>
          <div class="data-item">
            <span class="label">电压:</span>
            <span class="value">{{ droneData.battery.voltage.toFixed(2) }} V</span>
          </div>
          <div class="data-item">
            <span class="label">电流:</span>
            <span class="value">{{ droneData.battery.current.toFixed(2) }} A</span>
          </div>
          <div class="data-item">
            <span class="label">剩余电量:</span>
            <el-progress 
              :percentage="droneData.battery.remaining" 
              :color="getBatteryColor()"
              :stroke-width="20"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- 姿态角 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <h3>📐 姿态角度</h3>
          </template>
          <div class="data-item">
            <span class="label">横滚角 (Roll):</span>
            <span class="value">{{ droneData.attitude.roll.toFixed(2) }}°</span>
            <el-progress 
              :percentage="Math.abs(droneData.attitude.roll)"
              :color="Math.abs(droneData.attitude.roll) > 30 ? '#F56C6C' : '#67C23A'"
            />
          </div>
          <div class="data-item">
            <span class="label">俯仰角 (Pitch):</span>
            <span class="value">{{ droneData.attitude.pitch.toFixed(2) }}°</span>
            <el-progress 
              :percentage="Math.abs(droneData.attitude.pitch)"
              :color="Math.abs(droneData.attitude.pitch) > 30 ? '#F56C6C' : '#67C23A'"
            />
          </div>
          <div class="data-item">
            <span class="label">航向角 (Yaw):</span>
            <span class="value">{{ droneData.attitude.yaw.toFixed(2) }}°</span>
          </div>
        </el-card>
      </el-col>

      <!-- 速度 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <h3>💨 速度信息</h3>
          </template>
          <div class="data-item">
            <span class="label">X轴速度:</span>
            <span class="value">{{ droneData.velocity.vx.toFixed(2) }} m/s</span>
          </div>
          <div class="data-item">
            <span class="label">Y轴速度:</span>
            <span class="value">{{ droneData.velocity.vy.toFixed(2) }} m/s</span>
          </div>
          <div class="data-item">
            <span class="label">Z轴速度 (垂直):</span>
            <span class="value">{{ droneData.velocity.vz.toFixed(2) }} m/s</span>
          </div>
          <div class="data-item">
            <span class="label">🎯 地面速度 (水平):</span>
            <span class="value" style="color: #409EFF; font-weight: bold;">
              {{ droneData.ground_speed ? droneData.ground_speed.toFixed(2) : '0.00' }} m/s
            </span>
          </div>
          <div class="data-item">
            <span class="label">总速度 (3D):</span>
            <span class="value">{{ getTotalSpeed() }} m/s</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 原始数据 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <h3>📊 原始JSON数据</h3>
      </template>
      <pre class="json-data">{{ JSON.stringify(droneData, null, 2) }}</pre>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

const WEBSOCKET_URL = 'ws://localhost:8765'

// WebSocket连接
let ws = null
const isConnected = ref(false)
const isConnecting = ref(false)

// 无人机数据
const droneData = ref({
  connected: false,
  heartbeat: null,
  position: { lat: 0, lon: 0, alt: 0, relative_alt: 0 },
  attitude: { roll: 0, pitch: 0, yaw: 0 },
  battery: { voltage: 0, current: 0, remaining: 100 },
  gps: { fix_type: 0, satellites: 0 },
  mode: 'UNKNOWN',
  armed: false,
  velocity: { vx: 0, vy: 0, vz: 0 },
  last_update: null
})

// 连接状态
const connectionStatus = computed(() => {
  if (isConnected.value && droneData.value.connected) {
    return { type: 'success', text: '✅ 已连接到无人机' }
  } else if (isConnected.value && !droneData.value.connected) {
    return { type: 'warning', text: '⚠️ WebSocket已连接，等待无人机数据' }
  } else {
    return { type: 'info', text: '⭕ 未连接' }
  }
})

// 连接WebSocket
function connectWebSocket() {
  if (ws) return
  
  isConnecting.value = true
  console.log(`连接到 ${WEBSOCKET_URL}...`)
  
  try {
    ws = new WebSocket(WEBSOCKET_URL)
    
    ws.onopen = () => {
      isConnected.value = true
      isConnecting.value = false
      ElMessage.success('WebSocket连接成功')
      console.log('✅ WebSocket已连接')
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        
        if (message.type === 'welcome') {
          console.log('收到欢迎消息:', message.message)
        } else if (message.type === 'drone_data') {
          droneData.value = message.data
        }
      } catch (error) {
        console.error('解析消息失败:', error)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket错误:', error)
      ElMessage.error('WebSocket连接错误')
      isConnecting.value = false
    }
    
    ws.onclose = () => {
      isConnected.value = false
      isConnecting.value = false
      ws = null
      console.log('WebSocket已断开')
      ElMessage.warning('WebSocket连接已断开')
    }
  } catch (error) {
    console.error('连接失败:', error)
    ElMessage.error('无法创建WebSocket连接')
    isConnecting.value = false
  }
}

// 断开连接
function disconnectWebSocket() {
  if (ws) {
    ws.close()
    ws = null
    isConnected.value = false
  }
}

// 切换连接
function toggleConnection() {
  if (isConnected.value) {
    disconnectWebSocket()
  } else {
    connectWebSocket()
  }
}

// GPS定位类型
function getGpsFixType() {
  const fixType = droneData.value.gps.fix_type
  if (fixType === 0) return { type: 'danger', text: '无定位' }
  if (fixType === 1) return { type: 'warning', text: '无GPS' }
  if (fixType === 2) return { type: 'warning', text: '2D定位' }
  if (fixType === 3) return { type: 'success', text: '3D定位' }
  if (fixType >= 4) return { type: 'success', text: 'RTK定位' }
  return { type: 'info', text: '未知' }
}

// 电池颜色
function getBatteryColor() {
  const remaining = droneData.value.battery.remaining
  if (remaining > 60) return '#67C23A'
  if (remaining > 30) return '#E6A23C'
  return '#F56C6C'
}

// 计算总速度
function getTotalSpeed() {
  const { vx, vy, vz } = droneData.value.velocity
  return Math.sqrt(vx * vx + vy * vy + vz * vz).toFixed(2)
}

// 格式化时间
function formatTime(isoString) {
  if (!isoString) return '--'
  const date = new Date(isoString)
  return date.toLocaleTimeString('zh-CN')
}

// 生命周期
onMounted(() => {
  console.log('DroneTest组件已挂载')
  // 可以自动连接
  // connectWebSocket()
})

onUnmounted(() => {
  disconnectWebSocket()
})
</script>

<style scoped>
.drone-test-container {
  padding: 20px;
  background: #f5f7fa;
  min-height: 100vh;
}

.header-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h2 {
  margin: 0;
  font-size: 24px;
}

.connection-info {
  margin-top: 10px;
}

.last-update {
  color: #909399;
  font-size: 14px;
}

.data-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding: 10px;
  background: #f9fafc;
  border-radius: 4px;
}

.data-item .label {
  font-weight: bold;
  color: #606266;
  min-width: 120px;
}

.data-item .value {
  font-size: 16px;
  color: #303133;
  font-family: 'Courier New', monospace;
}

.json-data {
  background: #2c3e50;
  color: #42b983;
  padding: 20px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 14px;
  line-height: 1.6;
  max-height: 500px;
  overflow-y: auto;
}

:deep(.el-card__header) {
  background: #409eff;
  color: white;
}

:deep(.el-card__header h3) {
  margin: 0;
  font-size: 18px;
}
</style>

