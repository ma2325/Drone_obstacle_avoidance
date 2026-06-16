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
window.CESIUM_BASE_URL = '/node_modules/cesium/Build/Cesium/';

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
        // 可选：设置 Cesium Ion 的 AccessToken（不设置也能跑）
        Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJiNzEzZjEzYi0wNjg5LTQ0OTMtYWZkNS1iNTVjOTRmMDMwNzEiLCJpZCI6MzIwMjIwLCJpYXQiOjE3NTIyMDAxMzd9.oytvSPRNdHLhiI2KxkAAU8Peyb4bX0OaZFlZE4MDHv8'

        this.viewer = new Cesium.Viewer('map-container', {
          imageryProvider: new Cesium.UrlTemplateImageryProvider({
            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            subdomains: ['a', 'b', 'c']
          }),
          terrainProvider: new Cesium.EllipsoidTerrainProvider() // 无地形
        });



        // 设定初始视角
        this.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(116.40, 39.90, 200000.0)
        })

        // 添加设备点标记
        this.devices.forEach(device => {
          this.viewer.entities.add({
            id: device.id,
            name: device.name,
            position: Cesium.Cartesian3.fromDegrees(
              device.position[0], device.position[1]
            ),
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
          })
        })

        // 自动聚焦视角到设备
        this.viewer.zoomTo(this.viewer.entities)

      } catch (error) {
        console.error('Cesium 地图加载失败:', error)
        this.$message?.error?.('地图加载失败，请稍后重试')
      }
    }
    ,
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