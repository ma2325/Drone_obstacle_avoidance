<template>
  <div class="map-container-wrapper">
    <div id="map-container" :class="isCockpitView ? 'cockpit-map' : 'normal-map'"></div>

    <!-- ================= 普通视图 ================= -->
    <div v-show="!isCockpitView">

      <!-- 🎯 无人机实时数据面板（左侧） -->
      <DroneDataPanel />

      <DeviceDetail v-if="currentDevice" :device="currentDevice" @action="handleAction" class="detail-panel" />
      <DockerDetail v-if="currentDocker" :docker="currentDocker" :devices="devices" @action="handleAction"
        class="detail-panel" />


      <DroneLabels v-if="viewer && devices" :devices="devices" :viewer="viewer" @select-device="handleDeviceSelect" />


      <RightPanel class="right-panel" @action="handleAction" :devices="devices" />


      <div v-if="showModal" class="modal-overlay" :class="{ 'full-screen': modalType === 'Cockpit' }">
        <div class="modal-content">
          <component :is="modalType" :device="modalDevice" @action="handleAction" />
        </div>
      </div>


      <div class="map-legend">
        <div class="legend-row">
          <img src="/icons/congestion.svg" alt="拥堵点图标" class="legend-icon" />
          拥堵点
        </div>
        <div class="legend-row">
          <img src="/icons/bridge.svg" alt="大桥图标" class="legend-icon" />
          大桥
        </div>
        <div class="legend-row">
          <img src="/icons/danger.svg" alt="危险点图标" class="legend-icon" />
          危险点
        </div>
      </div>
    </div>

    <!-- ================= Cockpit 视图 ================= -->

    <div v-show="isCockpitView" class="cockpit-layout" :class="cockpitMode + '-mode'"
      style="width: 100%; height: 100%;">

      <div class="cockpit-top-left">
        <DockerVideo v-if="currentDocker && cockpitMode === 'takeoff'" :docker="currentDocker" />
      </div>


      <div class="cockpit-bottom-left">
      </div>


      <div class="cockpit-top-right" style="width: 100%; height: 100%;">
        <DroneVideo v-if="selectedDrone" :device="selectedDrone" />
      </div>


      <div class="cockpit-bottom-right" style="width: 100%; height: 100%;">
        <Cockpit :device="selectedDrone" :mode="cockpitMode" @action="handleAction" />
      </div>
    </div>
  </div>
</template>



<script>
import * as Cesium from 'cesium';
import { ArcGisMapServerImageryProvider } from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css'
import RightPanel from '../Home/RightPanel.vue';
import DeviceDetail from '../Home/DeviceDetail.vue';
import DockerDetail from '../Home/DockerDetail.vue';
import DispatchSettings from '../Home/DispatchSettings.vue';
import DispatchMonitor from '../Home/DispatchMonitor.vue';
import TakeOffSettings from '../Home/TakeOffSettings.vue';
import Cockpit from '../Home/Cockpit.vue';
import devices from '@/test-data/devices.json';
import dockers from '@/test-data/dockers.json';
import flightData from '@/test-data/flightData.json';
import DroneVideo from '../Home/DroneVideo.vue';
import DockerVideo from '../Home/DockerVideo.vue';
import routesData from '@/test-data/routes.json';
import DroneLabels from '../Home/DroneLabels.vue';
import eventPoints from '@/test-data/eventPoints.json';
import DroneDataPanel from '../Home/DroneDataPanel.vue';  // 🎯 新增：无人机数据面板



export default {
  components: {
    RightPanel,
    DeviceDetail,
    DockerDetail,
    DispatchSettings,
    TakeOffSettings,
    DispatchMonitor,
    DroneDataPanel,  // 🎯 注册无人机数据面板
    Cockpit,
    DroneVideo,
    DockerVideo,
    DroneLabels
  },
  data() {
    return {
      map: null,
      viewer: null,
      currentDevice: null,
      currentDocker: null,
      showModal: false,
      modalType: null,
      modalDevice: null,
      isCockpitView: false,
      devices,
      dockers,
      flightData,
      devicePositions: new Map(),
      dockerPositions: new Map(),
      focusedDeviceId: null,
      showDispatchMonitor: false,
      currentDispatchMonitorDevice: null,
      selectedDrone: null,
      eventPoints,
      hasFocusedOnce: false, // 标记
      cockpitMode: 'control-panel',
      _highlightRouteEntity: null, // ✅ 记录高亮路线实体，方便下次清理
    };
  },
  mounted() {
    console.log('当前四分视图状态:', this.isCockpitView);

    this.loadMap();
    // ✅ 建立无人机和机场之间的交互关系
    this.dockers.forEach(docker => {
      docker.drones = docker.associatedDevices
        .map(id => this.devices.find(device => device.id === id))
        .filter(Boolean)
    })

    // ✅ 如果路由带了 focus 参数，自动聚焦无人机
    const focusId = this.$route.query.focus;
    if (focusId) {
      this.$nextTick(() => {
        this.focusOnDevice(focusId);

        // 用完后清除 focus 参数，防止刷新时继续聚焦
        const newQuery = { ...this.$route.query };
        delete newQuery.focus;
        this.$router.replace({ path: this.$route.path, query: newQuery });
      });
    } else {
      // 只有在主页上，且没有 focus 参数时，恢复默认视角
      // if (this.$route.path === '/home') {
      //   this.resetToInitialView();  // 没有 focus 参数时恢复到默认视角
      // }
    }
  },

  beforeUnmount() {
    // ✅ 移除事件监听，避免内存泄漏
    window.removeEventListener('focus-device', this._offFocusDevice)
  },

  watch: {

    isCockpitView(newVal) {
      // 这里不再重新 loadMap，只切换容器的 class
      this.$nextTick(() => {
        // 容器尺寸/位置变化后，让 Cesium 重新适配
        if (this.viewer) {
          this.viewer.resize();
          this.viewer.scene.requestRender();
        }
      });
    },

    // 当选择的机场变化时，获取该机场的第一个关联无人机并展示
    currentDocker(newDocker) {
      if (newDocker && newDocker.associatedDevices && newDocker.associatedDevices.length > 0) {
        // 选择第一个关联的无人机
        const firstDroneId = newDocker.associatedDevices[0];
        this.selectDrone(firstDroneId);
      } else {
        this.selectedDrone = null;  // 如果没有关联的无人机，则清空选中
      }
    },

  },
  methods: {
    async loadMap() {

      try {

        Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJiNzEzZjEzYi0wNjg5LTQ0OTMtYWZkNS1iNTVjOTRmMDMwNzEiLCJpZCI6MzIwMjIwLCJpYXQiOjE3NTIyMDAxMzd9.oytvSPRNdHLhiI2KxkAAU8Peyb4bX0OaZFlZE4MDHv8';






        // 让Cesium自动使用默认的Ion影像和地形
        this.viewer = new Cesium.Viewer('map-container', {
          terrainProvider: await Cesium.createWorldTerrainAsync(),
          // 不指定imageryProvider，让Cesium使用默认的Ion影像
          homeButton: false,
          sceneModePicker: false,
          baseLayerPicker: false, // 设置为true可以看到底图选择器
          navigationHelpButton: false,
          geocoder: false,
          animation: true,
          timeline: true,
          fullscreenButton: false,
          infoBox: false,
          contextOptions: {
            requestWebgl2: true
          }
        });

        // 隐藏Cesium Ion的logo和版权信息
        this.viewer.cesiumWidget.creditContainer.style.display = "none";

        // 3) 再异步加载全球地形（此时 CESIUM_BASE_URL 已正确设置）
        const worldTerrain = await Cesium.createWorldTerrainAsync()
        this.viewer.terrainProvider = worldTerrain

        const focusId = this.$route.query.focus
        if (focusId) {
          console.log('[HomeView] 地图加载完成，准备聚焦无人机:', focusId)
          this.$nextTick(() => {
            this.focusOnDevice(focusId)
          })
        }




        // 添加高速公路3D Tiles底图
        //  try {
        //           const tileset = await Cesium.Cesium3DTileset.fromIonAssetId(96188);
        //           this.viewer.scene.primitives.add(tileset);
        //           console.log('Highway 3D Tileset loaded:', tileset);
        //           this.viewer.zoomTo(tileset, new Cesium.HeadingPitchRange(0, -Cesium.Math.PI / 4, 0));
        //         } catch (error) {
        //           console.error('Failed to load 3D Tileset (assetId: 96188):', error);
        //           this.viewer.camera.setView({
        //             destination: Cesium.Cartesian3.fromDegrees(115.695699, 39.043926, 10000.0),
        //           });
        //         }

        // 设置时钟和动画
        const startTime = Cesium.JulianDate.fromIso8601('2025-07-14T09:55:00Z');
        const stopTime = Cesium.JulianDate.addSeconds(startTime, 30000, new Cesium.JulianDate());
        this.viewer.clock.startTime = startTime.clone();
        this.viewer.clock.stopTime = stopTime.clone();
        this.viewer.clock.currentTime = startTime.clone();
        this.viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;
        this.viewer.clock.multiplier = 10;
        this.viewer.clock.shouldAnimate = true;
        this.viewer.timeline.zoomTo(startTime, stopTime);

        // 设定初始视角
        this.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(115.579662, 38.870149, 70000.0),
          orientation: { heading: 0, pitch: -Cesium.Math.PI / 2, roll: 0 }
        });
        console.log('Initial camera height:', this.viewer.camera.positionCartographic.height, 'meters');

        // 验证设备数据
        if (!this.devices || this.devices.length === 0) {
          console.warn('No devices available, using default view');
          return;
        }

        // 加载机场数据
        this.dockers.forEach(docker => {
          const entity = this.viewer.entities.add({
            id: docker.id,
            name: docker.name,
            position: Cesium.Cartesian3.fromDegrees(docker.position[0], docker.position[1], 0),
            model: {
              uri: 'models/docker1.glb',
              scale: 0.1,
              minimumPixelSize: 16,
              color: Cesium.Color.WHITE,
              silhouetteColor: Cesium.Color.WHITE,
              silhouetteSize: 2
            },
            label: {
              text: docker.name,
              font: '12px sans-serif',
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              outlineWidth: 2,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -15),

            }
          });
          entity.description = undefined;
          this.dockerPositions.set(docker.id, docker.position);
        });

        // 加载无人机数据
        this.devices.forEach(device => {
          const positionProperty = new Cesium.SampledPositionProperty();
          if (device.path && device.path.length > 0) {
            device.path.forEach(point => {
              const time = Cesium.JulianDate.fromIso8601(point.time);
              const position = Cesium.Cartesian3.fromDegrees(
                point.position[0],
                point.position[1],
                point.position[2]
              );
              positionProperty.addSample(time, position);
            });
            positionProperty.setInterpolationOptions({
              interpolationDegree: 2,
              interpolationAlgorithm: Cesium.LagrangePolynomialApproximation
            });
          } else {
            positionProperty.setInterpolationOptions({
              interpolationDegree: 1,
              interpolationAlgorithm: Cesium.LinearApproximation
            });
          }

          // 添加无人机实体
          const droneEntity = this.viewer.entities.add({
            id: device.id,
            name: device.name,
            position: positionProperty,
            viewFrom: new Cesium.Cartesian3(800, 1500, 400),
            model: {
              uri: 'models/drone2.glb',
              scale: 0.4,
              minimumPixelSize: 32,
              color: Cesium.Color.WHITE,
              silhouetteColor: Cesium.Color.WHITE,
              silhouetteSize: 1
            },
            label: {
              text: device.name,
              font: '12px sans-serif',
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              outlineWidth: 2,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -15),
              show: false
            },
          });

          droneEntity.description = undefined;
          this.devicePositions.set(device.id, device.position);

          // 添加跟随无人机的四棱锥
          const pyramidPosition = new Cesium.CallbackProperty((time) => {
            // 获取无人机在当前时间的位置
            return droneEntity.position.getValue(time);
          }, false);


          // 只为特定无人机（如当前选中的）添加四棱锥，而不是所有无人机
          if (device.id === this.selectedDrone?.id || device.status === '工作中') {
            // 为设备创建缓存对象（如果不存在）
            if (!this._pyramidCache) {
              this._pyramidCache = {};
            }

            // 添加四棱锥实体，高度等于无人机的高度（从地面到无人机）
            this.viewer.entities.add({
              name: `Pyramid-${device.id}`,
              position: new Cesium.CallbackProperty((time) => {
                // 初始化设备缓存
                if (!this._pyramidCache[device.id]) {
                  this._pyramidCache[device.id] = {
                    lastUpdateSecond: 0,
                    position: undefined,
                    height: 0,
                    bottomRadius: 0,
                    orientation: undefined
                  };
                }

                const cache = this._pyramidCache[device.id];
                const currentTimeInSeconds = Cesium.JulianDate.toDate(time).getTime() / 1000;

                // 每0.01秒更新一次
                if (currentTimeInSeconds - cache.lastUpdateSecond >= 0.01 || !cache.position) {
                  cache.lastUpdateSecond = currentTimeInSeconds;

                  // 获取无人机在当前时间的位置
                  const dronePosition = droneEntity.position.getValue(time);
                  if (!dronePosition) return undefined;

                  // 计算无人机的地理坐标（经纬度和高度）
                  const cartographic = Cesium.Cartographic.fromCartesian(dronePosition);
                  const longitude = cartographic.longitude;
                  const latitude = cartographic.latitude;
                  const height = cartographic.height || 0;

                  // 缓存高度
                  cache.height = height;

                  const maxHeight = 300; // 高度阈值
                  const maxRadius = 100; // 最大底部半径

                  // 线性插值计算底部半径
                  cache.bottomRadius = height >= maxHeight ?
                    maxRadius :
                    (height / maxHeight) * maxRadius;

                  // 计算地面点位置（同样的经纬度，但高度为0）
                  const groundPosition = Cesium.Cartesian3.fromRadians(
                    longitude,
                    latitude,
                    0
                  );

                  // 计算四棱锥的中心点（地面点和无人机位置的中点）
                  cache.position = Cesium.Cartesian3.midpoint(
                    groundPosition,
                    dronePosition,
                    new Cesium.Cartesian3()
                  );

                  // 计算从地心指向无人机的方向
                  const up = Cesium.Cartesian3.normalize(dronePosition, new Cesium.Cartesian3());

                  // 计算东方向作为参考
                  const east = Cesium.Cartesian3.cross(
                    Cesium.Cartesian3.UNIT_Z,
                    up,
                    new Cesium.Cartesian3()
                  );
                  Cesium.Cartesian3.normalize(east, east);

                  // 计算北方向
                  const north = Cesium.Cartesian3.cross(
                    up,
                    east,
                    new Cesium.Cartesian3()
                  );

                  // 创建从局部ENU坐标系到ECEF坐标系的旋转
                  const rotation = new Cesium.Matrix3();
                  Cesium.Matrix3.setColumn(rotation, 0, east, rotation);
                  Cesium.Matrix3.setColumn(rotation, 1, north, rotation);
                  Cesium.Matrix3.setColumn(rotation, 2, up, rotation);

                  cache.orientation = Cesium.Quaternion.fromRotationMatrix(rotation);
                }

                return cache.position;
              }, false),

              orientation: new Cesium.CallbackProperty((time) => {
                return this._pyramidCache[device.id]?.orientation;
              }, false),

              cylinder: {
                // 使用缓存的高度值
                length: new Cesium.CallbackProperty((time) => {
                  return this._pyramidCache[device.id]?.height || 0;
                }, false),
                topRadius: 0,
                // 使用动态计算的底部半径
                bottomRadius: new Cesium.CallbackProperty((time) => {
                  return this._pyramidCache[device.id]?.bottomRadius || 0;
                }, false),
                material: new Cesium.Color(0.0, 0.7, 0.9, 0.5),
                slices: 4,
                outline: false,
                numberOfVerticalLines: 4
              }
            });
          }

        });

        // 加载静态轨迹线数据
        routesData.forEach(route => {
          if (route.path && route.path.length > 0) {
            const routeColor = Cesium.Color.fromBytes(
              Math.floor(route.color[0] * 255),
              Math.floor(route.color[1] * 255),
              Math.floor(route.color[2] * 255),
              Math.floor(route.color[3] * 255)
            );

            // 创建基础路线
            this.viewer.entities.add({
              id: route.routeId,
              polyline: {
                positions: route.path.map(point => Cesium.Cartesian3.fromDegrees(point[0], point[1], point[2])),
                width: 8,
                material: new Cesium.PolylineOutlineMaterialProperty({
                  color: routeColor,
                  // outlineColor: Cesium.Color.WHITE,
                  outlineWidth: 1
                })
              }
            });
            // 点渲染 ⚠️/🔄
            this.renderEventPoints(this.eventPoints);


            // 创建流动箭头效果
            // this.viewer.entities.add({
            //   id: `${route.routeId}-arrow`,
            //   polyline: {
            //     positions: route.path.map(point => Cesium.Cartesian3.fromDegrees(point[0], point[1], point[2])),
            //     width: 5,
            //     material: new Cesium.PolylineDashMaterialProperty({
            //       color: Cesium.Color.WHITE,
            //       gapColor: Cesium.Color.TRANSPARENT,
            //       dashLength: 16.0,
            //       dashPattern: 255, // 二进制模式: 11111111
            //     })
            //   }
            // });
          }
        });

        // 渲染场景
        this.viewer.scene.requestRender();

        // 大桥模型
    const bridgeEntity = this.viewer.entities.add({
      name: "bridge",
      position: Cesium.Cartesian3.fromDegrees(116.033843,39.537097, 15), // 经纬度 + 高度（示例：上海附近）
      model: {
        uri: "models/bridge2.glb",  // 你的大桥 glb 模型文件路径
        scale: 1.9,                  // 缩放比例
        minimumPixelSize: 30,       // 最小像素大小，避免模型太远消失
        maximumScale: 2000,          // 最大放大倍数
        runAnimations: false         // 如果模型有动画，可以控制是否播放
      },
      orientation: Cesium.Transforms.headingPitchRollQuaternion(
  Cesium.Cartesian3.fromDegrees(116.033843,39.537097,15),
  new Cesium.HeadingPitchRoll(
    Cesium.Math.toRadians(87),   // heading (绕Z轴旋转)
    0.0,                         // pitch
    0.0                          // roll
  )
)

    });

    
    //this.viewer.trackedEntity = bridgeEntity;
    
    


        // 地图点击事件
        const handler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
        handler.setInputAction((click) => {
          const pickedObject = this.viewer.scene.pick(click.position);
          const handler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
          handler.setInputAction((click) => {
            const pickedObject = this.viewer.scene.pick(click.position);
            if (Cesium.defined(pickedObject) && pickedObject.id) {
              const id = pickedObject.id.id;

              const position = entity.position.getValue(this.viewer.clock.currentTime);
              if (position) {
                this.viewer.camera.flyTo({
                  destination: position,
                  orientation: { heading: 0, pitch: -0.5, roll: 0 },
                  duration: 1.5,
                  complete: () => {
                    //  飞行完成后再启用追踪视角
                    this.viewer.trackedEntity = entity;
                    console.log(`Now tracking ${id}`);
                  }
                });

                // 立即更新选中状态（无视角跳变）
                this.focusedDeviceId = id;
                this.currentDevice = device;
                this.currentDocker = null;

                this.handleAction({ type: 'show-detail', data: { id } });
              } else {
                console.warn(`No position found at current time for device: ${id}`);
              }
            }
          }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
      } catch (error) {
        console.error('Error loading map:', error);
        // 地图初始化失败时直接退出，避免继续访问未创建的 viewer 导致页面崩溃
        return;
      }
      const handler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);

      handler.setInputAction((click) => {
  // 根据鼠标点击位置，计算椭球上的笛卡尔坐标
  const cartesian = this.viewer.camera.pickEllipsoid(
    click.position,
    this.viewer.scene.globe.ellipsoid
  );

  if (cartesian) {
    // 转换成经纬度
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
    const lon = Cesium.Math.toDegrees(cartographic.longitude).toFixed(6);
    const lat = Cesium.Math.toDegrees(cartographic.latitude).toFixed(6);
    const height = cartographic.height.toFixed(2);

    console.log(`点击位置: [${lon},${lat}]`);
  } else {
    console.warn("没有拾取到地球表面（可能点击在空背景上）");
  }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);


    },




    resetToInitialView() {
      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(115.579662, 38.870149, 70000.0),
        orientation: { heading: 0, pitch: -Cesium.Math.PI / 2, roll: 0 },
        duration: 2.0,
        complete: () => {
          console.log('Reset to initial view, camera height:', this.viewer.camera.positionCartographic.height, 'meters');
        }
      });
      this.focusedDeviceId = null;
      this.currentDevice = null;
      this.currentDocker = null;
    },
    focusOnDevice(deviceId, pitch = -0.5) {
      if (this.focusedDeviceId === deviceId) {
        this.resetToInitialView();
        return;
      }

      const entity = this.viewer.entities.getById(deviceId);
      if (entity) {
        // 设置追踪
        this.viewer.trackedEntity = entity;

        this.focusedDeviceId = deviceId;
        this.currentDevice = this.devices.find(device => device.id === deviceId);
        this.currentDocker = null;
      } else {
        console.warn(`Device entity ${deviceId} not found`);
      }
    },


    focusOnDocker(dockerId, pitch = -0.5) {
      if (this.focusedDeviceId === dockerId) {
        this.resetToInitialView();
        return;
      }
      const position = this.dockerPositions.get(dockerId);
      if (position) {
        this.viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(position[0], position[1] - 0.01, 800.0),
          orientation: { heading: 0, pitch, roll: 0 },
          duration: 2.0,
          complete: () => {
            console.log('Focus docker camera height:', this.viewer.camera.positionCartographic.height, 'meters');
          }
        });
        this.focusedDeviceId = dockerId;
        this.currentDocker = this.dockers.find(docker => docker.id === dockerId);
        this.currentDevice = null;
      } else {
        console.warn(`Docker ID ${dockerId} not found`);
      }
    },



    // 选择当前机场的关联无人机
    selectDrone(droneId) {
      this.selectedDrone = this.devices.find(device => device.id === droneId);
    },

    // 处理标签点击
    handleDeviceSelect(deviceId) {
      this.focusOnDevice(deviceId);
    },

    //点击事件
    handleAction({ type, data }) {
      switch (type) {
        case 'show-detail':
          if (!data || !data.id) {
            this.$message.error('无效的设备数据');
            return;
          }
          console.log(`Handling show-detail for device: ${data.id}`);

          // ✅ 打开设备详情，但不追踪
          const idStr = String(data.id);
          this.currentDevice = this.devices.find(d => String(d.id) === idStr) || null;
          this.currentDocker = null;
          this.focusedDeviceId = idStr;

          // ✅ 高亮该无人机对应的路线（不对焦、不追踪）
          this.highlightRouteForUav(idStr);

          break;

        case 'show-docker-detail':
          if (!data || !data.id) {
            this.$message.error('无效的机场数据');
            return;
          }
          console.log(`Handling show-docker-detail for docker: ${data.id}`);
          this.focusOnDocker(data.id);
          break;

        case 'close-detail':
          this.currentDevice = null;
          this.currentDocker = null;
          this.focusedDeviceId = null;
          break;

        //一键调度逻辑
        case 'dispatch':
          if (data.status === '空闲中' || data.status === '待命') {
            if (data.battery < 10) {
              this.$message.error('电量过低，无法调度');
              return;
            }
            this.modalDevice = { ...data, ...this.flightData };
            this.modalType = 'DispatchSettings';
            this.showModal = true;
          } else if (data.status === '工作中') {
            const priority = data.priority;

            if (priority === '高') {
              this.$message.warning('任务紧急，不能调度');
              return;
            }

            if (priority === '中') {
              this.$confirm('该设备正在执行中等紧急任务，确定要强制调度吗？', '提示', {
                confirmButtonText: '确认调度',
                cancelButtonText: '取消',
                type: 'warning'
              }).then(() => {
                this.modalDevice = { ...data, ...this.flightData };
                this.modalType = 'DispatchSettings';
                this.showModal = true;
              }).catch(() => {
                // 用户取消
              });
            }

            if (priority === '低') {
              this.modalDevice = { ...data, ...this.flightData };
              this.modalType = 'DispatchSettings';
              this.showModal = true;
            }
          } else {
            this.$message.error('设备当前状态无法调度');
          }
          break;

        //一键起飞逻辑
        case 'takeoff':
          if (data.associatedDevices && data.associatedDevices.length > 0) {
            const uavId = data.associatedDevices[0];
            const uav = this.devices.find(d => d.id === uavId);

            if (!uav) {
              this.$message.error('未找到关联的无人机信息');
              return;
            }

            if (uav.status !== '待命') {
              this.$message.warning('当前关联无人机不在待命状态，无法起飞');
              return;
            }

            if (uav.battery < 20) {
              this.$message.warning('电量不足，无法起飞');
              return;
            }

            // 起飞条件满足，打开 TakeOffSettings 弹窗
            this.modalDevice = { ...uav, ...this.flightData };
            this.modalType = 'TakeOffSettings';
            this.showModal = true;

          } else {
            this.$message.warning('当前机场未关联可用的无人机');
          }
          break;

        // 调度设置弹窗确认，弹出 DispatchMonitor
        case 'confirm-dispatch':
          this.modalDevice = { ...data };
          this.modalType = 'DispatchMonitor';
          this.showModal = true;
          break;

        // 起飞设置弹窗确认后
        case 'confirm-takeoff':
          this.modalDevice = { ...data };
          this.cockpitMode = 'takeoff'; // 设置为一键起飞模式
          this.isCockpitView = true;

          console.log('一键起飞模式，数据来源: dockers.json -> devices.json');

          // 保持原有逻辑：使用机场关联的无人机
          if (this.currentDocker && this.currentDocker.associatedDevices && this.currentDocker.associatedDevices.length > 0) {
            const firstDroneId = this.currentDocker.associatedDevices[0];
            this.selectedDrone = this.devices.find(device => device.id === firstDroneId);
            console.log('选择的无人机:', this.selectedDrone);
          }
          break;

        case 'enter-control-panel':
          if (data && data.id) {
            this.cockpitMode = 'control-panel';
            this.modalDevice = { ...data };
            this.isCockpitView = true;         // ⬅️ 先切到 cockpit（会触发上面的 watch）
            this.selectedDrone = data;
            this.currentDocker = null;

            this.$nextTick(() => {
              const drone = this.viewer?.entities.getById(data.id);
              if (drone) {
                // 设定相机相对实体的观察位置
                drone.viewFrom = new Cesium.Cartesian3(800, 1500, 400);
                // 追踪实体
                this.viewer.trackedEntity = drone;
              }
              // 再次适配尺寸，保证追踪时画布是新尺寸
              this.viewer?.resize();
              this.viewer?.scene.requestRender();
            });
          }
          break;

        case 'exit-cockpit-view':
          console.log('退出中控台，返回普通地图视图');
          this.isCockpitView = false;
          this.cockpitMode = null;
          this.selectedDrone = null;
          this.currentDocker = null;
          this.viewer.trackedEntity = null; // 取消追踪
          break;





        case 'close-modal':
        case 'cancel':
          this.showModal = false;
          this.modalType = null;
          this.modalDevice = null;
          break;
        case 'select-on-map':
          console.log(`处理地图选点: ${data.field}`);
          break;
        case 'upload-waypoints':
          console.log('处理航点文件:', data.file);
          break;
        default:
          console.warn('未知操作:', type);

      }
    },

    toggleCockpitView() {
      this.isCockpitView = !this.isCockpitView;
      console.log('切换视图: ', this.isCockpitView);
    },
    //点事件
    renderEventPoints(points) {
      if (!this.viewer || !Array.isArray(points)) return;

      // 清理旧实体
      (this._eventEntityIds || []).forEach(id => {
        const e = this.viewer.entities.getById(id);
        e && this.viewer.entities.remove(e);
      });
      this._eventEntityIds = [];

      points.forEach(p => {
        let iconUrl = "/icons/default-icon.svg";  // 默认图标

        // 根据事件类型设置图标
        if (p.type === "congestion") iconUrl = "/icons/congestion.svg";
        if (p.type === "bridge") iconUrl = "/icons/bridge.svg";
        if (p.type === "danger") iconUrl = "/icons/danger.svg";

        // 添加实体位置
        const ent = this.viewer.entities.add({
          id: p.id,
          name: p.name,
          position: Cesium.Cartesian3.fromDegrees(
            p.position[0],
            p.position[1],
            p.position[2] || 0
          ),
          billboard: {
            image: iconUrl,
            width: 32,
            height: 32,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            scale: 0.8
          },
          // description: `<b>${p.name}</b>` // 事件点的描述
        });

        // 将添加的实体 ID 存储，以便以后清理
        this._eventEntityIds.push(ent.id);

        // 添加虚线从事件点到地面
        const dashLineId = `dash-line-${p.id}`;
        const dashLine = this.viewer.entities.add({
          id: dashLineId,
          name: `${p.name}虚线标记`,
          polyline: {
            positions: new Cesium.CallbackProperty(() => {
              // 获取事件点的当前位置
              const eventPosition = Cesium.Cartesian3.fromDegrees(
                p.position[0],
                p.position[1],
                p.position[2] || 0
              );

              // 创建地面点（相同经纬度，高度为0）
              const cartographic = Cesium.Cartographic.fromCartesian(eventPosition);
              const groundPosition = Cesium.Cartesian3.fromRadians(
                cartographic.longitude,
                cartographic.latitude,
                0
              );

              return [eventPosition, groundPosition];
            }, false),
            width: 5,
            material: new Cesium.PolylineDashMaterialProperty({
              color: Cesium.Color.WHITE.withAlpha(0.7),
              dashLength: 12,
              dashPattern: 255 // 二进制: 00001111 (4像素显示，4像素空白)
            })
          }
        });

        // 存储虚线实体的ID以便后续清理
        this._eventEntityIds.push(dashLineId);
      });

      // 刷新视图
      this.viewer.scene.requestRender();
    },



    // ====== 高亮路线 ======
    highlightRouteForUav(uavId) {
      if (!this.viewer) return;

      const idStr = String(uavId);

      // 先清掉之前的高亮
      if (this._highlightRouteEntity) {
        this.viewer.entities.remove(this._highlightRouteEntity);
        this._highlightRouteEntity = null;
      }

      // 找到该无人机的路线
      const route = (routesData || []).find(r => String(r.uavId) === idStr);
      if (!route || !Array.isArray(route.path) || route.path.length === 0) {
        console.warn('[highlightRouteForUav] 未找到路线或路径为空, uavId =', idStr);
        return;
      }

      // 构建 positions
      const positions = route.path.map(p =>
        Cesium.Cartesian3.fromDegrees(p[0], p[1], p[2] || 0)
      );
      

      // 叠加高亮线（不改变你原来画的基础路线）
      this._highlightRouteEntity = this.viewer.entities.add({
        id: `highlight-${route.routeId}`,
        polyline: {
          positions,
          width: 15,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.3,
            color: Cesium.Color.GREEN
          }),
          clampToGround: false
        }
      });

      // 取消追踪（只高亮，不跟随）
      this.viewer.trackedEntity = undefined;

      // === 新增：把相机飞到“中间点” ===
      const midIdx = Math.floor(route.path.length / 2);
      const mid = route.path[midIdx];
      const midLon = mid[0];
      const midLat = mid[1];
      const midAlt = mid[2] || 0;

      // 计算一个合适的相机高度（用路径高度和一个最小高度兜底）
      const maxAlt = route.path.reduce((m, p) => Math.max(m, p[2] || 0), 0);
      const cameraAlt = Math.max(10000, maxAlt + 1600); // 你可以按需调整

      this.viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(midLon, midLat, cameraAlt + 20000),
        orientation: {
          heading: 0,
          pitch: -Cesium.Math.toRadians(90), // 俯视 45°
          roll: 0
        },
        duration: 1.5
      });

      // 强制渲染
      this.viewer.scene.requestRender();
    },

  },
};

</script>

<style scoped>
.map-container-wrapper {
  position: relative;
  width: 100%;
  height: calc(100vh - 60px);
  display: grid;
  /* 两列：左 1 份，右 2 份；共 12 行 */
  grid-template-columns: 1fr 2fr;
  grid-template-rows: repeat(12, 1fr);
  gap: 10px;
  background-color: #2c2f38;
  overflow: hidden;
}

#map-container.normal-map {
  grid-column: 1 / 3;
  grid-row: 1 / 13;
}

#map-container.cockpit-map {
  grid-column: 1 / 2;
  grid-row: 1 / 13;
  border: 1px solid #222;
  border-radius: 8px;
  overflow: hidden;
}

.cockpit-layout {
  grid-column: 1 / 3;
  grid-row: 1 / 13;
  display: contents;
}

.cockpit-top-right {
  grid-column: 2 / 3;
  grid-row: 1 / 7;
}

.cockpit-bottom-right {
  grid-column: 2 / 3;
  grid-row: 9 / 13;
  background-color: #2a2e34;
  border-radius: 12px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, .3);
  overflow: auto;
  padding: 10px;
}

/* .cockpit-layout.takeoff-mode .cockpit-bottom-right {
  grid-column: 2 / 3;
  grid-row: 9 / 13;
  background-color: #2a2e34;
  border-radius: 12px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, .3);
  overflow: hidden;
  padding: 0px;

} */


.cockpit-top-left {
  grid-column: 1 / 2;
  grid-row: 1 / 3;
  display: none;
}



.cockpit-bottom-left {
  grid-column: 1 / 2;
  grid-row: 1 / 13;
  pointer-events: none;
  /* 防止遮挡地图交互 */
  background: transparent;
}


#map-container canvas {
  display: block;
}

.right-panel {
  position: absolute;
  right: 0;
  top: 0;
  width: 270px;
  height: 100%;
}

@media (max-width: 992px) {
  .right-panel {
    width: 280px;
  }
}

.detail-panel {
  position: absolute;
  left: 20px;
  top: 20px;
  width: 400px;
  z-index: 2000;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 3000;
}

.modal-overlay.full-screen {
  background: none;
}

.modal-overlay.full-screen .modal-content {
  width: 100%;
  height: 100%;
  border-radius: 0;
}

.modal-content {
  background: white;
  padding: 20px;
  border-radius: 8px;
  width: 400px;
}


.cockpit-bottom-right .control-buttons {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
}

button {
  background-color: #ff5c5c;
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
}

button:hover {
  background-color: #ff3b3b;
}

.map-legend {
  position: absolute;
  left: 12px;
  bottom: 150px;
  z-index: 1;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 15px;
  line-height: 18px;
}

.legend-row {
  display: flex;
  align-items: center;
  color: #ffffff;
  z-index: 1;
  margin-top: 5px;
}

.legend-icon {
  width: 20px;
  height: 20px;
  margin-right: px;
}


</style>
