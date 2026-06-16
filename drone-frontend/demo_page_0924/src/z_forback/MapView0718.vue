<template>
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- 地图容器 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 右侧浮动卡片 -->
    <DroneLine 
      :device="deviceInfo" 
      @detail="handleDetail" 
      class="right-card-overlay"
    />
  </div>
</template>

<script>
import { onMounted } from 'vue'
import * as Cesium from 'cesium';
import stations from '@/assets/station.json';           // 站点数据，包含经纬度和名称
import segmentedRoutes from '@/assets/segmented_route.json'; // 路线段数据，包含起止站点和坐标
import DroneLine from '../Map/DroneLine.vue'; // 路线段数据，包含起止站点和坐标

export default {
  components: { DroneLine },
  data() {
    return {
      viewer: null,
      deviceInfo: {
        id: 'M3D-001',
        status: '待命',
        battery: '85%',
        position: '东经115.91° 北纬39.01°',
      },
    };
  },
  mounted() {
    this.loadMap();
  },
  methods: {
    loadMap() {
      // 创建 Cesium Viewer，使用纯球体地形（无外部地形服务）
      this.viewer = new Cesium.Viewer('map-container', {
        timeline: false,
        animation: false,
        shouldAnimate: true,
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          subdomains: ['a', 'b', 'c'],
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(), // 纯球体地形，非真实高程
      });

      // 禁用昼夜光照，避免阴影影响视觉
      this.viewer.scene.globe.enableLighting = false;

      // 设置摄像头初始视角（经度，纬度，高度）
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(115.90, 39.00, 350000.0),
      });

      // 允许用户操作，旋转、拖拽和缩放
      const controller = this.viewer.scene.screenSpaceCameraController;
      controller.enableRotate = true;
      controller.enableTilt = true;
      controller.enableLook = true;
      controller.enableZoom = true;
      controller.enableTranslate = true;

      // 添加动态站点标记
      stations.forEach(station => {
        const getPixelSize = (time) => {
          const seconds = Cesium.JulianDate.toDate(time).getTime();
          return 6 + 6 * Math.abs(Math.sin(seconds / 2000 * Math.PI));
        };
        const getColor = (time) => {
          const seconds = Cesium.JulianDate.toDate(time).getTime();
          const alpha = 0.4 + 0.6 * Math.abs(Math.sin(seconds / 2000 * Math.PI));
          return Cesium.Color.ORANGE.withAlpha(alpha);
        };

        this.viewer.entities.add({
          id: station.name,
          name: station.name,
          position: Cesium.Cartesian3.fromDegrees(station.lng, station.lat),
          point: {
            pixelSize: new Cesium.CallbackProperty(getPixelSize, false),
            color: new Cesium.CallbackProperty(getColor, false),
          },
          label: {
            text: station.name,
            font: 'bold 14px Microsoft YaHei',
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.fromCssColorString('#185ABD'),
            outlineWidth: 3,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -15),
          }
        });
      });


      // 添加路线段线条
      segmentedRoutes.forEach((segment, index) => {
        const total = segmentedRoutes.length;
        const hueStart = 0.55;
        const hueEnd = 0.7;
        const hue = hueStart + (index / total) * (hueEnd - hueStart);

        this.viewer.entities.add({
          id: `route-segment-${index}`,
          name: `${segment.startStation} - ${segment.endStation}`,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(segment.coords),
            width: 6,
            material: Cesium.Color.fromHsl(hue, 0.65, 0.5, 0.7),
          },
          label: {
            text: `${segment.startStation} → ${segment.endStation}`,
            font: '16px "Microsoft YaHei"',
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.fromCssColorString('#1890bd'),
            outlineColor: Cesium.Color.BLUE.withAlpha(0.7),
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(0, -10),
            verticalOrigin: Cesium.VerticalOrigin.TOP,
          }
        });
      });
    },
    
    handleDetail() {
      console.log('查看详情:', this.deviceInfo);
      // 实现查看详情逻辑，例如跳转或弹窗
    },
  },
};
  
</script>

<style>
#map-container {
  width: 100%;
  height: 100vh; /* 高度撑满视窗 */
}
</style>
