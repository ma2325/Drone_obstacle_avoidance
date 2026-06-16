<template>
  <div class="drone-line-container">
    <!-- 地图容器 -->
    <div id="map-container" class="map-container"></div>

    <!-- 卡片区域 -->
    <div class="config-card">
      <el-tabs v-model="activeTab" class="config-tabs">
        <el-tab-pane label="基础" name="base">
          <!-- 1. 标题区 -->
          <h3 style="margin-bottom: 16px;">基础设置</h3>

          <!-- 2. 设置区域 -->
          <div class="section">
            <div class="section-left">
              <el-form label-position="top">
                <el-form-item label="航线名称">
                  <el-input v-model="form.routeName" placeholder="请输入航线名称" />
                </el-form-item>
                <el-form-item label="飞行器型号">
                  <el-select v-model="form.droneType" placeholder="请选择型号">
                    <el-option label="Matrice 3TD" value="Matrice 3TD" />
                    <el-option label="Mavic 3E" value="Mavic 3E" />
                  </el-select>
                </el-form-item>
              </el-form>
            </div>

            <div class="section-right">
              <el-form label-position="top">
                <el-form-item label="起飞点坐标">
                  <el-input v-model="form.takeoffPoint" readonly />
                </el-form-item>
                <el-form-item label="飞向首航点模式">
                  <el-select v-model="form.firstPointMode">
                    <el-option label="安全模式" value="安全模式" />
                    <el-option label="直接飞行" value="直接飞行" />
                  </el-select>
                </el-form-item>
                <el-form-item label="安全起飞高度">
                  <el-input v-model="form.safeHeight" suffix-icon="el-icon-s-promotion" />
                </el-form-item>
                <el-form-item label="飞向首航点速度">
                  <el-input v-model="form.firstSpeed" suffix="m/s" />
                </el-form-item>
              </el-form>
            </div>
          </div>

          <el-divider />

          <!-- 3. 高度设置 -->
          <div class="section">
            <el-form label-position="top">
              <el-form-item label="航线高度模式">
                <el-radio-group v-model="form.altitudeMode">
                  <el-radio-button label="绝对高度" />
                  <el-radio-button label="相对地形高度" />
                  <el-radio-button label="相对起飞点高度" />
                </el-radio-group>
              </el-form-item>
              <el-form-item label="当前模式下高度">
                <el-input v-model="form.altitude" suffix="m" />
              </el-form-item>
            </el-form>
          </div>

          <el-divider />

          <!-- 4. 动作设置 -->
          <div class="section">
            <el-form label-position="top">
              <el-form-item label="全局航线速度">
                <el-input v-model="form.routeSpeed" suffix="m/s" />
              </el-form-item>
              <el-form-item label="航线结束动作">
                <el-select v-model="form.endAction">
                  <el-option label="返航" value="返航" />
                  <el-option label="悬停" value="悬停" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-checkbox v-model="form.continueOnLost">失控是否继续执行航线</el-checkbox>
              </el-form-item>
              <el-form-item label="失控动作类型">
                <el-select v-model="form.lostAction">
                  <el-option label="返航" value="返航" />
                  <el-option label="降落" value="降落" />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <el-divider />

          <!-- 5. 飞行模式设置 -->
          <div class="section">
            <el-form label-position="top">
              <el-form-item label="航点转弯模式">
                <el-select v-model="form.turnMode">
                  <el-option label="直线飞行，到点停" value="直线飞行，到点停" />
                  <el-option label="平滑过渡" value="平滑过渡" />
                </el-select>
              </el-form-item>
              <el-form-item label="飞行器偏航角模式">
                <el-select v-model="form.yawMode">
                  <el-option label="沿航线方向" value="沿航线方向" />
                </el-select>
              </el-form-item>
              <el-form-item label="云台俯仰角模式">
                <el-select v-model="form.gimbalMode">
                  <el-option label="固定设置" value="固定设置" />
                  <el-option label="随动" value="随动" />
                </el-select>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <el-tab-pane label="航点" name="waypoints">
          <p>航点功能开发中...</p>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

const activeTab = ref('base')

// 表单数据
const form = ref({
  routeName: '测试航线0412',
  droneType: 'Matrice 3TD',
  takeoffPoint: '',
  firstPointMode: '安全模式',
  safeHeight: '100',
  firstSpeed: '10',
  altitudeMode: '绝对高度',
  altitude: '120',
  routeSpeed: '10',
  endAction: '返航',
  continueOnLost: false,
  lostAction: '返航',
  turnMode: '直线飞行，到点停',
  yawMode: '沿航线方向',
  gimbalMode: '固定设置',
})

let viewer = null

onMounted(() => {
  viewer = new Cesium.Viewer('map-container', {
    terrainProvider: Cesium.createWorldTerrain(),
    animation: false,
    timeline: false,
    geocoder: false,
    homeButton: false,
    baseLayerPicker: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
    selectionIndicator: false
  })

  viewer.scene.globe.depthTestAgainstTerrain = true

  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(121.272285, 31.052934, 1500),
    orientation: {
      heading: Cesium.Math.toRadians(0),
      pitch: Cesium.Math.toRadians(-45),
    }
  })

  // 点击地图获取坐标
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
  handler.setInputAction((click) => {
    const picked = viewer.scene.pickPosition(click.position)
    if (Cesium.defined(picked)) {
      const cartographic = Cesium.Cartographic.fromCartesian(picked)
      const lon = Cesium.Math.toDegrees(cartographic.longitude).toFixed(6)
      const lat = Cesium.Math.toDegrees(cartographic.latitude).toFixed(6)
      const alt = cartographic.height.toFixed(2)

      form.value.takeoffPoint = `[${lat}, ${lon}, ${alt}]`

      viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
        point: {
          pixelSize: 10,
          color: Cesium.Color.YELLOW,
        },
        label: {
          text: '起飞点',
          font: '14px sans-serif',
          fillColor: Cesium.Color.WHITE,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 2,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -12),
        }
      })
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
})
</script>

<style scoped>
.drone-line-container {
  display: flex;
  height: 100vh;
}

.map-container {
  width: 60%;
  height: 100%;
}

.config-card {
  width: 40%;
  padding: 20px;
  overflow-y: auto;
  background-color: #1e1e1e;
  color: #fff;
  border-left: 1px solid #333;
}

.section {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

.section-left, .section-right {
  width: 48%;
}
</style>
