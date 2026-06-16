<template>
  <div class="drone-data-panel">
    <!-- 连接状态 -->
    <div class="panel-header">
      <h3>🚁 无人机实时数据</h3>
      <el-tag :type="connectionStatus.type" size="small">
        {{ connectionStatus.text }}
      </el-tag>
    </div>

    <!-- 关键数据显示 -->
    <div class="data-section" v-if="isConnected">
      
      <!-- 飞行状态 -->
      <div class="data-group">
        <div class="group-title">飞行状态</div>
        <div class="data-row">
          <span class="label">模式:</span>
          <el-tag size="small" :type="droneData.armed ? 'danger' : 'info'">
            {{ droneData.mode }}
          </el-tag>
        </div>
        <div class="data-row">
          <span class="label">电机:</span>
          <el-tag size="small" :type="droneData.armed ? 'danger' : 'success'">
            {{ droneData.armed ? '解锁' : '锁定' }}
          </el-tag>
        </div>
      </div>

      <!-- 🎯 关键：离地高度 -->
      <div class="data-group highlight">
        <div class="group-title">🎯 离地高度</div>
        <div class="data-row" v-if="droneData.rangefinder && droneData.rangefinder.distance > 0">
          <span class="label">测距仪:</span>
          <span class="value primary">{{ droneData.rangefinder.distance.toFixed(2) }} m</span>
        </div>
        <div class="data-row" v-else>
          <span class="label">GPS高度:</span>
          <span class="value">{{ droneData.position.relative_alt.toFixed(2) }} m</span>
        </div>
      </div>

      <!-- GPS位置 -->
      <div class="data-group">
        <div class="group-title">GPS位置</div>
        <div class="data-row">
          <span class="label">定位:</span>
          <el-tag size="small" :type="getGpsFixType().type">
            {{ getGpsFixType().text }}
          </el-tag>
        </div>
        <div class="data-row">
          <span class="label">卫星:</span>
          <span class="value">{{ droneData.gps.satellites }} 颗</span>
        </div>
        <div class="data-row" v-if="droneData.position.lat !== 0">
          <span class="label">纬度:</span>
          <span class="value small">{{ droneData.position.lat.toFixed(6) }}°</span>
        </div>
        <div class="data-row" v-if="droneData.position.lon !== 0">
          <span class="label">经度:</span>
          <span class="value small">{{ droneData.position.lon.toFixed(6) }}°</span>
        </div>
      </div>

      <!-- 🎯 关键：速度 -->
      <div class="data-group highlight">
        <div class="group-title">🎯 飞行速度</div>
        <div class="data-row">
          <span class="label">地面速度:</span>
          <span class="value primary">{{ droneData.ground_speed ? droneData.ground_speed.toFixed(1) : '0.0' }} m/s</span>
        </div>
        <div class="data-row">
          <span class="label">垂直速度:</span>
          <span class="value">{{ droneData.velocity.vz.toFixed(1) }} m/s</span>
        </div>
      </div>

      <!-- 姿态角 -->
      <div class="data-group">
        <div class="group-title">姿态角度</div>
        <div class="data-row">
          <span class="label">横滚:</span>
          <span class="value">{{ droneData.attitude.roll.toFixed(1) }}°</span>
        </div>
        <div class="data-row">
          <span class="label">俯仰:</span>
          <span class="value">{{ droneData.attitude.pitch.toFixed(1) }}°</span>
        </div>
        <div class="data-row">
          <span class="label">航向:</span>
          <span class="value">{{ droneData.attitude.yaw.toFixed(1) }}°</span>
        </div>
      </div>

      <!-- 电池 -->
      <div class="data-group">
        <div class="group-title">电池状态</div>
        <div class="data-row">
          <span class="label">电压:</span>
          <span class="value">{{ droneData.battery.voltage.toFixed(1) }} V</span>
        </div>
        <div class="data-row">
          <span class="label">电流:</span>
          <span class="value">{{ droneData.battery.current.toFixed(2) }} A</span>
        </div>
        <div class="data-row">
          <span class="label">剩余:</span>
          <span class="value" :style="{color: getBatteryColor()}">
            {{ droneData.battery.remaining }}%
          </span>
        </div>
      </div>

      <!-- 最后更新时间 -->
      <div class="last-update" v-if="droneData.last_update">
        更新: {{ formatTime(droneData.last_update) }}
      </div>
    </div>

    <!-- 未连接状态 -->
    <div v-else class="no-connection">
      <p>等待无人机连接...</p>
      <el-button type="primary" size="small" @click="connectWebSocket">
        尝试连接
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

const WEBSOCKET_URL = 'ws://localhost:8765'

// WebSocket连接
let ws = null
const isConnected = ref(false)

// 无人机数据
const droneData = ref({
  connected: false,
  position: { lat: 0, lon: 0, alt: 0, relative_alt: 0, heading: 0 },
  attitude: { roll: 0, pitch: 0, yaw: 0 },
  battery: { voltage: 0, current: 0, remaining: 100 },
  gps: { fix_type: 0, satellites: 0 },
  mode: 'UNKNOWN',
  armed: false,
  velocity: { vx: 0, vy: 0, vz: 0 },
  ground_speed: 0,
  rangefinder: { distance: 0, available: false },
  last_update: null
})

// 连接状态
const connectionStatus = computed(() => {
  if (isConnected.value && droneData.value.connected) {
    return { type: 'success', text: '已连接' }
  } else if (isConnected.value) {
    return { type: 'warning', text: '等待数据' }
  } else {
    return { type: 'info', text: '未连接' }
  }
})

// 连接WebSocket
function connectWebSocket() {
  if (ws) return
  
  try {
    ws = new WebSocket(WEBSOCKET_URL)
    
    ws.onopen = () => {
      isConnected.value = true
      console.log('✅ 无人机数据面板已连接')
    }
    
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'drone_data') {
          droneData.value = message.data
        }
      } catch (error) {
        console.error('解析消息失败:', error)
      }
    }
    
    ws.onerror = (error) => {
      console.error('WebSocket错误:', error)
    }
    
    ws.onclose = () => {
      isConnected.value = false
      ws = null
      console.log('WebSocket已断开，5秒后重连...')
      setTimeout(connectWebSocket, 5000)
    }
  } catch (error) {
    console.error('连接失败:', error)
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

// GPS定位类型
function getGpsFixType() {
  const fixType = droneData.value.gps.fix_type
  if (fixType === 0) return { type: 'danger', text: '无定位' }
  if (fixType === 1) return { type: 'warning', text: '无GPS' }
  if (fixType === 2) return { type: 'warning', text: '2D' }
  if (fixType === 3) return { type: 'success', text: '3D' }
  if (fixType >= 4) return { type: 'success', text: 'RTK' }
  return { type: 'info', text: '未知' }
}

// 电池颜色
function getBatteryColor() {
  const remaining = droneData.value.battery.remaining
  if (remaining > 60) return '#67C23A'
  if (remaining > 30) return '#E6A23C'
  return '#F56C6C'
}

// 格式化时间
function formatTime(isoString) {
  if (!isoString) return '--'
  const date = new Date(isoString)
  return date.toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit' 
  })
}

// 生命周期
onMounted(() => {
  // 自动连接
  connectWebSocket()
})

onUnmounted(() => {
  disconnectWebSocket()
})
</script>

<style scoped>
.drone-data-panel {
  position: fixed;
  left: 170px;  /* 🎯 调整：留出左侧菜单栏空间（150px + 20px间距） */
  top: 80px;
  width: 280px;
  max-height: calc(100vh - 100px);
  background: rgba(30, 30, 45, 0.95);
  border-radius: 8px;
  padding: 15px;
  color: #fff;
  font-size: 13px;
  overflow-y: auto;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  backdrop-filter: blur(10px);
}

/* 滚动条样式 */
.drone-data-panel::-webkit-scrollbar {
  width: 6px;
}

.drone-data-panel::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 3px;
}

.drone-data-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}

/* 头部 */
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: bold;
}

/* 数据组 */
.data-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.data-group {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  padding: 10px;
}

.data-group.highlight {
  background: rgba(64, 158, 255, 0.1);
  border-left: 3px solid #409EFF;
}

.group-title {
  font-size: 12px;
  font-weight: bold;
  color: #409EFF;
  margin-bottom: 8px;
  text-transform: uppercase;
}

.data-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.data-row:last-child {
  margin-bottom: 0;
}

.data-row .label {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
}

.data-row .value {
  color: #fff;
  font-weight: 500;
  font-family: 'Courier New', monospace;
}

.data-row .value.small {
  font-size: 11px;
}

.data-row .value.primary {
  color: #409EFF;
  font-weight: bold;
  font-size: 14px;
}

/* 最后更新时间 */
.last-update {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  text-align: center;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
}

/* 未连接状态 */
.no-connection {
  text-align: center;
  padding: 20px;
  color: rgba(255, 255, 255, 0.6);
}

.no-connection p {
  margin-bottom: 15px;
}
</style>

