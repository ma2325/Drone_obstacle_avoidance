<template>
  <div class="docker-video-container">
    <video 
      ref="videoRef" 
      controls 
      autoplay 
      muted 
      style="width: 100%; height: 100%; object-fit: cover;"
    >
      <source :src="docker.videoStream" type="application/x-mpegURL" />
    </video>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import Hls from 'hls.js'

const props = defineProps({
  docker: {
    type: Object,
    required: true
  }
})

const videoRef = ref(null)
let hls = null

const initVideo = () => {
  const video = videoRef.value
  if (!video || !props.docker?.videoStream) return

  // 清除旧实例
  if (hls) {
    hls.destroy()
    hls = null
  }

  if (Hls.isSupported()) {
    hls = new Hls()
    hls.loadSource(props.docker.videoStream)
    hls.attachMedia(video)
    hls.on(Hls.Events.ERROR, (event, data) => {
      console.error('HLS Error:', data)
    })
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = props.docker.videoStream
    video.play().catch(e => console.error('Play failed:', e))
  }
}

onMounted(initVideo)
watch(() => props.docker, initVideo)
</script>

<style scoped>
.docker-video-container {
  width: 100%;
  aspect-ratio: 16 / 9;  /* 保持16:9的宽高比 */
  background-color: #2a2a3a;  /* 深色背景 */
  border-radius: 6px;  /* 圆角 */
  margin: 0;
  overflow: hidden;  /* 隐藏溢出内容 */
  position: relative;  /* 相对定位 */
}

.docker-video-container::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #606080;
  font-size: 14px;
}

/* 视频元素样式 */
.docker-video-container video {
  width: 100%;
  height: 100%;
  object-fit: cover;  /* 保持宽高比填充容器 */
  background-color: #000;  /* 视频加载前的背景色 */
}
</style>