<template>
  <!-- 地图外层容器 -->
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- 主地图 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 操作按钮区 -->
    <div class="btn-group">
      <button @click="toggleClickToAddPoint">
        {{ clickPointEnabled ? '关闭打点' : '启用打点' }}
      </button>
    <button @click="generateRouteFromPoints">生成飞行航线</button>
    <button @click="toggleAnimation">
        {{ animationPlaying ? '暂停飞行动画' : '开始飞行动画' }}
      </button>
    </div>

    <!-- 迷你地图 -->
    <div id="mini-view" style="position: absolute; top: 30px; left: 10px; width: 220px; height: 160px; border: 2px solid #ccc; z-index: 998;"></div>

    <!-- 无人机设备信息卡片 -->
    <DroneLine :device="deviceInfo" @detail="handleDetail" class="right-card-overlay" />
  </div>
</template>

<script>
import * as Cesium from 'cesium';
import DroneLine from '../Map/DroneLine.vue';
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3MjNmNDQ4Ny04MjBjLTQyYjgtOTA5Ni1lMjRhOTk5MGY3MjMiLCJpZCI6MzIzMzA3LCJpYXQiOjE3NTMwNjU0NzZ9.fD2b3-Hes2o3RrMfNg45qkW5x1-cK0Yqn-xLpxT8SAc';

export default {
  components: { DroneLine },
  // 利用点击不同type的卡片对应跳转后的页面功能
  setup() {
    const route = useRoute();
    const routeType = ref(route.params.type || '');

    // 控制按钮显示逻辑
    const showButtons = {
      enablePointMark: routeType.value === '航点飞行',
      generatePath: routeType.value === '航点飞行' || routeType.value === '带状航线',
      flightAnimation: routeType.value !== '建图航拍',
    };

    return { routeType, showButtons };
  },
  data() {
    return {
      viewer: null,
      miniViewer: null,
      clickPointEnabled: false,
      clickHandler: null,
      deviceInfo: {},
      animationPlaying: true,
      dronePath: [],
      startTime: null,
      stopTime: null,
      userPoints: [],
      coneHeading: 0,
      coneMoveHandler: null,
    };
  },
  mounted() {
    this.loadMap();
  },
  methods: {
    // 初始化主地图和迷你图
    loadMap() {
      this.viewer = new Cesium.Viewer('map-container', {
        timeline: true,
        animation: true,
        shouldAnimate: true,
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          subdomains: ['a', 'b', 'c'],
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      });

      this.viewer.scene.globe.enableLighting = false;
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(115.83, 39.04, 200),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-15),
          roll: 0.0,
        },
      });

      this.miniViewer = new Cesium.Viewer('mini-view', {
        timeline: false,
        animation: false,
        baseLayerPicker: false,
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          subdomains: ['a', 'b', 'c'],
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      });
    },

    // 打点切换按钮
    toggleClickToAddPoint() {
      if (!this.clickPointEnabled) {
        this.enableClickToAddPoint();
      } else {
        this.disableClickToAddPoint();
      }
      this.clickPointEnabled = !this.clickPointEnabled;
    },

    // 启用地图点击添加点
    enableClickToAddPoint() {
      if (this.clickHandler) return;
      this.clickHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
      this.clickHandler.setInputAction((movement) => {
        const earthPosition = this.viewer.scene.pickPosition(movement.position);
        if (!Cesium.defined(earthPosition)) return;
        const cartographic = Cesium.Cartographic.fromCartesian(earthPosition);
        const lon = Cesium.Math.toDegrees(cartographic.longitude);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        const alt = 300;
        this.userPoints.push({ lng: lon, lat: lat, alt });

        // 添加点标记
        this.viewer.entities.add({
          id: `user-point-${this.userPoints.length}`,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
          billboard: {
            image: '/location-filled.svg',
            width: 32,
            height: 32,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          },
          label: {
            text: `(${lon.toFixed(4)}, ${lat.toFixed(4)})`,
            font: '12px sans-serif',
            fillColor: Cesium.Color.BLACK,
            showBackground: true,
            backgroundColor: Cesium.Color.WHITE.withAlpha(0.6),
            horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            pixelOffset: new Cesium.Cartesian2(10, 0),
          },
        });

        // 添加地面垂线投影（虚线）
        this.viewer.entities.add({
          id: `vertical-line-${this.userPoints.length}`,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights([lon, lat, alt, lon, lat, 0]),
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({
              color: new Cesium.Color(1.0, 0.5, 0.0, 0.6),  // 橙色
              dashLength: 8,
            }),
          },
        });
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },

    disableClickToAddPoint() {
      if (this.clickHandler) {
        this.clickHandler.destroy();
        this.clickHandler = null;
      }
    },

    // 生成航线、锥体
    generateRouteFromPoints() {
      if (this.userPoints.length < 2) {
        alert('请至少打两个点');
        return;
      }
      this.dronePath = [...this.userPoints];
      this.addDroneTrajectory();
      this.addViewCone();
      this.enableViewConeRotation();
    },

    // 添加无人机动画轨迹
    addDroneTrajectory() {
      this.startTime = Cesium.JulianDate.now();
      this.stopTime = Cesium.JulianDate.addSeconds(this.startTime, this.dronePath.length * 2, new Cesium.JulianDate());

      const pathPositions = this.dronePath.map(p => Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt));
      const oldPath = this.viewer.entities.getById('drone-path');
      if (oldPath) this.viewer.entities.remove(oldPath);
      this.viewer.entities.add({
        id: 'drone-path',
        polyline: {
          positions: pathPositions,
          width: 8,
          material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.2, color: Cesium.Color.CYAN }),
        },
      });

      const sampledPosition = new Cesium.SampledPositionProperty();
      this.dronePath.forEach((point, index) => {
        const time = Cesium.JulianDate.addSeconds(this.startTime, index * 2, new Cesium.JulianDate());
        const position = Cesium.Cartesian3.fromDegrees(point.lng, point.lat, point.alt);
        sampledPosition.addSample(time, position);
      });

      const oldDrone = this.viewer.entities.getById('drone-entity');
      if (oldDrone) this.viewer.entities.remove(oldDrone);
      this.viewer.entities.add({
        id: 'drone-entity',
        availability: new Cesium.TimeIntervalCollection([
          new Cesium.TimeInterval({ start: this.startTime, stop: this.stopTime }),
        ]),
        position: sampledPosition,
        orientation: new Cesium.VelocityOrientationProperty(sampledPosition),
        model: {
          uri: '/models/Cesium_Air.glb',
          scale: 1.0,
          minimumPixelSize: 64,
          maximumScale: 200,
        },
        path: {
          resolution: 1,
          material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.2, color: Cesium.Color.YELLOW }),
          width: 2,
        },
      });

      this.viewer.clock.startTime = this.startTime.clone();
      this.viewer.clock.stopTime = this.stopTime.clone();
      this.viewer.clock.currentTime = this.startTime.clone();
      this.viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;
      this.viewer.clock.multiplier = 1;
      this.viewer.clock.shouldAnimate = this.animationPlaying;
      if (this.viewer.timeline) {
        this.viewer.timeline.zoomTo(this.startTime, this.stopTime);
      }
    },

    // 添加锥体并绑定位置和方向
    addViewCone() {
      const oldCone = this.viewer.entities.getById('view-cone');
      if (oldCone) this.viewer.entities.remove(oldCone);

      const coneLength = 100;
      const coneBottomRadius = 30;

      this.viewer.entities.add({
        id: 'view-cone',
        position: new Cesium.CallbackProperty((time) => {
          const drone = this.viewer.entities.getById('drone-entity');
          return drone ? drone.position.getValue(time) : Cesium.Cartesian3.fromDegrees(0, 0, 0);
        }, false),
        orientation: new Cesium.CallbackProperty((time) => {
          const drone = this.viewer.entities.getById('drone-entity');
          if (!drone) return Cesium.Quaternion.IDENTITY;
          const pos = drone.position.getValue(time);
          return Cesium.Transforms.headingPitchRollQuaternion(
            pos,
            new Cesium.HeadingPitchRoll(this.coneHeading, Cesium.Math.toRadians(90), 0)
          );
        }, false),
        cylinder: {
          length: coneLength,
          topRadius: 0,
          bottomRadius: coneBottomRadius,
          material: Cesium.Color.YELLOW.withAlpha(0.5),
          outline: true,
          outlineColor: Cesium.Color.ORANGE,
        },
      });
    },

    // 鼠标移动改变锥体朝向
    enableViewConeRotation() {
      if (this.coneMoveHandler) return;
      this.coneMoveHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
      this.coneMoveHandler.setInputAction((movement) => {
        const earthPosition = this.viewer.scene.pickPosition(movement.endPosition);
        if (!Cesium.defined(earthPosition)) return;
        const drone = this.viewer.entities.getById('drone-entity');
        if (!drone) return;
        const dronePosition = drone.position.getValue(this.viewer.clock.currentTime);
        if (!dronePosition) return;

        const from = Cesium.Cartographic.fromCartesian(dronePosition);
        const to = Cesium.Cartographic.fromCartesian(earthPosition);
        const heading = Math.atan2(to.longitude - from.longitude, to.latitude - from.latitude);
        this.coneHeading = heading;
      }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
    },

    toggleAnimation() {
      this.animationPlaying = !this.animationPlaying;
      this.viewer.clock.shouldAnimate = this.animationPlaying;
    },

    handleDetail() {
      console.log('查看详情');
    },
  },

  beforeUnmount() {
    this.disableClickToAddPoint();
    if (this.coneMoveHandler) {
      this.coneMoveHandler.destroy();
      this.coneMoveHandler = null;
    }
    if (this.viewer) {
      this.viewer.destroy();
      this.viewer = null;
    }
    if (this.miniViewer) {
      this.miniViewer.destroy();
      this.miniViewer = null;
    }
  },
};
</script>

<style scoped>
.btn-group {
  position: absolute;
  bottom: 120px;   /* 离底部距离稍大，整体上移 */
  left: 10px;
  display: flex;
  flex-direction: column;  /* 竖排排列 */
  gap: 12px;               /* 按钮间距 */
  z-index: 999;
}

.btn-group button {
  background-color: #2c3e50;  /* 深蓝色 */
  color: white;
  border: none;
  padding: 12px 18px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 0 4px 6px rgb(0 0 0 / 0.15);
  transition: background-color 0.3s ease;
}

.btn-group button:hover {
  background-color: #34495e;  /* 悬浮色 */
}

.btn-group button:active {
  background-color: #1f2d3d;  /* 点击时颜色 */
}
</style>

<style>
#map-container {
  width: 100%;
  height: 100vh;
}
</style>
