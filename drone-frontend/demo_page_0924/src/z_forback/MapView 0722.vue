<template>
  <!-- 整个地图及控件的外层容器，宽高填满视口高度，relative定位方便绝对定位子元素 -->
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- Cesium 地图容器，填充父容器 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 开关点击地图打点的按钮，绝对定位于左下方，点击切换打点状态 -->
    <button @click="toggleClickToAddPoint" style="position: absolute; bottom: 50px; left: 10px; z-index: 999;">
      <!-- 根据打点开关状态显示文字 -->
      {{ clickPointEnabled ? '关闭打点' : '启用打点' }}
    </button>

    <!-- 生成飞行航线按钮，绝对定位在打点按钮上方，点击生成路径 -->
    <button @click="generateRouteFromPoints" style="position: absolute; bottom: 90px; left: 10px; z-index: 999;">
      生成飞行航线
    </button>

    <!-- 控制飞行动画播放暂停的按钮，绝对定位于左下角，点击切换动画状态 -->
    <button @click="toggleAnimation" style="position: absolute; bottom: 10px; left: 10px; z-index: 999;">
      <!-- 根据动画播放状态显示文字 -->
      {{ animationPlaying ? '暂停飞行动画' : '开始飞行动画' }}
    </button>

    <!-- 右上角显示小视图地图（迷你地图）容器，固定大小和边框 -->
    <div id="mini-view" style="position: absolute; top: 30px; left: 10px; width: 220px; height: 160px; border: 2px solid #ccc; z-index: 998;"></div>

    <!-- 自定义浮动卡片组件，用于显示无人机相关信息 -->
    <DroneLine :device="deviceInfo" @detail="handleDetail" class="right-card-overlay" />
  </div>
</template>

<script>
// 引入 Cesium 主要库
import * as Cesium from 'cesium';

// 导入站点数据，json 格式，包含经纬度和名称等信息
import stations from '@/assets/station.json';

// 导入分段航线数据，json 格式
import segmentedRoutes from '@/assets/segmented_route.json';

// 引入自定义无人机轨迹卡片组件
import DroneLine from '../Map/DroneLine.vue';

// 设置 Cesium Ion 访问令牌，替换为你自己的令牌
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3MjNmNDQ4Ny04MjBjLTQyYjgtOTA5Ni1lMjRhOTk5MGY3MjMiLCJpZCI6MzIzMzA3LCJpYXQiOjE3NTMwNjU0NzZ9.fD2b3-Hes2o3RrMfNg45qkW5x1-cK0Yqn-xLpxT8SAc';

export default {
  components: { DroneLine },
  data() {
    return {
      viewer: null,          // 主地图 Cesium Viewer 实例
      miniViewer: null,      // 迷你地图 Cesium Viewer 实例
      clickPointEnabled: false, // 是否启用地图点击打点功能
      clickHandler: null,    // Cesium 事件处理对象，监听地图点击
      deviceInfo: {},        // 传递给 DroneLine 组件的无人机设备信息
      animationPlaying: true, // 飞行动画播放状态开关
      dronePath: [],         // 飞行路径点集合
      startTime: null,       // 飞行动画开始时间
      stopTime: null,        // 飞行动画结束时间
      userPoints: [],        // 用户点击地图生成的点集合
    };
  },
  mounted() {
    // 组件挂载完成后加载地图
    this.loadMap();
  },
  methods: {
    // 初始化加载 Cesium 地图及相关元素
    loadMap() {
      // 创建主地图 Viewer，设置图层和地形
      this.viewer = new Cesium.Viewer('map-container', {
        timeline: true,       // 显示时间轴控件
        animation: true,      // 显示动画控件
        shouldAnimate: true,  // 是否默认动画播放
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',  // 使用 OpenStreetMap 瓦片地图
          subdomains: ['a', 'b', 'c'],  // 瓦片子域名，提升加载效率
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),  // 使用默认椭球体地形
        // terrainProvider: Cesium.createWorldTerrain() // 使用真实地形
      });

      // 关闭地球光照效果
      this.viewer.scene.globe.enableLighting = false;

      // 设置初始相机视角，中心经纬度115.83, 39.04，高度200米，视角俯仰-15度
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(115.83, 39.04, 200),
        orientation: {
          heading: Cesium.Math.toRadians(0),    // 航向角0度（正北）
          pitch: Cesium.Math.toRadians(-15),    // 俯仰角-15度（向下看）
          roll: 0.0
        }
      });

      // 遍历所有站点，添加实体点和标签显示
      stations.forEach((station) => {
        this.viewer.entities.add({
          id: station.name,  // 实体ID为站点名
          position: Cesium.Cartesian3.fromDegrees(station.lng, station.lat, station.alt || 0), // 经纬度及高度
          point: {
            pixelSize: 8,                       // 点大小
            color: Cesium.Color.ORANGE.withAlpha(0.8),  // 橙色半透明
          },
          label: {                             // 标签设置
            text: station.name,                // 标签文本为站点名
            font: 'bold 14px Microsoft YaHei', // 字体样式
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,  // 填充加轮廓
            fillColor: Cesium.Color.WHITE,    // 白色填充
            outlineColor: Cesium.Color.BLUE,  // 蓝色轮廓
            outlineWidth: 3,                   // 轮廓宽度
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM, // 标签底部对齐点
            pixelOffset: new Cesium.Cartesian2(0, -15),    // 垂直向上偏移15像素
          },
        });
      });

      // 创建迷你地图（小窗口）Viewer，关闭时间轴和动画控件，简化界面
      this.miniViewer = new Cesium.Viewer('mini-view', {
        timeline: false,
        animation: false,
        baseLayerPicker: false,  // 不显示底图切换控件
        imageryProvider: new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          subdomains: ['a', 'b', 'c'],
        }),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
      });

      // 每帧渲染后，同步主地图中特定实体（id=observe-point）的位置到迷你地图摄像机视角
      this.viewer.scene.postRender.addEventListener(() => {
        const observeEntity = this.viewer.entities.getById('observe-point');
        if (observeEntity) {
          const position = observeEntity.position.getValue(this.viewer.clock.currentTime);
          if (position) {
            this.miniViewer.camera.setView({
              destination: position,
              orientation: {
                heading: Cesium.Math.toRadians(180),  // 视角朝向180度（南）
                pitch: Cesium.Math.toRadians(-30),    // 俯视30度
                roll: 0,
              },
            });
          }
        }
      });

      // 加载并绘制分段航线
      this.addSegmentedRoutes();
    },

    // 添加无人机飞行轨迹及动画实体
    addDroneTrajectory() {
      // 获取当前时间作为动画开始时间
      this.startTime = Cesium.JulianDate.now();

      // 计算动画结束时间：开始时间+路径点数*2秒（假设每段飞行2秒）
      this.stopTime = Cesium.JulianDate.addSeconds(
        this.startTime,
        this.dronePath.length * 2,
        new Cesium.JulianDate()
      );

      // 将路径点转换成 Cesium 坐标数组
      const pathPositions = this.dronePath.map((p) =>
        Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt)
      );

      // 在地图上添加路径线（光晕效果）
      this.viewer.entities.add({
        id: 'drone-path',
        polyline: {
          positions: pathPositions,
          width: 4,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.2,
            color: Cesium.Color.CYAN,
          }),
        },
      });

      // 创建一个时间动态的属性用于无人机位置插值
      const sampledPosition = new Cesium.SampledPositionProperty();

      // 将每个路径点及其对应的时间样本添加到属性中
      this.dronePath.forEach((point, index) => {
        const time = Cesium.JulianDate.addSeconds(
          this.startTime,
          index * 2,
          new Cesium.JulianDate()
        );
        const position = Cesium.Cartesian3.fromDegrees(point.lng, point.lat, point.alt);
        sampledPosition.addSample(time, position);
      });

      // 添加无人机实体，绑定位置和方向，设置3D模型和路径轨迹样式
      this.viewer.entities.add({
        id: 'drone-entity',
        availability: new Cesium.TimeIntervalCollection([
          new Cesium.TimeInterval({ start: this.startTime, stop: this.stopTime }),
        ]),
        position: sampledPosition,
        orientation: new Cesium.VelocityOrientationProperty(sampledPosition), // 方向跟随速度向量
        model: {
          uri: '/models/Cesium_Air.glb', // 3D模型文件路径
          scale: 1.0,
          minimumPixelSize: 64,          // 最小像素大小，保证近距离可见
          maximumScale: 200,
        },
        path: {                          // 飞行轨迹的线条样式
          resolution: 1,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.2,
            color: Cesium.Color.YELLOW,
          }),
          width: 2,
        },
      });

      // 配置时钟的开始/结束时间和播放模式
      this.viewer.clock.startTime = this.startTime.clone();
      this.viewer.clock.stopTime = this.stopTime.clone();
      this.viewer.clock.currentTime = this.startTime.clone();
      this.viewer.clock.clockRange = Cesium.ClockRange.CLAMPED;  // 播放到末尾停住
      this.viewer.clock.multiplier = 1;                           // 时间流速1倍
      this.viewer.clock.shouldAnimate = true;                     // 启动画面动画

      // 时间轴缩放到动画区间
      if (this.viewer.timeline) {
        this.viewer.timeline.zoomTo(this.startTime, this.stopTime);
      }
    },

    // 添加分段航线，绘制多条线路段并设置颜色和标签
    addSegmentedRoutes() {
      const total = segmentedRoutes.length;
      const hueStart = 0.55;  // 色调起始值，HSL 颜色空间
      const hueEnd = 0.7;     // 色调结束值

      segmentedRoutes.forEach((segment, index) => {
        // 根据序号计算渐变色调
        const hue = hueStart + (index / total) * (hueEnd - hueStart);

        this.viewer.entities.add({
          id: `route-segment-${index}`,
          name: `${segment.startStation} - ${segment.endStation}`,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(segment.coords),
            width: 6,
            material: Cesium.Color.fromHsl(hue, 0.65, 0.5, 0.7), // 透明度0.7
          },
          label: {
            text: `${segment.startStation} → ${segment.endStation}`, // 标签文字
            font: '16px "Microsoft YaHei"',
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            fillColor: Cesium.Color.fromCssColorString('#1890bd'), // 蓝色
            outlineColor: Cesium.Color.BLUE.withAlpha(0.7),
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(0, -10),
            verticalOrigin: Cesium.VerticalOrigin.TOP,
          }
        });
      });
    },

    // 切换飞行动画的播放和暂停状态
    toggleAnimation() {
      this.animationPlaying = !this.animationPlaying;
      this.viewer.clock.shouldAnimate = this.animationPlaying;
    },

    // 切换地图点击打点功能的开关
    toggleClickToAddPoint() {
      if (!this.clickPointEnabled) {
        this.enableClickToAddPoint();
      } else {
        this.disableClickToAddPoint();
      }
      this.clickPointEnabled = !this.clickPointEnabled;
    },

    // 启用地图点击打点功能，绑定鼠标左键点击事件
    enableClickToAddPoint() {
      if (this.clickHandler) return;  // 已启用则返回

      // 创建事件处理器，绑定到地图画布
      this.clickHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas);

      // 监听左键点击事件
      this.clickHandler.setInputAction((movement) => {
        // 使用 pickPosition 获取鼠标点在地球上的笛卡尔坐标
        const earthPosition = this.viewer.scene.pickPosition(movement.position);
        if (Cesium.defined(earthPosition)) {
          // 将笛卡尔坐标转换成经纬度
          const cartographic = Cesium.Cartographic.fromCartesian(earthPosition);
          const lon = Cesium.Math.toDegrees(cartographic.longitude);
          const lat = Cesium.Math.toDegrees(cartographic.latitude);
          const alt = 300;  // 海拔高度，默认300米

          // 保存用户点击的点到数组
          this.userPoints.push({ lng: lon, lat: lat, alt: alt });

          // 使用 SVG 图标代替点
          this.viewer.entities.add({
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
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },

    // 禁用点击打点，销毁事件处理器
    disableClickToAddPoint() {
      if (this.clickHandler) {
        this.clickHandler.destroy();
        this.clickHandler = null;
      }
    },

    // 生成飞行路径，从用户点击的点构造路径并显示飞行动画
    generateRouteFromPoints() {
      if (this.userPoints.length < 2) {
        alert('请至少打两个点');
        return;
      }
      // 复制用户点到飞行路径
      this.dronePath = [...this.userPoints];
      // 添加轨迹和飞行动画
      this.addDroneTrajectory();
    },

    // 处理无人机详情查看回调
    handleDetail() {
      console.log('查看详情');
    },
  },

  // 组件卸载时，销毁地图及事件处理器，避免内存泄漏
  beforeUnmount() {
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
/* 地图容器样式，填满整个视口高度 */
#map-container {
  width: 100%;
  height: 100vh;
}
</style>
