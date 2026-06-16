<template>
  <div class="device-detail">
    <div class="header">
      <h3>{{ device?.name }}</h3>
      <!-- 型号 -->
          <div class="status-item">
            <span class="model-text">{{ device?.model }}</span>
          </div>
      <el-button size="small" circle @click="$emit('action', { type: 'close-detail' })" class="close-btn">
        <el-icon>
          <Close />
        </el-icon>
      </el-button>
    </div>

    <div class="content">
      <!-- 无人机状态区块 -->
      <div class="drone-status-section">
        <div class="status-indicators">
          <div class="top-status" :class="{
        'status-disconnected': device?.status === '工作中',
        'status-connected': device?.status === '空闲中'
      }">
        {{ device?.status || '未知' }}
    </div>
          
          <!-- 电池电量 -->
<!-- 电池电量 -->
<div class="status-item">
  <div class="battery-icon">
  <div
    class="battery-level"
    :style="{ width: device?.battery + '%' }"
    :class="getBatteryClass(device?.battery)"
  ></div>
  <span class="battery-percentage">{{ device?.battery }}%</span>
</div>

</div>



          <!--按钮 -->
          <div class="dispatch-button" @click="$emit('action', { type: 'enter-control-panel', data: device })">
            <span>控制面板</span>
          </div>

          <div class="dispatch-button" @click="$emit('action', { type: 'dispatch', data: device })">
            <span>立即调度</span>
          </div>
        </div>
      </div>

      <!-- 实时视频 -->
      <div class="live-broadcast">
        <video ref="videoRef" controls autoplay muted style="width: 100%; height: 100%; object-fit: cover;">
          <!-- 确保这里的 src 是相对路径，或者是公开的可访问路径 -->
          <source :src="device?.videoStream" type="video/mp4" />
          <!-- 如果浏览器不支持 MP4，显示备用消息 -->
          你的浏览器不支持播放此视频格式。
        </video>
      </div>

      <!-- 自定义内容 -->
      <div class="custom-content">
        <slot></slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Close } from '@element-plus/icons-vue';
import { onMounted, watch, ref } from 'vue';

const props = defineProps({
  device: {
    type: Object,
    required: true,
    validator: (device) =>
      ['id', 'name', 'status', 'battery', 'model', 'videoStream'].every((key) => key in device)
  }
});

const videoRef = ref(null);

const getBatteryClass = (battery) => {
  if (battery <= 20) return 'low';
  if (battery <= 60) return 'medium';
  return 'high'; // 默认返回绿色
};


onMounted(() => {
  const video = videoRef.value;
  const videoSource = props.device?.videoStream; // 获取视频路径

  if (video && videoSource) {
    video.src = videoSource;  // 设置视频源
    video.load();  // 重新加载视频
    video.play().catch((e) => console.error('播放失败:', e)); // 播放视频并捕获任何错误
  }
});

watch(() => props.device.videoStream, (newSrc) => {
  const video = videoRef.value;
  if (video && newSrc) {
    video.src = newSrc; // 更新视频源
    video.load();  // 重新加载视频
    video.play().catch((e) => console.error('播放失败:', e)); // 播放新的视频源
  }
});
</script>

<style scoped>
.device-detail {
  width: 100%;
  max-width: 480px;
  background-color: black;
  border: 1px solid black;
  border-radius: 8px;
  color: #e0e0e0;
  margin: 0;
  padding: 0;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #2d2d3d;
  padding: 4px 8px;
}

.header h3 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #ffffff;
}

.top-status {
  font-size: 11px;
  background-color: #b3b6b9;
  color: #606060;
  border-radius: 6px;
  padding: 2px 6px;
  margin-left: auto;
  margin-right: 8px;
}

.status-disconnected {
  background-color: #52482c;
  color: white;
}

.status-connected {
  background-color: #8abc8a;
  color: green;
}

.close-btn {
  background-color: #464649;   /* 默认背景色 */
  color: #fff;                 /* 图标颜色 */
  border: none;                /* 去掉边框 */
  transition: background-color 0.3s ease; /* 鼠标移动时渐变 */
}

/* 鼠标悬停 */
.close-btn:hover {
  background-color: #dba541;  /* 悬停时背景，比如红色 */
  color: #fff;                /* 图标保持白色 */
}

.content {
  padding: 0;
}

.drone-status-section {
  margin: 8px 12px;
}

.status-indicators {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 50px;
}

/* 父容器居中 */
.status-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 12px;
  justify-content: center; /* 居中对齐 */
  margin-top: 0px; /* 可选：调整上边距 */
}

/* 电池图标外框保持原样 */
.battery-icon {
  width: 35px;
  height: 15px;
  border: 1.5px solid #fff;
  border-radius: 4px;
  position: relative;
  display: flex;
  justify-content: flex-start;
}


/* 电池内部的剩余电量条 */
.battery-level {
  height: 100%;
  background-color: #4CAF50; /* 电池内填充颜色，默认为绿色 */
  border-radius: 4px 0 0 4px;  /* 让电量条的左边圆滑 */
  transition: width 0.5s ease;  /* 平滑过渡 */
  position: relative;  /* 使文字定位到电池内部 */
  display: flex;
  justify-content: center;
  align-items: center;
}

.battery-percentage {
   position: absolute;   /* 绝对定位 */
  top: 30%;
  left: 50%;
  transform: translate(-50%, -50%); /* 居中对齐 */
  font-size: 10px !important;
  color: #fff;
  font-weight: bold;
  white-space: nowrap;
  pointer-events: none; /* 保证点击事件不受影响 */
}



/* 电池电量条 - 不同电量显示不同颜色 */
.battery-level.low {
  background-color: #F44336;  /* 红色表示电量低 */
}

.battery-level.medium {
  background-color: #FFEB3B;  /* 黄色表示电量中等 */
}

.battery-level.high {
  background-color: #4CAF50;  /* 绿色表示电量充足 */
}



.model-text,
.battery-percentage {
  font-size: 13px;
  color: #ffffff;
  font-weight: bold;
  margin-top: 2px;
}

.dispatch-button {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 6px;
  color: #fff;
  background-color: #233542;
  cursor: pointer;
  border: none;
  transition: background-color 0.3s ease;
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.3);
  white-space: nowrap;
}

.dispatch-button:hover {
  background-color: #6295cc;
}

.live-broadcast {
  width: 100%;
  aspect-ratio: 16 / 9;
  background-color: #2a2a3a;
  border-radius: 6px;
  margin: 0;
  overflow: hidden;
  position: relative;
}

.live-broadcast::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #606080;
  font-size: 14px;
}

.custom-content {
  margin-top: 0px;
}
</style>
