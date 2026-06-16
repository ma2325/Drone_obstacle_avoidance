<template>
  <div class="map-container-wrapper">
    <!-- 地图容器 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 设备详情 -->
    <DeviceDetail v-if="currentDevice" :device="currentDevice" @action="handleAction" class="detail-panel" />

    <!-- 右侧面板 -->
    <RightPanel class="right-panel" @action="handleAction" :devices="devices" />

    <!-- 弹窗 -->
    <div v-if="showModal" class="modal-overlay" :class="{ 'full-screen': modalType === 'Cockpit' }">
      <div class="modal-content">
        <component :is="modalType" :device="modalDevice" @action="handleAction" />
      </div>
    </div>
  </div>
</template>

<script>
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import RightPanel from '../Home/RightPanel.vue';
import DeviceDetail from '../Home/DeviceDetail.vue';
import TakeOffSettings from '../Home/TakeOffSettings.vue';
import Cockpit from '../Home/Cockpit.vue';
import devices from '@/test-data/devices.json';
import flightData from '@/test-data/flightData.json';
import cesiumCoords from '@/assets/jingShiCoords.json';//轨迹点JSON路径
import stations from '@/assets/station.json';  // 你的站点JSON路径
window.CESIUM_BASE_URL = '/node_modules/cesium/Build/Cesium/';

//添加一个地理距离计算函数 + 给京石高速每个轨迹点匹配最近的收费站。
// 计算两点间 Haversine 距离（单位：米）
function getDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000; // 地球半径 (m)
  const toRad = deg => deg * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// 获取最近收费站名称
function findNearestStation(lon, lat, stationList) {
  let minDist = Infinity;
  let nearestStation = null;
  for (const station of stationList) {
    const dist = getDistance(lat, lon, station.lat, station.lng);
    if (dist < minDist) {
      minDist = dist;
      nearestStation = station.name;
    }
  }
  // 如果最近站点距离太远，就返回 null
  return minDist < maxDistance ? nearestStation : null;
}


export default {
  components: {
    RightPanel,
    DeviceDetail,
    TakeOffSettings,
    Cockpit
  },
  data() {
    return {
      map: null,
      currentDevice: null,
      showModal: false,
      modalType: null,
      modalDevice: null,
      devices,
      flightData
    };
  },
  mounted() {
    console.log(document.getElementById('map-container'))
    console.log('Cesium静态资源根路径:', window.CESIUM_BASE_URL);
    console.log('Cesium版本:', Cesium.VERSION);
    this.loadMap();

  },
  methods: {
    async loadMap() {
      try {
        // 【1】可选：设置 Cesium Ion 的 AccessToken
        Cesium.Ion.defaultAccessToken =
          'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJiNzEzZjEzYi0wNjg5LTQ0OTMtYWZkNS1iNTVjOTRmMDMwNzEiLCJpZCI6MzIwMjIwLCJpYXQiOjE3NTIyMDAxMzd9.oytvSPRNdHLhiI2KxkAAU8Peyb4bX0OaZFlZE4MDHv8';

        // 【2】初始化 Viewer
        this.viewer = new Cesium.Viewer('map-container', {
          imageryProvider: new Cesium.UrlTemplateImageryProvider({
            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            subdomains: ['a', 'b', 'c']
          }),
          terrainProvider: new Cesium.EllipsoidTerrainProvider() // 无地形
        });

        // 【3】设定初始视角（北京地区）
        this.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(116.40, 39.90, 200000.0)
        });

        // 【4】添加设备标记（蓝色圆点 + 名称标签）
        this.devices.forEach(device => {
          this.viewer.entities.add({
            id: device.id,
            name: device.name,
            position: Cesium.Cartesian3.fromDegrees(device.position[0], device.position[1]),
            point: {
              pixelSize: 10,
              color: Cesium.Color.BLUE
            },
            label: {
              text: device.name,
              font: '14px sans-serif',
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              outlineWidth: 2,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -15)
            }
          });
        });

        // 【5】添加收费站标记（橙色圆点 + 白字标签）
        stations.forEach(station => {
          this.viewer.entities.add({
            id: station.name,
            name: station.name,
            position: Cesium.Cartesian3.fromDegrees(station.lng, station.lat),
            point: {
              pixelSize: 12,
              color: Cesium.Color.ORANGE,
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 2
            },
            label: {
              text: station.name,
              font: '14px sans-serif',
              style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              outlineWidth: 2,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -15),
              fillColor: Cesium.Color.WHITE
            }
          });
        });

        // 【6】按最近收费站对轨迹进行分段（分段绘制）
        const pointCount = cesiumCoords.length / 2;
        const segments = [];
        let currentSegment = [];
        let lastStation = null;

        for (let i = 0; i < pointCount; i++) {
          const lon = cesiumCoords[i * 2];
          const lat = cesiumCoords[i * 2 + 1];
          const station = findNearestStation(lon, lat, stations,1000);

          // 若收费站发生切换，则分段保存
          if (lastStation !== null && station !== lastStation) {
            if (currentSegment.length >= 4) {
              segments.push({
                from: lastStation,
                to: station,
                coords: currentSegment
              });
            }
            currentSegment = [];
          }

          currentSegment.push(lon, lat);
          lastStation = station;
        }

        // 最后一段也要收尾
        if (currentSegment.length >= 4) {
          segments.push({
            from: lastStation,
            to: lastStation,
            coords: currentSegment
          });
        }

        // 【7】绘制每一段轨迹（不同颜色区分）
        const colorList = [
          Cesium.Color.RED,
          Cesium.Color.ORANGE,
          Cesium.Color.YELLOW,
          Cesium.Color.GREEN,
          Cesium.Color.BLUE,
          Cesium.Color.CYAN,
          Cesium.Color.PURPLE,
          Cesium.Color.MAGENTA
        ];

        segments.forEach((segment, index) => {
          this.viewer.entities.add({
            name: `段落: ${segment.from} → ${segment.to}`,
            polyline: {
              positions: Cesium.Cartesian3.fromDegreesArray(segment.coords),
              width: 5,
              material: colorList[index % colorList.length]
            }
          });
        });

        // ❌ 注意：不要再添加整条统一轨迹，否则会覆盖分段显示
        // this.viewer.entities.add({
        //   id: 'jingShiHighwayPolyline',
        //   name: '京石高速轨迹',
        //   polyline: {
        //     positions: Cesium.Cartesian3.fromDegreesArray(cesiumCoords),
        //     width: 5,
        //     material: Cesium.Color.RED
        //   }
        // });

        // 【8】聚焦至所有实体（自动缩放视角）
        this.viewer.zoomTo(this.viewer.entities);

      } catch (error) {
        console.error('Cesium 地图加载失败:', error);
        this.$message?.error?.('地图加载失败，请稍后重试');
      }
    },

    handleAction({ type, data }) {
      switch (type) {
        case 'show-detail':
          if (!data || !data.id) {
            this.$message.error('无效的设备数据');
            return;
          }
          this.currentDevice = data;
          this.viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(data.position[0], data.position[1], 50000)
          })
            ;
          break;
        case 'close-detail':
          this.currentDevice = null;
          break;
        case 'takeoff':
          if (data.status !== '空闲中') {
            this.$message.error('设备工作中，无法起飞');
            return;
          }
          if (data.battery < 10) {
            this.$message.error('电量不足，无法起飞');
            return;
          }
          this.modalDevice = { ...data, ...this.flightData };
          this.modalType = 'TakeOffSettings';
          this.showModal = true;
          break;
        case 'confirm-takeoff':
          if (!data.latitude || !data.longitude || !data.deviceId) {
            this.$message.error('参数无效，请检查');
            return;
          }
          this.modalDevice = { ...this.modalDevice, params: data };
          this.modalType = 'Cockpit';
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
    }
  }
}
</script>

<style scoped>
.map-container-wrapper {
  position: relative;
  width: 100%;
  height: calc(100vh - 60px);
  /* 减去顶部导航栏高度 */
  padding: 0;
  overflow: hidden;
}

#map-container {
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
}

#map-container canvas {
  display: block;
}


.right-panel {
  position: absolute;
  right: 0;
  top: 0;
  width: 300px;
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
  width: 300px;
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
</style>