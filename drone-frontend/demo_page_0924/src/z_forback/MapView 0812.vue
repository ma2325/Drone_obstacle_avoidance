```vue
<template>
  <!-- 地图外层容器，占据整个视口 -->
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- 主地图容器 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 操作按钮区，根据航线类型动态显示 -->
    <div class="btn-group" v-if="showButtons && Object.values(showButtons).some(val => val)">
      <!-- 航点飞行相关按钮 -->
      <button v-if="showButtons.enablePointMark" @click="toggleClickToAddPoint">
        {{ clickPointEnabled ? '关闭打点' : '启用打点' }}
      </button>
      <button v-if="showButtons.generatePointPath" @click="generateRouteFromPoints">生成飞行航线</button>
      <button v-if="showButtons.flightAnimation" @click="toggleAnimation">
        {{ animationPlaying ? '暂停飞行动画' : '开始飞行动画' }}
      </button>
      <!-- 建图航拍相关按钮 -->
      <button v-if="showButtons.drawArea" @click="toggleDrawArea">
        {{ drawAreaEnabled ? '关闭区域绘制' : '启用区域绘制' }}
      </button>
      <button v-if="showButtons.generateGrid" @click="generateGridPath">生成航拍网格</button>
      <button v-if="showButtons.previewGridPath" @click="previewGridPath">预览航拍路径</button>
      <!-- 带状航线相关按钮 -->
      <button v-if="showButtons.generateStripPath" @click="generateStripPath">生成带状路径</button>
    </div>
    <!-- 如果没有按钮显示，提示用户 -->
    <div v-else class="no-buttons-message">
      未检测到有效航线类型，请从任务列表重新选择
    </div>

    <!-- 迷你地图，显示在主地图左上角 -->
    <div id="mini-view" style="position: absolute; top: 30px; left: 10px; width: 220px; height: 160px; border: 2px solid #ccc; z-index: 998;"></div>

    <!-- 无人机设备信息卡片 -->
    <DroneLine :device="deviceInfo" @detail="handleDetail" class="right-card-overlay" />
  </div>
</template>

<script>
import * as Cesium from 'cesium';
import DroneLine from '../Map/DroneLine.vue';
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import * as turf from '@turf/turf';

// 设置 Cesium 的 Ion 访问令牌
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3MjNmNDQ4Ny04MjBjLTQyYjgtOTA5Ni1lMjRhOTk5MGY3MjMiLCJpZCI6MzIzMzA3LCJpYXQiOjE3NTMwNjU0NzZ9.fD2b3-Hes2o3RrMfNg45qkW5x1-cK0Yqn-xLpxT8SAc';

// 确保 Cesium 资源路径正确
if (typeof CESIUM_BASE_URL !== 'undefined') {
  Cesium.buildModuleUrl.setBaseUrl(CESIUM_BASE_URL);
}

export default {
  components: { DroneLine },

  setup() {
    const route = useRoute();
    const routeType = ref(route.params.type || '');
    const taskId = ref(route.params.taskId || '');

    const showButtons = ref({
      enablePointMark: routeType.value === '航点飞行',
      generatePointPath: routeType.value === '航点飞行',
      flightAnimation: routeType.value === '航点飞行' || routeType.value === '带状航线',
      drawArea: routeType.value === '建图航拍',
      generateGrid: routeType.value === '建图航拍',
      previewGridPath: routeType.value === '建图航拍',
      generateStripPath: routeType.value === '带状航线',
    });

    onMounted(() => {
      console.log('进入地图页，当前航线类型:', routeType.value, '任务ID:', taskId.value);
      if (!['航点飞行', '建图航拍', '带状航线'].includes(routeType.value)) {
        console.warn('无效的航线类型:', routeType.value);
      }
    });

    return { routeType, showButtons, taskId };
  },

  data() {
    return {
      viewer: null,
      miniViewer: null,
      clickPointEnabled: false,
      drawAreaEnabled: false,
      clickHandler: null,
      areaHandler: null,
      deviceInfo: {}, // 动态绑定 taskId
      animationPlaying: true,
      dronePath: [],
      startTime: null,
      stopTime: null,
      userPoints: [],
      userAreaPoints: [],
      gridPath: [],
      stripPath: [],
      coneHeading: 0,
      coneMoveHandler: null,
      savedRoutes: {}, // 本地缓存，从 localStorage 加载
    };
  },

  mounted() {
    this.deviceInfo.taskId = this.taskId; // 绑定 taskId
    console.log('MapView mounted, taskId:', this.taskId);
    this.loadMap();
    this.loadSavedRoute(); // 加载保存的航线
  },

  methods: {
    // 加载保存的航线
    loadSavedRoute() {
      try {
        const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}');
        console.log('从 localStorage 加载 savedRoutes:', savedRoutes);
        this.savedRoutes = savedRoutes;

        if (!this.taskId) {
          console.warn('taskId 为空，无法加载航线');
          return;
        }

        if (savedRoutes[this.taskId]) {
          const route = savedRoutes[this.taskId];
          console.log(`加载任务 ${this.taskId} 的航线数据:`, route);

          if (route.type === '航点飞行') {
            this.userPoints = JSON.parse(JSON.stringify(route.points || []));
            console.log('恢复航点飞行数据，userPoints:', this.userPoints);
            if (this.userPoints.length >= 2) {
              this.generateRouteFromPoints();
            }
          } else if (route.type === '建图航拍') {
            this.gridPath = JSON.parse(JSON.stringify(route.points || []));
            this.userAreaPoints = JSON.parse(JSON.stringify(route.areaPoints || []));
            console.log('恢复建图航拍数据，gridPath:', this.gridPath, 'userAreaPoints:', this.userAreaPoints);
            if (this.gridPath.length >= 2) {
              this.addDroneTrajectory(this.gridPath);
              this.drawAreaPolygon();
            }
          } else if (route.type === '带状航线') {
            this.stripPath = JSON.parse(JSON.stringify(route.points || []));
            this.userPoints = JSON.parse(JSON.stringify(route.basePoints || []));
            console.log('恢复带状航线数据，stripPath:', this.stripPath, 'userPoints:', this.userPoints);
            if (this.stripPath.length >= 2) {
              this.addDroneTrajectory(this.stripPath);
            }
          }
        } else {
          console.log(`任务 ${this.taskId} 无保存的航线数据`);
        }
      } catch (error) {
        console.error('加载航线数据失败:', error);
      }
    },

    // 保存航线到 localStorage
    saveRouteToStorage() {
      try {
        console.log('保存航线到 localStorage, savedRoutes:', this.savedRoutes);
        localStorage.setItem('savedRoutes', JSON.stringify(this.savedRoutes));
        console.log('保存成功，当前 localStorage savedRoutes:', JSON.parse(localStorage.getItem('savedRoutes')));
      } catch (error) {
        console.error('保存航线到 localStorage 失败:', error);
      }
    },

    // 初始化主地图和迷你地图
    loadMap() {
      try {
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
      } catch (error) {
        console.error('地图初始化失败:', error);
      }
    },

    // 切换航点打点状态
    toggleClickToAddPoint() {
      if (!this.clickPointEnabled) {
        this.enableClickToAddPoint();
      } else {
        this.disableClickToAddPoint();
      }
      this.clickPointEnabled = !this.clickPointEnabled;
    },

    // 启用航点打点
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

        this.viewer.entities.add({
          id: `vertical-line-${this.userPoints.length}`,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights([lon, lat, alt, lon, lat, 0]),
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({
              color: new Cesium.Color(1.0, 0.5, 0.0, 0.6),
              dashLength: 8,
            }),
          },
        });
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },

    // 禁用航点打点
    disableClickToAddPoint() {
      if (this.clickHandler) {
        this.clickHandler.destroy();
        this.clickHandler = null;
      }
    },

    // 生成航点飞行路径和视锥
    generateRouteFromPoints() {
      if (this.userPoints.length < 2) {
        alert('请至少打两个点');
        return;
      }
      this.dronePath = JSON.parse(JSON.stringify(this.userPoints));
      this.addDroneTrajectory();
      this.addViewCone();
      this.enableViewConeRotation();
      this.savedRoutes[this.deviceInfo.taskId] = {
        type: '航点飞行',
        points: JSON.parse(JSON.stringify(this.userPoints)),
      };
      console.log('生成航点飞行航线，保存数据:', this.savedRoutes[this.deviceInfo.taskId]);
      this.saveRouteToStorage();
    },

    // 添加无人机动画轨迹
    addDroneTrajectory(path = this.dronePath) {
      this.startTime = Cesium.JulianDate.now();
      this.stopTime = Cesium.JulianDate.addSeconds(this.startTime, path.length * 2, new Cesium.JulianDate());

      const pathPositions = path.map(p => Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt));
      const oldPath = this.viewer.entities.getById('drone-path');
      if (oldPath) this.viewer.entities.remove(oldPath);
      this.viewer.entities.add({
        id: 'drone-path',
        polyline: {
          positions: pathPositions,
          width: 10,
          material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.2, color: Cesium.Color.CYAN }),
        },
      });

      const sampledPosition = new Cesium.SampledPositionProperty();
      path.forEach((point, index) => {
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

    // 添加视锥并绑定无人机位置和方向
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

    // 鼠标移动改变视锥朝向
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

    // 切换飞行动画播放状态
    toggleAnimation() {
      this.animationPlaying = !this.animationPlaying;
      this.viewer.clock.shouldAnimate = this.animationPlaying;
    },

    // 处理无人机信息卡片详情点击
    handleDetail() {
      console.log('查看详情，任务ID:', this.deviceInfo.taskId);
      const route = this.savedRoutes[this.deviceInfo.taskId];
      if (!route) {
        alert('未找到对应的航线，请先生成');
        return;
      }

      console.log('恢复航线数据:', route);
      if (route.type === '航点飞行') {
        this.userPoints = JSON.parse(JSON.stringify(route.points || []));
        this.generateRouteFromPoints();
      } else if (route.type === '建图航拍') {
        this.gridPath = JSON.parse(JSON.stringify(route.points || []));
        this.userAreaPoints = JSON.parse(JSON.stringify(route.areaPoints || []));
        this.addDroneTrajectory(this.gridPath);
        this.drawAreaPolygon();
      } else if (route.type === '带状航线') {
        this.stripPath = JSON.parse(JSON.stringify(route.points || []));
        this.userPoints = JSON.parse(JSON.stringify(route.basePoints || []));
        this.addDroneTrajectory(this.stripPath);
      }
    },

    // 切换区域绘制状态（建图航拍）
    toggleDrawArea() {
      if (!this.drawAreaEnabled) {
        this.enableDrawArea();
      } else {
        this.disableDrawArea();
      }
      this.drawAreaEnabled = !this.drawAreaEnabled;
    },

    // 启用区域绘制（建图航拍）
    enableDrawArea() {
      if (this.areaHandler) return;
      this.areaHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
      this.areaHandler.setInputAction((movement) => {
        const earthPosition = this.viewer.scene.pickPosition(movement.position);
        if (!Cesium.defined(earthPosition)) return;
        const cartographic = Cesium.Cartographic.fromCartesian(earthPosition);
        const lon = Cesium.Math.toDegrees(cartographic.longitude);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        const alt = 300;
        this.userAreaPoints.push({ lng: lon, lat: lat, alt });

        this.viewer.entities.add({
          id: `area-point-${this.userAreaPoints.length}`,
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

        if (this.userAreaPoints.length >= 2) {
          const oldPolygon = this.viewer.entities.getById('area-polygon');
          if (oldPolygon) this.viewer.entities.remove(oldPolygon);
          this.viewer.entities.add({
            id: 'area-polygon',
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(
                this.userAreaPoints.flatMap(p => [p.lng, p.lat, p.alt])
              ),
              material: Cesium.Color.BLUE.withAlpha(0.3),
              outline: true,
              outlineColor: Cesium.Color.BLUE,
            },
          });
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },

    // 禁用区域绘制
    disableDrawArea() {
      if (this.areaHandler) {
        this.areaHandler.destroy();
        this.areaHandler = null;
      }
    },

    // 恢复区域多边形
    drawAreaPolygon() {
      if (this.userAreaPoints.length >= 2) {
        const oldPolygon = this.viewer.entities.getById('area-polygon');
        if (oldPolygon) this.viewer.entities.remove(oldPolygon);
        this.viewer.entities.add({
          id: 'area-polygon',
          polygon: {
            hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(
              this.userAreaPoints.flatMap(p => [p.lng, p.lat, p.alt])
            ),
            material: Cesium.Color.BLUE.withAlpha(0.3),
            outline: true,
            outlineColor: Cesium.Color.BLUE,
          },
        });

        this.userAreaPoints.forEach((point, index) => {
          const existingPoint = this.viewer.entities.getById(`area-point-${index + 1}`);
          if (existingPoint) this.viewer.entities.remove(existingPoint);
          this.viewer.entities.add({
            id: `area-point-${index + 1}`,
            position: Cesium.Cartesian3.fromDegrees(point.lng, point.lat, point.alt),
            billboard: {
              image: '/location-filled.svg',
              width: 32,
              height: 32,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            },
            label: {
              text: `(${point.lng.toFixed(4)}, ${point.lat.toFixed(4)})`,
              font: '12px sans-serif',
              fillColor: Cesium.Color.BLACK,
              showBackground: true,
              backgroundColor: Cesium.Color.WHITE.withAlpha(0.6),
              horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
              verticalOrigin: Cesium.VerticalOrigin.TOP,
              pixelOffset: new Cesium.Cartesian2(10, 0),
            },
          });
        });
        console.log('恢复区域多边形，userAreaPoints:', this.userAreaPoints);
      }
    },

    // 生成航拍网格路径（建图航拍）
    generateGridPath() {
      if (this.userAreaPoints.length < 3) {
        alert('请至少绘制三个点以形成多边形区域');
        return;
      }
      this.gridPath = [];
      const bounds = this.getPolygonBounds(this.userAreaPoints);
      const step = 100;
      const stepLat = step / 111111;
      const stepLng = step / (111111 * Math.cos(Cesium.Math.toRadians(bounds.minLat)));

      const polygon = {
        type: 'Polygon',
        coordinates: [
          this.userAreaPoints
            .map(p => [p.lng, p.lat])
            .concat([[this.userAreaPoints[0].lng, this.userAreaPoints[0].lat]]),
        ],
      };

      for (let lat = bounds.minLat; lat <= bounds.maxLat; lat += stepLat) {
        for (let lng = bounds.minLng; lng <= bounds.maxLng; lng += stepLng) {
          const point = turf.point([lng, lat]);
          if (turf.booleanPointInPolygon(point, polygon)) {
            this.gridPath.push({ lng, lat, alt: 300 });
          }
        }
      }

      if (this.gridPath.length > 1) {
        const optimizedPath = this.optimizeGridPath(this.gridPath);
        this.addDroneTrajectory(optimizedPath);
        this.savedRoutes[this.deviceInfo.taskId] = {
          type: '建图航拍',
          points: JSON.parse(JSON.stringify(this.gridPath)),
          areaPoints: JSON.parse(JSON.stringify(this.userAreaPoints)),
        };
        console.log('生成建图航拍网格，保存数据:', this.savedRoutes[this.deviceInfo.taskId]);
        this.saveRouteToStorage();
      } else {
        alert('未生成有效网格路径，请检查多边形区域');
      }
    },

    // 优化网格路径（蛇形路径排序）
    optimizeGridPath(points) {
      const groupedByLat = points.reduce((acc, p) => {
        const latKey = Math.round(p.lat / (100 / 111111)) * (100 / 111111);
        if (!acc[latKey]) acc[latKey] = [];
        acc[latKey].push(p);
        return acc;
      }, {});

      const sortedLats = Object.keys(groupedByLat).sort((a, b) => a - b);
      const optimizedPath = [];
      sortedLats.forEach((lat, index) => {
        const row = groupedByLat[lat].sort((a, b) => (index % 2 === 0 ? a.lng - b.lng : b.lng - a.lng));
        optimizedPath.push(...row);
      });

      return optimizedPath;
    },

    // 预览航拍路径（建图航拍）
    previewGridPath() {
      if (this.gridPath.length < 2) {
        alert('请先生成航拍网格');
        return;
      }
      this.toggleAnimation();
    },

    // 生成带状路径（带状航线）
    generateStripPath() {
      if (this.userPoints.length < 2) {
        alert('请至少打两个点以定义带状区域');
        return;
      }
      this.stripPath = [];
      const step = 5;
      const width = 50;
      const [p1, p2] = this.userPoints;
      const angle = Math.atan2(p2.lat - p1.lat, p2.lng - p1.lng);
      for (let offset = -width / 2; offset <= width / 2; offset += step) {
        const dx = (offset * Math.cos(angle + Math.PI / 2)) / 111111;
        const dy = (offset * Math.sin(angle + Math.PI / 2)) / 111111;
        this.stripPath.push(
          { lng: p1.lng + dx, lat: p1.lat + dy, alt: 300 },
          { lng: p2.lng + dx, lat: p2.lat + dy, alt: 300 }
        );
      }
      this.addDroneTrajectory(this.stripPath);
      this.savedRoutes[this.deviceInfo.taskId] = {
        type: '带状航线',
        points: JSON.parse(JSON.stringify(this.stripPath)),
        basePoints: JSON.parse(JSON.stringify(this.userPoints)),
      };
      console.log('生成带状航线，保存数据:', this.savedRoutes[this.deviceInfo.taskId]);
      this.saveRouteToStorage();
    },

    // 计算多边形边界
    getPolygonBounds(points) {
      const lngs = points.map(p => p.lng);
      const lats = points.map(p => p.lat);
      return {
        minLng: Math.min(...lngs),
        maxLng: Math.max(...lngs),
        minLat: Math.min(...lats),
        maxLat: Math.max(...lats),
      };
    },
  },

  beforeUnmount() {
    this.disableClickToAddPoint();
    this.disableDrawArea();
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
    console.log('MapView beforeUnmount, 保存的航线数据未清除');
  },
};
</script>

<style scoped>
.btn-group {
  position: absolute;
  bottom: 120px;
  left: 10px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 1000;
  max-height: 70vh;
  overflow-y: auto;
  background-color: rgba(0, 0, 0, 0.5);
  padding: 10px;
  border-radius: 8px;
}

.btn-group button {
  background-color: #2c3e50;
  color: white;
  border: none;
  padding: 12px 18px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
  transition: background-color 0.3s ease;
}

.btn-group button:hover {
  background-color: #34495e;
}

.btn-group button:active {
  background-color: #1f2d3d;
}

.no-buttons-message {
  position: absolute;
  bottom: 120px;
  left: 10px;
  background-color: rgba(255, 0, 0, 0.8);
  color: white;
  padding: 10px;
  border-radius: 8px;
  z-index: 1000;
  font-size: 14px;
}
</style>

<style>
#map-container {
  width: 100%;
  height: 100vh;
}
</style>
```