<template>
  <div class="drone-labels-container">
    <div 
      v-for="(labelData, deviceId) in activeLabels" 
      :key="deviceId"
      class="progress-wrapper"
      :style="getLabelStyle(labelData)"
    >
      <div class="progress-box">
        <div class="progress-container">
          <div class="progress-bar" :style="{ width: `${labelData.progress}%` }"></div>
        </div>
        <span class="progress-text">{{ labelData.progress }}%</span>
      </div>
    </div>
  </div>
</template>

<script>
import * as Cesium from 'cesium';

export default {
  name: 'DroneLabels',
  props: {
    devices: { type: Array, required: true },
    viewer: { type: Object, required: true }
  },
  data() {
    return {
      activeLabels: {},
      updateInterval: null
    };
  },
  mounted() {
    this.startUpdateLoop();
  },
  beforeUnmount() {
    this.stopUpdateLoop();
  },
  methods: {
    startUpdateLoop() {
      this.updateInterval = setInterval(this.updateLabels, 200);
    },
    stopUpdateLoop() {
      if (this.updateInterval) {
        clearInterval(this.updateInterval);
        this.updateInterval = null;
      }
    },
    updateLabels() {
      if (!this.viewer || !this.devices) return;

      const scene = this.viewer.scene;
      const newActiveLabels = {};

      this.devices.forEach(device => {
        const entity = this.viewer.entities.getById(device.id);
        if (!entity) return;

        const position = entity.position.getValue(this.viewer.clock.currentTime);
        if (!position) return;

        const canvasPosition = scene.cartesianToCanvasCoordinates(position);
        if (!canvasPosition) return;

        // 计算进度
        const progress = this.calculateRouteProgress(device);

        newActiveLabels[device.id] = {
          x: canvasPosition.x,
          y: canvasPosition.y,
          progress
        };
      });

      this.activeLabels = newActiveLabels;
    },
    calculateRouteProgress(device) {
      if (!device.path || device.path.length === 0) return 0;

      const currentTime = this.viewer.clock.currentTime;
      const startTime = Cesium.JulianDate.fromIso8601(device.path[0].time);
      const endTime = Cesium.JulianDate.fromIso8601(device.path[device.path.length - 1].time);

      if (Cesium.JulianDate.greaterThan(currentTime, startTime)) {
        if (Cesium.JulianDate.greaterThan(currentTime, endTime)) return 100;
        const totalDuration = Cesium.JulianDate.secondsDifference(endTime, startTime);
        const elapsedDuration = Cesium.JulianDate.secondsDifference(currentTime, startTime);
        return Math.round((elapsedDuration / totalDuration) * 100);
      }
      return 0;
    },
    getLabelStyle(labelData) {
      return {
        position: 'absolute',
        left: `${labelData.x}px`,
        top: `${labelData.y}px`,
        transform: 'translate(-50%, -150%)'
      };
    }
  }
};
</script>

<style scoped>
.drone-labels-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
}

.progress-wrapper {
  pointer-events: none;
}

.progress-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0, 0, 0, 0.3); 
  padding: 1px 5px;
  border-radius: 6px;
}

.progress-container {
  width: 30px;
  height: 4px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: #00c4ff;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 8px;
  color: #ffffff;
}
</style>
