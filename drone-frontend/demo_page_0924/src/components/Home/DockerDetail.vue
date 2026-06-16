<template>
  <div class="device-detail">
    <div class="header">
      <h3>{{ docker?.name }}</h3>
      <span class="top-status" :class="{
        'status-disconnected': docker?.status === '异常',
        'status-connected': docker?.status === '空闲',
        'status-charging': docker?.status === '充电中'
      }">
        {{ docker?.status || '未知' }}
      </span>
      <el-button size="small" circle @click="$emit('action', { type: 'close-detail' })" class="close-btn">
        <el-icon>
          <Close />
        </el-icon>
      </el-button>
    </div>

    <!-- 关联的无人机 -->
    <div v-if="associatedDrones.length">
      <div v-for="drone in associatedDrones" :key="drone.id" class="linked-drone">
        <div class="linked-drone-model">{{ drone.model }}</div>
        <div class="linked-drone-status">
          电量：{{ drone.battery }}%
        </div>
        <div class="takeoff-button" v-if="canTakeOff" @click="$emit('action', { type: 'takeoff', data: docker })">
          <span>一键起飞</span>
        </div>
      </div>
    </div>

    <div class="content">
      <!-- 实时视频模块 -->
      <div class="live-broadcast">
        <video ref="videoRef" controls autoplay muted style="width: 100%; height: 100%; object-fit: cover;"></video>
      </div>



      <!-- 环境信息 -->
      <div class="environment-section">
        <div class="environment-item">
          <span class="label">风速:</span>
          <span class="value">{{ docker?.windSpeed }} m/s</span>
        </div>
        <div class="environment-item">
          <span class="label">雨量:</span>
          <span class="value">{{ docker?.rainfall }} mm</span>
        </div>
        <div class="environment-item">
          <span class="label">舱内温度:</span>
          <span class="value">{{ docker?.temperature }} ℃</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch, ref } from 'vue'
import { Close } from '@element-plus/icons-vue'
import Hls from 'hls.js'

const props = defineProps({
  docker: {
    type: Object,
    required: true
  },
  devices: {
    type: Array,
    required: true
  }
})

const emit = defineEmits(['action'])

const videoRef = ref(null)
let hlsInstance = null

function initVideoStream(src) {
  const video = videoRef.value
  if (!video || !src) return

  if (hlsInstance) {
    hlsInstance.destroy()
    hlsInstance = null
  }

  video.src = ''
  video.load()

  if (Hls.isSupported()) {
    hlsInstance = new Hls()
    hlsInstance.loadSource(src)
    hlsInstance.attachMedia(video)
    hlsInstance.on(Hls.Events.ERROR, (event, data) => {
      console.error('HLS 错误:', data)
    })
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = src
    video.play().catch((e) => console.error('播放失败:', e))
  } else {
    console.warn('HLS 不支持，且浏览器不支持播放 .m3u8')
  }
}

// 初始化 & 响应 docker.videoStream 变化
onMounted(() => {
  initVideoStream(props.docker.videoStream)
})

watch(() => props.docker.videoStream, (newSrc) => {
  initVideoStream(newSrc)
})

const associatedDrones = computed(() => {
  if (!props.docker?.associatedDevices) return []
  return props.docker.associatedDevices
    .map(id => props.devices.find(d => d.id === id))
    .filter(Boolean)
})

const canTakeOff = computed(() =>
  associatedDrones.value.some(drone => drone.status === '待命' && drone.battery >= 10)
)
</script>


<style scoped>
.device-detail {
  width: 100%;
  max-width: 700px;
  background-color: black;
  border: 1px solid black;
  border-radius: 8px;
  color: #E0E0E0;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  padding: 0;
  margin: 0;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #2D2D3D;
  padding: 0;
}

.header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #FFFFFF;
  margin: 0 8px;
}

.top-status {
  font-size: 12px;
  border-radius: 6px;
  padding: 2px 6px;
  background-color: #b3b6b9;
  color: #606060;
  margin-left: auto;
  margin-right: 12px;
}

.status-disconnected {
  background-color: #a7706e;
  color: #c33838;
}

.status-connected {
  background-color: #8abc8a;
  color: green;
}

.status-charging {
  background-color: #FFD700;
  color: #333;
}

.close-btn {
  background-color: #ceced8;
  font-size: small;
  margin-right: 8px;
}

.content {
  padding: 0;
}

.live-broadcast {
  width: 100%;
  aspect-ratio: 16 / 9; 
  background-color: #2A2A3A;
  border-radius: 6px;
  margin: 0;
  overflow: hidden;
  position: relative;
}

.live-broadcast::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #606080;
  font-size: 14px;
}

.linked-drone {
  padding: 6px 0;
  border-bottom: 1px dashed #3a3a3a;
  font-size: 12px;
  color: #CCCCCC;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between; /* 左右分布 */
  gap: 6px; /* 控制间距 */
  margin: 8px 12px;
}

.linked-drone-name {
  font-weight: bold;
}

.linked-drone-model {
  font-size: 11px;
  color: #aaa;
  margin-top: 2px;
}

.linked-drone-status {
  color: #999;
  font-size: 11px;
  margin-top: 2px;
}

.takeoff-button {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 6px;
  color: #fff;
  background-color: #409EFF;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(64, 158, 255, 0.3);
  border: none;
  transition: background-color 0.3s ease;
  margin-top: 8px;
}

.takeoff-button:hover {
  background-color: #337ecc;
}

.environment-section {
  display: flex;
  justify-content: space-around;
  /* background: rgb(86, 15, 174); */
  border-radius: 6px;
  margin: 0;
  padding: 4px 0;
}

.environment-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #FFFFFF;
  font-weight: 500;
}

.label {
  font-size: 12px;
}

.value {
  font-size: 12px;
  font-weight: bold;
}
</style>
