<template>
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- 主地图容器 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 启用/关闭打点按钮 -->
    <button 
      @click="toggleClickToAddPoint" 
      style="position: absolute; bottom: 10px; left: 10px; z-index: 999;"
    >
      {{ clickPointEnabled ? '关闭打点' : '启用打点' }}
    </button>

    <!-- 小窗同步视角 -->
    <div 
      id="mini-view" 
      style="position: absolute; top: 30px; left: 10px; width: 220px; height: 160px; border: 2px solid #ccc;"
    ></div>

    <!-- 浮动卡片组件 -->
    <DroneLine 
      :device="deviceInfo" 
      @detail="handleDetail" 
      class="right-card-overlay"
    />
  </div>
</template>

<script>
import * as Cesium from 'cesium';
import stations from '@/assets/station.json';
import DroneLine from '../Map/DroneLine.vue';

export default {
  components: { DroneLine },
  data() {
    return {
      viewer: null,
      miniViewer: null,
      clickPointEnabled: false,       // 打点开关状态
      clickHandler: null,             // 监听器引用
      deviceInfo: {},                 // 你的浮动卡片数据，自己初始化
      draggingEntity: null,
      handler: null,
    };
  },
  mounted() {
    this.loadMap();
  },
  methods: {
    loadMap() {
      // 初始化主地图
      this.viewer = new Cesium.Viewer('map-container', {
        timeline: false,
        animation: false,
        shouldAnimate: true,
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          subdomains: ['a', 'b', 'c'],
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      });

      this.viewer.scene.globe.enableLighting = false;

      // 设置初始视角
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(115.90, 39.00, 3000.0),
      });

      // 添加站点点位
      stations.forEach(station => {
        this.viewer.entities.add({
          id: station.name,
          position: Cesium.Cartesian3.fromDegrees(station.lng, station.lat, station.alt || 0),
          point: {
            pixelSize: 8,
            color: Cesium.Color.ORANGE.withAlpha(0.8),
          },
          label: {
            text: station.name,
            font: 'bold 14px Microsoft YaHei',
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLUE,
            outlineWidth: 3,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -15),
          }
        });
      });

      // 添加观察点和视野锥
      const obsLng = 115.905;
      const obsLat = 39.005;
      const obsAlt = 5000;
      const obsPos = Cesium.Cartesian3.fromDegrees(obsLng, obsLat, obsAlt);

      this.viewer.entities.add({
        id: 'observe-point',
        position: obsPos,
        point: {
          pixelSize: 10,
          color: Cesium.Color.RED.withAlpha(0.9),
        },
        label: {
          text: '观察点',
          font: 'bold 14px Microsoft YaHei',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -20),
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM
        }
      });

      // 添加视野锥体
      this.viewer.entities.add({
        name: '观察点视野锥体',
        position: obsPos,
        orientation: Cesium.Transforms.headingPitchRollQuaternion(
          obsPos,
          new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(180), Cesium.Math.toRadians(-30), 0)
        ),
        customSensor: new Cesium.CustomSensorVolume({
          radius: 1000.0,
          xHalfAngle: Cesium.Math.toRadians(20),
          yHalfAngle: Cesium.Math.toRadians(15),
          material: Cesium.Color.GREEN.withAlpha(0.3),
          lineColor: Cesium.Color.LIME.withAlpha(0.6),
        })
      });

      // 初始化小窗视图
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

      // 小窗视角同步锁定观察点
      this.viewer.scene.postRender.addEventListener(() => {
        const observeEntity = this.viewer.entities.getById('observe-point');
        if (observeEntity) {
          const position = observeEntity.position.getValue(this.viewer.clock.currentTime);
          if (position) {
            this.miniViewer.camera.setView({
              destination: position,
              orientation: {
                heading: Cesium.Math.toRadians(180),
                pitch: Cesium.Math.toRadians(-30),
                roll: 0
              }
            });
          }
        }
      });
      
    },

    // 切换打点功能开关
    toggleClickToAddPoint() {
      if (!this.clickPointEnabled) {
        this.enableClickToAddPoint();
      } else {
        this.disableClickToAddPoint();
      }
      this.clickPointEnabled = !this.clickPointEnabled;
    },

    // 启用点击打点功能，监听地图左键点击
    enableClickToAddPoint() {
      if (this.clickHandler) return; // 已经启用

      this.clickHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);
      this.clickHandler.setInputAction((movement) => {
        const earthPosition = this.viewer.scene.pickPosition(movement.position);
        if (Cesium.defined(earthPosition)) {
          const cartographic = Cesium.Cartographic.fromCartesian(earthPosition);
          const lon = Cesium.Math.toDegrees(cartographic.longitude).toFixed(6);
          const lat = Cesium.Math.toDegrees(cartographic.latitude).toFixed(6);
          // alt 可用，按需显示
          // const alt = cartographic.height.toFixed(2);

          this.viewer.entities.add({
            position: earthPosition,
            point: {
              pixelSize: 10,
              color: Cesium.Color.YELLOW,
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 1,
            },
            label: {
              text: `(${lon}, ${lat})`,
              font: '12px sans-serif',
              fillColor: Cesium.Color.BLACK,
              showBackground: true,
              backgroundColor: Cesium.Color.WHITE.withAlpha(0.6),
              horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
              verticalOrigin: Cesium.VerticalOrigin.TOP,
              pixelOffset: new Cesium.Cartesian2(10, 0),
            }
          });
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },

    // 关闭打点功能，释放监听器
    disableClickToAddPoint() {
      if (this.clickHandler) {
        this.clickHandler.destroy();
        this.clickHandler = null;
      }
    },

    handleDetail() {
      console.log('查看详情');
    },
  },

  beforeUnmount() {
    // 组件卸载时，释放监听器和Cesium资源
    this.disableClickToAddPoint();
    if (this.viewer) {
      this.viewer.destroy();
      this.viewer = null;
    }
    if (this.miniViewer) {
      this.miniViewer.destroy();
      this.miniViewer = null;
    }
  }
};
</script>

<style>
#map-container {
  width: 100%;
  height: 100vh;
}
</style>
