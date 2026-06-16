<template>
  <div class="live-broadcast">
    <video ref="videoRef" controls autoplay muted style="width: 100%; height: 100%; object-fit: cover;">
      <!-- 根据视频流格式决定类型 -->
      <source :src="videoSource" :type="videoType" />
    </video>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import Hls from 'hls.js';

const props = defineProps({
  device: {
    type: Object,
    required: true,
  },
});

const videoRef = ref(null);
let hlsInstance = null;

// 计算视频源和类型
const videoSource = computed(() => {
  return props.device?.videoStream || '';
});

const videoType = computed(() => {
  // 如果是 .m3u8 文件，使用 HLS.js
  if (videoSource.value.endsWith('.m3u8')) {
    return 'application/x-mpegURL';
  }
  // 否则默认为 MP4 格式
  return 'video/mp4';
});

// 初始化视频流
onMounted(() => {
  const video = videoRef.value;
  const videoSrc = videoSource.value;

  if (!video || !videoSrc) return;

  if (hlsInstance) {
    hlsInstance.destroy();
    hlsInstance = null;
  }

  // 如果是 HLS 流，使用 HLS.js 处理
  if (videoType.value === 'application/x-mpegURL' && Hls.isSupported()) {
    hlsInstance = new Hls();
    hlsInstance.loadSource(videoSrc);
    hlsInstance.attachMedia(video);
    hlsInstance.on(Hls.Events.ERROR, (event, data) => {
      console.error('HLS 错误:', data);
    });
  } else if (videoType.value === 'video/mp4') {
    // 如果是 MP4 文件，直接播放
    video.src = videoSrc;
    video.play().catch((e) => console.error('播放失败:', e));
  } else {
    console.warn('不支持的视频类型');
  }
});
</script>

<style scoped>
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
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #606080;
  font-size: 14px;
}
</style>
