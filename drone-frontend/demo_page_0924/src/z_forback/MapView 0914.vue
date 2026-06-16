<!-- src/components/TaskLine/MapView.vue -->
<template>
  <!-- 主容器：地图 + 右侧配置 -->
  <div id="map-wrapper" style="width: 100%; height: 100vh; position: relative;">
    <!-- 主地图 -->
    <div id="map-container" style="width: 100%; height: 100%;"></div>

    <!-- 左上角迷你地图 -->
    <div
      id="mini-view"
      style="position: absolute; top: 30px; left: 10px; width: 220px; height: 160px; border: 2px solid #ccc; z-index: 998;"
    ></div>

    <!-- 加载提示（恢复航线/覆盖物时） -->
    <div
      v-if="isLoadingRoute"
      style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: rgba(0,0,0,0.7); color: white; padding: 10px 20px; border-radius: 4px; z-index: 1000;"
    >
      正在加载航线...
    </div>

    <!-- 返回菜单 -->
    <button class="return-menu-btn" v-if="!airspaceMode" @click="returnToRoutePlan">返回航线菜单</button>

    <!-- 右侧配置卡片（可折叠） -->
    <div class="config-card" :class="{ collapsed: isConfigCollapsed }">
      <button class="toggle-config-btn" @click="toggleConfigCard" title="收起/展开">
        <el-icon size="20" color="#ffffff">
          <ArrowRight v-if="!isConfigCollapsed" />
          <ArrowLeft v-else />
        </el-icon>
      </button>

      <!-- 非空域模式：显示“基础 / 航点(任务)”等原有配置 -->
      <el-tabs v-if="!airspaceMode" v-model="activeTab" class="config-tabs" v-show="!isConfigCollapsed">
        <!-- 基础设置 -->
        <el-tab-pane label="基础" name="base">
          <h3 style="margin-bottom: 16px;">基础设置</h3>
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
                <el-form-item label="飞向首航点速度">
                  <el-input v-model="form.firstSpeed" />
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
                  <el-input v-model="form.safeHeight" />
                </el-form-item>
              </el-form>
            </div>
          </div>

          <el-divider />

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
                <el-input v-model="form.altitude" />
              </el-form-item>
            </el-form>
          </div>

          <el-divider />

          <div class="section">
            <el-form label-position="top">
              <el-form-item label="全局航线速度">
                <el-input v-model="form.routeSpeed" />
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
        </el-tab-pane>

        <!-- 航点/建图/带状/预设 -->
        <el-tab-pane label="航点" name="waypoints">
          <el-form label-position="top">
            <el-form-item label="任务类型">
              <el-select v-model="routeType" placeholder="选择任务类型" @change="updateButtonVisibility">
                <el-option label="航点飞行" value="航点飞行" />
                <el-option label="建图航拍" value="建图航拍" />
                <el-option label="带状航线" value="带状航线" />
                <el-option label="预设航线" value="预设航线" />
              </el-select>
            </el-form-item>

            <el-form-item label="飞行高度">
              <el-input v-model.number="flightHeight" @change="updateSelectedPointHeight" />
            </el-form-item>

            <el-form-item>
              <button class="save-settings-btn" @click="saveSettings">保存设置</button>
            </el-form-item>

            <el-form-item label="任务配置">
              <el-button type="primary" @click="openTaskDialog(false)">新建任务</el-button>
            </el-form-item>
          </el-form>

          <div class="btn-group">
            <button v-if="showButtons.enablePointMark" @click="toggleClickToAddPoint">
              {{ clickPointEnabled ? '关闭打点' : '启用打点' }}
            </button>
            <button v-if="showButtons.generatePointPath" @click="generateRouteFromPoints">生成飞行航线</button>
            <button v-if="showButtons.flightAnimation" @click="toggleAnimation">
              {{ animationPlaying ? '暂停飞行动画' : '开始飞行动画' }}
            </button>
            <button v-if="showButtons.drawArea" @click="toggleDrawArea">
              {{ drawAreaEnabled ? '关闭区域绘制' : '启用区域绘制' }}
            </button>
            <button v-if="showButtons.generateGrid" @click="generateGridPath">生成航拍网格</button>
            <button v-if="showButtons.previewGridPath" @click="previewGridPath">预览航拍路径</button>
            <button v-if="showButtons.generateStripPath" @click="generateStripPath">生成带状路径</button>
          </div>

          <div v-if="!Object.values(showButtons).some(v => v)" class="no-buttons-message">
            未选择有效航线类型，请选择任务类型
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- 空域模式：右侧面板 -->
      <div v-else v-show="!isConfigCollapsed">
        <h3 style="margin-bottom: 16px;">空域编辑</h3>
        <el-form label-width="92px">
          <el-form-item label="空域名称">
            <el-input v-model="airspaceForm.name" placeholder="测试禁飞区" />
          </el-form-item>

          <el-form-item label="空域类型">
            <el-select v-model="airspaceForm.type" placeholder="请选择空域类型">
              <el-option v-for="t in airspaceTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>

          <el-form-item label="封面缩略图">
            <div style="display:flex; gap:12px; align-items:center;">
              <img
                v-if="airspaceForm.cover"
                :src="airspaceForm.cover"
                alt="cover"
                style="width:120px;height:80px;object-fit:cover;border-radius:4px;border:1px solid #555;"
              />
              <div v-else style="width:120px;height:80px;border:1px dashed #666;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#999;">
                无
              </div>
              <el-button size="small" @click="captureCover">设置</el-button>
            </div>
          </el-form-item>

          <el-form-item label="有效时间">
            <el-date-picker v-model="airspaceForm.start" type="date" placeholder="开始日期" style="width: 45%;" />
            <span style="display:inline-block;width:10%;text-align:center;color:#999;">至</span>
            <el-date-picker v-model="airspaceForm.end" type="date" placeholder="结束日期" style="width: 45%;" />
          </el-form-item>

          <el-form-item label="备注信息">
            <el-input v-model="airspaceForm.remark" placeholder="输入相关信息" />
          </el-form-item>

          <el-form-item label="操作">
            <el-button type="primary" @click="toggleAirspaceDrawing">
              {{ airspaceDrawing ? '结束绘制' : (userAreaPoints.length ? '替换区域' : '开始绘制') }}
            </el-button>
            <el-button type="success" :disabled="!canSaveAirspace" @click="saveAirspace">保存</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <!-- 任务新建/修改弹窗（保留原功能） -->
    <el-dialog v-model="taskDialogVisible" title="新建任务" width="500px">
      <el-form :model="currentTask" label-width="100px">
        <el-form-item label="任务ID">
          <el-input v-model="currentTask.id" placeholder="请输入任务ID" :disabled="editMode" />
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="currentTask.name" placeholder="请输入任务名称" :disabled="editMode" />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="currentTask.taskType" placeholder="请选择任务类型" @change="updateInspectionTypes">
            <el-option label="线路扫描" value="线路扫描" />
            <el-option label="点位扫描" value="点位扫描" />
          </el-select>
        </el-form-item>
        <el-form-item label="航线任务">
          <el-checkbox-group v-model="currentTask.type">
            <el-checkbox v-if="currentTask.taskType === '线路扫描'" v-for="o in areaTypes" :key="o" :label="o">{{ o }}</el-checkbox>
            <el-checkbox v-if="currentTask.taskType === '点位扫描'" v-for="o in pointTypes" :key="o" :label="o">{{ o }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="起飞点">
          <el-select v-model="currentTask.takeoff" placeholder="请选择起飞点">
            <el-option v-for="p in takeoffPoints" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="航线编号"><el-input v-model="currentTask.route_id" /></el-form-item>
        <el-form-item label="航线里程"><el-input v-model="currentTask.route" /></el-form-item>

        <template v-if="currentTask.taskType === '点位扫描'">
          <el-form-item label="巡检位置（中心）">
            <el-input v-model="currentTask.inspectCenter" placeholder="点击下方按钮后在地图上单击选择圆心" readonly />
          </el-form-item>
          <el-form-item label="巡检半径（米）">
            <el-input v-model="currentTask.inspectRadius" placeholder="第二次单击确定后填入" readonly />
          </el-form-item>
          <el-form-item label="巡检区域">
            <el-button type="primary" size="small" @click="enablePickInspectionArea">地图上选择</el-button>
          </el-form-item>
        </template>

        <el-form-item label="时间窗">
          <el-time-picker
            v-model="currentTask.time_window"
            is-range range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间"
            format="HH:mm" value-format="HH:mm"
          />
        </el-form-item>
        <el-form-item label="飞行趟数"><el-input v-model="currentTask.flightCount" /></el-form-item>
        <el-form-item label="任务执行时间">
          <el-select v-model="currentTask.executionTime"><el-option label="立即执行" value="immediate" /><el-option label="设定时间" value="custom" /></el-select>
        </el-form-item>
        <el-form-item label="自定义时间" v-if="currentTask.executionTime === 'custom'">
          <el-date-picker v-model="currentTask.customExecutionTime" type="datetime" format="YYYY-MM-DD HH:mm" value-format="YYYY-MM-DD HH:mm" style="width:100%" />
        </el-form-item>
        <el-form-item label="预计执行时间 (h)"><el-input v-model="currentTask.expectedFinish" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTask">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
/**
 * MapView.vue —— 合并版（支持“航线任务 + 空域编辑”双模式）
 *
 * ✅ 修复点：
 *  - FIX-1：兼容 openPayload 形态 { type:'open-map-from-airspace', data:{...} }，能正确进入空域模式。
 *  - FIX-2：保存空域后，除了 $emit('action')，额外用 window.dispatchEvent 广播 'airspace-updated'，与 Airspace.vue 的全局监听匹配。
 */
import { ArrowRight, ArrowLeft } from '@element-plus/icons-vue'
import * as Cesium from 'cesium'
import * as turf from '@turf/turf'
import stations from '@/test-data/station.json'
import segmentedRoutes from '@/test-data/segmented_route.json'
import route3d_0 from '@/test-data/routes_3d/route_0_3d.json'
import route3d_1 from '@/test-data/routes_3d/route_1_3d.json'
import route3d_2 from '@/test-data/routes_3d/route_2_3d.json'
import route3d_3 from '@/test-data/routes_3d/route_3_3d.json'
import route3d_5 from '@/test-data/routes_3d/route_5_3d.json'
import route3d_6 from '@/test-data/routes_3d/route_6_3d.json'
import route3d_7 from '@/test-data/routes_3d/route_7_3d.json'
import route3d_8 from '@/test-data/routes_3d/route_8_3d.json'
import route3d_9 from '@/test-data/routes_3d/route_9_3d.json'
import route3d_21 from '@/test-data/routes_3d/route_21_3d.json'
import route3d_22 from '@/test-data/routes_3d/route_22_3d.json'
import 'cesium/Build/Cesium/Widgets/widgets.css'

/** 呼吸标记 SVG */
const BREATH_ICON =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(`
<svg width="64" height="64" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <circle cx="32" cy="32" r="15" fill="#00E5FF" filter="url(#glow)"/>
  <circle cx="32" cy="32" r="15" fill="none" stroke="white" stroke-width="4"/>
  <circle cx="32" cy="32" r="6" fill="white"/>
</svg>`)

/** Cesium Token（示例） */
Cesium.Ion.defaultAccessToken =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI3MjNmNDQ4Ny04MjBjLTQyYjgtOTA5Ni1lMjRhOTk5MGY3MjMiLCJpZCI6MzIzMzA3LCJpYXQiOjE3NTMwNjU0NzZ9.fD2b3-Hes2o3RrMfNg45qkW5x1-cK0Yqn-xLpxT8SAc'

/*预设 3D 航线 */
const FILE_MAP = {
  route_0: route3d_0,
  route_1: route3d_1,
  route_2: route3d_2,
  route_3: route3d_3,
  route_5: route3d_5,
  route_6: route3d_6,
  route_7: route3d_7,
  route_8: route3d_8,
  route_9: route3d_9,
  route_21: route3d_21,
  route_22: route3d_22
}

/*相机初始位置-参数映射表*/
const PRESET_CAMERAS = {
  // 支持两种命名：route3d_1 / route_1
  route_1:   { lng: 115.646870, lat: 38.965610, height: 1600, headingDeg: 0,   pitchDeg: -45 },
  route3d_1: { lng: 115.646870, lat: 38.965610, height: 1600, headingDeg: 0,   pitchDeg: -45 },

  route_6:   { lng: 115.667308, lat: 38.849182, height: 8000, headingDeg: 0,  pitchDeg: -15 },
  route3d_6: { lng: 115.667308, lat: 38.849182, height: 8000, headingDeg: 0,  pitchDeg: -15 },

  route_3:   { lng: 115.529220, lat: 38.782651, height: 1600, headingDeg: -15, pitchDeg: -45 },
  route3d_3: { lng: 115.529220, lat: 38.782651, height: 1600, headingDeg: -15, pitchDeg: -45 },

  route_4:   { lng: 115.298243, lat: 38.702834, height: 1600, headingDeg: 0,   pitchDeg: -45 },
  route3d_4: { lng: 115.298243, lat: 38.702834, height: 1600, headingDeg: 0,   pitchDeg: -45 },
}

/** 空域类型 → 填充色 */
const AIRSPACE_COLOR = {
  禁飞区: '#a61d24',
  适飞区: '#389e0d',
  限飞区: '#d46b08',
  危险区: '#fa541c',
  保护区: '#531dab'
}

export default {
  name: 'MapView',
  components: { ArrowRight, ArrowLeft },
  props: {
    /** 任务模式入参（保持原样） */
    type: { type: String, default: '航点飞行' },
    taskId: { type: [String, Number], default: '' },
    startStation: { type: String, default: '' },
    preset3dKey: { type: String, default: '' },
    restore: { type: Boolean, default: true },
    lock: { type: Boolean, default: false },
    navNonce: { type: Number, default: 0 },

    /** 新增：统一“打开地图”的负载（空域专用） */
    openPayload: { type: Object, default: null },
    payloadNonce: { type: Number, default: 0 },
  },
  emits: ['action'],

  /** keep-alive 生命周期 */
  activated () { if (this.viewer) this.viewer.clock.shouldAnimate = this.animationPlaying },
  deactivated () { if (this.viewer) this.viewer.clock.shouldAnimate = false },

  data () {
    return {
      /* -------------------- 全局就绪/UI -------------------- */
      activeTab: 'base',
      isConfigCollapsed: false,
      isLoadingRoute: false,
      viewer: null,
      miniViewer: null,
      _cameraInputHandler: null,

      /* -------------------- 航线模式状态 -------------------- */
      routeType: this.type,
      showButtons: {
        enablePointMark: this.type === '航点飞行',
        generatePointPath: this.type === '航点飞行',
        flightAnimation: ['航点飞行', '带状航线', '预设航线'].includes(this.type),
        drawArea: this.type === '建图航拍',
        generateGrid: this.type === '建图航拍',
        previewGridPath: this.type === '建图航拍',
        generateStripPath: this.type === '带状航线'
      },
      taskIdLocal: String(this.taskId || ''),
      preset3dKeyLocal: this.preset3dKey || '',
      wantRestore: !!this.restore,
      _lastPreset3D: '',
      _lastNonce: 0,

      clickHandler: null,
      animationPlaying: true,
      clickPointEnabled: false,
      drawAreaEnabled: false,

      userPoints: [],       // 航点
      showAreaVertices: false,// 绘制时显示点，结束后自动隐藏
      userAreaPoints: [],   // 建图/空域多边形（复用）
      
      gridPath: [],
      stripPath: [],
      dronePath: [],

      startTime: null,
      stopTime: null,
      coneHeading: 0,
      coneMoveHandler: null,
      _draggedEntity: null,
      _dragPromptEntity: null,
      selectedPointIndex: null,

      flightHeight: 300,
      savedRoutes: {},

      /** 预设航线端点实体 id（用于清理） */
      presetStartId: 'preset-start-point',
      presetEndId: 'preset-end-point',
      presetStartProjId: 'preset-start-projection',
      presetEndProjId: 'preset-end-projection',

      /** 表单（航线设置） */
      form: {
        routeName: '测试航线',
        droneType: 'Matrice 3TD',
        takeoffPoint: '',
        firstPointMode: '安全模式',
        safeHeight: '100',
        firstSpeed: '10',
        altitudeMode: '绝对高度',
        altitude: '300',
        routeSpeed: '10',
        endAction: '返航',
        continueOnLost: false,
        lostAction: '返航',
        turnMode: '直线飞行，到点停',
        yawMode: '沿航线方向',
        gimbalMode: '固定设置'
      },

      /** 任务弹窗（保留原功能） */
      taskDialogVisible: false,
      editMode: false,
      currentTask: {
        id: '', name: '', taskType: '', type: [], takeoff: '',
        route_id: '', route: '', inspectCenter: '', inspectRadius: '',
        time_window: [], flightCount: 1, executionTime: 'immediate',
        customExecutionTime: '', expectedFinish: ''
      },
      areaTypes: ['抛洒物识别', '团雾检测', '病害识别', '拥堵点检测'],
      pointTypes: ['桥梁巡检', '边坡巡检'],
      takeoffPoints: [],

      /** 点位扫描 - 巡检圆 */
      pickingInspection: false,
      inspectionCenter: null,
      inspectionRadius: 0,
      inspectionCenterId: 'inspection-center-point',
      inspectionCircleId: 'inspection-circle',

      turnaroundCenter: null,
      turnaroundRadius: 0,

      /** -------------------- 空域模式状态 -------------------- */
      airspaceMode: false,             // 是否处于空域模式
      airspaceDrawing: false,          // 是否正在绘制
      airspaceIdLocal: '',             // 空域 ID
      airspaceForm: {                  // 右侧表单
        name: '',
        type: '危险区',
        cover: '',
        start: '',
        end: '',
        remark: ''
      },
      airspaceTypes: ['禁飞区', '适飞区', '限飞区', '危险区', '保护区']
    }
  },

  created () {
    /* ---- 侦听任务模式 props（保持原逻辑） ---- */
    this.$watch(
      () => [this.type, this.taskId, this.preset3dKey, this.restore, this.navNonce, this.openPayload, this.payloadNonce],
      ([t, id, preset, rst, nonce, payload]) => {
        
        /* 1) 任务模式的更新 */
        this.routeType = t
        this.taskIdLocal = String(id || '')
        this.preset3dKeyLocal = preset || ''
        this.wantRestore = !!rst
        this.updateButtonVisibility()

        /* ============================ FIX-1 开始 ============================
         * 兼容两种负载：
         *  A) { type:'open-map-from-airspace', data:{...} }   ← 来自 Airspace.vue
         *  B) 直接就是 { airspaceId, name, polygon, ... }
         *  命中即进入空域模式，否则恢复任务模式 UI
         * ================================================================== */
        let p = payload
        if (p && p.data && p.type === 'open-map-from-airspace') p = p.data
        const isAirspaceOpen =
          p &&
          (
            p.type === 'open-map-from-airspace' ||        // 兜底字段
            p.airspaceId || Array.isArray(p.polygon)      // 通过字段特征识别
            
          )

        if (isAirspaceOpen) {
          this.enterAirspaceMode(p)
          return
        } else {
          this.exitAirspaceMode(false)
        }
        /* ============================ FIX-1 结束 ============================ */

        if (!this.viewer) return
        if (preset) {
          if (preset !== this._lastPreset3D) {
            this.applyPreset3D()
            this._lastPreset3D = preset
          } else if (nonce && nonce !== this._lastNonce) {
            this._lastNonce = nonce
            this.setInitialCameraForPreset(preset)  // 可选：强制按预设航线初始视角重置
            this.refitPresetCamera(preset)
          }
        }
        if (t !== '预设航线' || this.wantRestore) this.loadSavedRoute()
      },
      { immediate: true }
    )

    // 航线高度双向同步
    this.$watch(() => this.flightHeight, v => (this.form.altitude = String(v)))
    this.$watch(() => this.form.altitude, v => { const n = parseFloat(v); if (!isNaN(n)) this.flightHeight = n })

    // 起飞点下拉
    this.takeoffPoints = Array.isArray(stations) ? stations.map(s => s.name) : []
  },

  mounted () {
    this.loadMap()
    if (this.openPayload) {
     const p = this.openPayload.data && this.openPayload.type === 'open-map-from-airspace'
       ? this.openPayload.data
       : this.openPayload
     if (p && (p.airspaceId || Array.isArray(p.polygon))) this.enterAirspaceMode(p)
   }
  },

  activated () {
   // keep-alive 返回时也兜底一次，确保右侧仍是空域模式
   if (this.openPayload) {
     const p = this.openPayload.data && this.openPayload.type === 'open-map-from-airspace'
       ? this.openPayload.data
       : this.openPayload
     if (p && (p.airspaceId || Array.isArray(p.polygon))) this.enterAirspaceMode(p)
   }
 },

  beforeUnmount () {
    this.disableClickToAddPoint()
    this.disableDrawArea()
    if (this.coneMoveHandler) { this.coneMoveHandler.destroy(); this.coneMoveHandler = null }
    if (this.viewer) {
      this.viewer.entities.removeById(this.inspectionCenterId)
      this.viewer.entities.removeById(this.inspectionCircleId)
    }
    if (this._dragPromptEntity) { this.viewer.entities.remove(this._dragPromptEntity); this._dragPromptEntity = null }
    const debugPoint = this.viewer?.entities.getById('debug-cone-vertex')
    if (debugPoint) this.viewer.entities.remove(debugPoint)
    if (this.viewer) { this.viewer.destroy(); this.viewer = null }
    if (this.miniViewer) { this.miniViewer.destroy(); this.miniViewer = null }
    if (this._cameraInputHandler) { this._cameraInputHandler.destroy(); this._cameraInputHandler = null }
  },

  computed: {
    /** 空域是否可保存 */
    canSaveAirspace () {
      return (
        this.airspaceMode &&
        this.airspaceForm.name.trim() &&
        this.airspaceForm.type &&
        this.userAreaPoints.length >= 3
      )
    }
  },

  methods: {
    /* ================= 工具 & 规范化 ================= */
    n (v) { return typeof v === 'string' ? parseFloat(v) : v },
    normPoint (p, defaultAlt = 0) {
      if (!p) return null
      const lng = this.n(p.lng ?? p[0])
      const lat = this.n(p.lat ?? p[1])
      const alt = this.n(p.alt ?? p[2] ?? defaultAlt)
      return { lng, lat, alt }
    },
    coercePoints (arr = [], d = 0) {
      return (arr || []).map(p => this.normPoint(p, d)).filter(q => q && ![q.lng, q.lat].some(Number.isNaN))
    },

    // --------------框选路径窗口中心显示----------------------//
    /** 计算预设3D航线的最小外接矩形（不渲染，仅用于相机定位） */
    computePresetBounds(presetKey) {
      const json = FILE_MAP[presetKey]
      if (!json) return null
      const raw = this.getLngLatPairsFromJson(json)
      if (!Array.isArray(raw) || raw.length < 2) return null

      // 经/纬可能互换，做一次修正
      const fix = (lng, lat) => {
        const swapped = Math.abs(lng) <= 90 && Math.abs(lat) > 90 && Math.abs(lat) <= 180
        return swapped ? [lat, lng] : [lng, lat]
      }

      let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
      raw.forEach(p => {
        const a = Array.isArray(p) ? p[0] : p.lng
        const b = Array.isArray(p) ? p[1] : p.lat
        const [lng, lat] = fix(a, b)
        minLng = Math.min(minLng, lng)
        maxLng = Math.max(maxLng, lng)
        minLat = Math.min(minLat, lat)
        maxLat = Math.max(maxLat, lat)
      })
      if (!Number.isFinite(minLng) || !Number.isFinite(minLat)) return null

      const centerLng = (minLng + maxLng) / 2
      const centerLat = (minLat + maxLat) / 2

      // 用经纬差估一个合适高度，让矩形完整且居中
      const dx = Math.max(1e-6, Math.abs(maxLng - minLng))
      const dy = Math.max(1e-6, Math.abs(maxLat - minLat))
      const horizMeters = Math.max(dx, dy) * 111111
      const height = Math.max(800, horizMeters * 2)  // 倍数可按喜好调

      return { minLng, minLat, maxLng, maxLat, centerLng, centerLat, height }
    },

    /** 将相机置于矩形中心（不渲染矩形） */
    centerCameraOnBounds(bounds, tiltDeg = -45) {
      if (!this.viewer || !bounds) return
      const { centerLng, centerLat, height } = bounds
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(centerLng, centerLat, height),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(tiltDeg), roll: 0 }
      })
    },
    
    // --------------框选路径窗口中心显示结束----------------//

    /** 将 route3d_* / route_* 统一为 route_* */
    normalizePresetKey (k = '') {
      if (!k) return ''
      return String(k).replace(/^route3d_/, 'route_')
    },

    /** 按 PRESET_CAMERAS 设置初始相机视角（若无匹配则不动） */
    setInitialCameraForPreset (keyRaw) {
      const key = this.normalizePresetKey(keyRaw)
      const cam = PRESET_CAMERAS[key] || PRESET_CAMERAS[keyRaw]
      if (!this.viewer || !cam) return
      const { lng, lat, height = 1600, headingDeg = 0, pitchDeg = -45 } = cam
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(lng, lat, height),
        orientation: {
          heading: Cesium.Math.toRadians(headingDeg),
          pitch:   Cesium.Math.toRadians(pitchDeg),
          roll:    0
        }
      })
    },


    // -----------------点位呼吸动画-------------------//
    /* ================= 呼吸高亮 ================= */
    addBreathingMarker (idBase, lng, lat, opts = {}) {
      if (!this.viewer) return
      const idIcon = `${idBase}-icon`
      const idRing = `${idBase}-ring`
      this.viewer.entities.removeById(idIcon)
      this.viewer.entities.removeById(idRing)

      const iconSize = Number(opts.iconSize ?? 36)
      const ringMin  = Number(opts.ringMin ?? 20)
      const ringMax  = Number(opts.ringMax ?? 120)
      const periodMs = Number(opts.periodMs ?? 1600)
      const labelText = String(opts.label ?? '标记')

      const scaleFn = time => {
        const t = Cesium.JulianDate.toDate(time).getTime()
        const phase = (Math.sin((t % periodMs) / periodMs * Math.PI * 2) + 1) / 2
        return 0.9 + 0.25 * phase
      }

      this.viewer.entities.add({
        id: idIcon,
        position: Cesium.Cartesian3.fromDegrees(lng, lat, 0),
        billboard: {
          image: BREATH_ICON,
          width: iconSize, height: iconSize,
          scale: new Cesium.CallbackProperty(scaleFn, false),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text: labelText,
          font: 'bold 14px "Microsoft YaHei", sans-serif',
          fillColor: Cesium.Color.WHITE,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.fromCssColorString('#185ABD'),
          outlineWidth: 3,
          pixelOffset: new Cesium.Cartesian2(0, -28),
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
        }
      })

      const radiusFn = new Cesium.CallbackProperty((time) => {
        const t = Cesium.JulianDate.toDate(time).getTime()
        const phase = (t % periodMs) / periodMs
        return ringMin + (ringMax - ringMin) * phase
      }, false)
      const alphaFn = new Cesium.CallbackProperty((time) => {
        const t = Cesium.JulianDate.toDate(time).getTime()
        const phase = (t % periodMs) / periodMs
        return Math.max(0.08, 1 - phase)
      }, false)

      this.viewer.entities.add({
        id: idRing,
        position: Cesium.Cartesian3.fromDegrees(lng, lat, 0),
        ellipse: {
          semiMajorAxis: radiusFn,
          semiMinorAxis: radiusFn,
          material: new Cesium.ColorMaterialProperty(
            new Cesium.CallbackProperty((time) =>
              Cesium.Color.fromCssColorString('#00E5FF').withAlpha(alphaFn.getValue(time)), false
            )
          ),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#00E5FF').withAlpha(0.7),
          height: 0,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
        }
      })
    },
    removeBreathingMarker (idBase) {
      if (!this.viewer) return
      this.viewer.entities.removeById(`${idBase}-icon`)
      this.viewer.entities.removeById(`${idBase}-ring`)
    },


    /* ================= 相机贴合 ================= */
    fitCameraToBounds (minLng, minLat, maxLng, maxLat, tiltDeg = -45) {
      if (!this.viewer) return
      if (![minLng, minLat, maxLng, maxLat].every(Number.isFinite)) return
      const centerLng = (minLng + maxLng) / 2
      const centerLat = (minLat + maxLat) / 2
      const dx = Math.max(1e-6, Math.abs(maxLng - minLng))
      const dy = Math.max(1e-6, Math.abs(maxLat - minLat))
      const horizMeters = Math.max(dx, dy) * 111111
      const height = Math.max(800, horizMeters * 2)
      this.viewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(centerLng, centerLat, height),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(tiltDeg), roll: 0 }
      })
    },
    fitCameraToPoints (points, tiltDeg = -45) {
      const pts = this.coercePoints(points, 0)
      if (!pts.length) return
      const lngs = pts.map(p => p.lng), lats = pts.map(p => p.lat)
      this.fitCameraToBounds(Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats), tiltDeg)
    },

    refitPresetCamera (presetKey) {
      const json = FILE_MAP[presetKey]
      if (!json) return
      const pts = this.getLngLatPairsFromJson(json)
      if (!pts || pts.length < 2) return
      const lngs = pts.map(p => (Array.isArray(p) ? p[0] : p.lng))
      const lats = pts.map(p => (Array.isArray(p) ? p[1] : p.lat))
      this.fitCameraToBounds(Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats), -45)
    },

    /* ================= 地图初始化 ================= */
    loadMap () {
      Cesium.createWorldTerrainAsync({
        requestVertexNormals: true,
        requestWaterMask: true
      }).then(terrainProvider => {
        // 主地图
        this.viewer = new Cesium.Viewer('map-container', {
          terrainProvider,
          timeline: true,
          animation: true,
          shouldAnimate: true,
          imageryProvider: new Cesium.UrlTemplateImageryProvider({
            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            subdomains: ['a', 'b', 'c']
          })
        })
        this.viewer.scene.globe.enableLighting = false
        this.viewer.scene.globe.depthTestAgainstTerrain = false
        this.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(116.128449, 39.732607, 100.0),
          orientation: { heading: 0, pitch: Cesium.Math.toRadians(0), roll: 0.0 }
        })

        // 用户交互后取消自动跟随（飞行动画）
        this._cameraInputHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas)
        const cancelTrack = () => {
          if (this.viewer.trackedEntity) this.viewer.trackedEntity = undefined
        }
        ;[
          Cesium.ScreenSpaceEventType.LEFT_DOWN,
          Cesium.ScreenSpaceEventType.MIDDLE_DOWN,
          Cesium.ScreenSpaceEventType.RIGHT_DOWN,
          Cesium.ScreenSpaceEventType.WHEEL,
          Cesium.ScreenSpaceEventType.PINCH_START
        ].forEach(t => this._cameraInputHandler.setInputAction(cancelTrack, t))

        // 迷你地图
        this.miniViewer = new Cesium.Viewer('mini-view', {
          timeline: false,
          animation: false,
          baseLayerPicker: false,
          imageryProvider: new Cesium.UrlTemplateImageryProvider({
            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            subdomains: ['a', 'b', 'c']
          }),
          terrainProvider: new Cesium.EllipsoidTerrainProvider()
        })
        const c = this.miniViewer.scene.screenSpaceCameraController
        c.enableRotate = c.enableTranslate = c.enableZoom = c.enableTilt = c.enableLook = false

        // 相机联动（主 → 迷你）
        let _lastSync = 0
        const syncMiniFromMain = () => {
          const now = performance.now()
          if (now - _lastSync < 50) return
          _lastSync = now
          const cam = this.viewer.camera
          this.miniViewer.camera.setView({
            destination: cam.position,
            orientation: { heading: cam.heading, pitch: cam.pitch, roll: cam.roll }
          })
          updateMiniViewportRect()
        }
        this.viewer.scene.postRender.addEventListener(syncMiniFromMain)

        // 在迷你地图绘制主视口矩形
        const updateMiniViewportRect = () => {
          const rect = this.viewer.camera.computeViewRectangle(this.viewer.scene.globe.ellipsoid)
          if (!rect) return
          const id = 'main-viewport-rect'
          let e = this.miniViewer.entities.getById(id)
          if (!e) {
            e = this.miniViewer.entities.add({
              id,
              rectangle: {
                coordinates: rect,
                material: Cesium.Color.TRANSPARENT,
                outline: true,
                outlineColor: Cesium.Color.RED,
                outlineWidth: 2
              }
            })
          } else {
            e.rectangle.coordinates = rect
          }
        }

        // 迷你地图点击定位主图
        const miniHandler = new Cesium.ScreenSpaceEventHandler(this.miniViewer.scene.canvas)
        miniHandler.setInputAction((click) => {
          const cart = this.miniViewer.camera.pickEllipsoid(click.position, Cesium.Ellipsoid.WGS84)
          if (!Cesium.defined(cart)) return
          const carto = Cesium.Cartographic.fromCartesian(cart)
          const h = this.viewer.camera.positionCartographic.height
          this.viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromRadians(carto.longitude, carto.latitude, h),
            orientation: { heading: this.viewer.camera.heading, pitch: this.viewer.camera.pitch, roll: 0 },
            duration: 0.8
          })
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

        // 站点点位（主 + 迷你）
        stations.forEach(s => {
          const getPixelSize = (time) => {
            const t = Cesium.JulianDate.toDate(time).getTime()
            return 6 + 6 * Math.abs(Math.sin((t / 2000) * Math.PI))
          }
          const getColor = (time) => {
            const t = Cesium.JulianDate.toDate(time).getTime()
            const a = 0.4 + 0.6 * Math.abs(Math.sin((t / 2000) * Math.PI))
            return Cesium.Color.ORANGE.withAlpha(a)
          }
          this.viewer.entities.add({
            id: `station-${s.name}`,
            name: s.name,
            position: Cesium.Cartesian3.fromDegrees(this.n(s.lng), this.n(s.lat), 0),
            point: { pixelSize: new Cesium.CallbackProperty(getPixelSize, false), color: new Cesium.CallbackProperty(getColor, false) },
            label: {
              text: s.name, font: 'bold 14px Microsoft YaHei', style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.fromCssColorString('#185ABD'), outlineWidth: 3,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -15)
            }
          })
          this.miniViewer.entities.add({
            id: `mini-station-${s.name}`,
            name: s.name,
            position: Cesium.Cartesian3.fromDegrees(this.n(s.lng), this.n(s.lat), 0),
            point: { pixelSize: 6, color: Cesium.Color.ORANGE },
            label: {
              text: s.name, font: 'bold 12px Microsoft YaHei', style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.fromCssColorString('#185ABD'), outlineWidth: 2,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -12)
            }
          })
        })

        // 分段参考线（主+迷你）
        segmentedRoutes.forEach((seg, idx) => {
          const hue = 0.55 + (idx / segmentedRoutes.length) * (0.7 - 0.55)
          const positions = Cesium.Cartesian3.fromDegreesArray(seg.coords.flat())
          this.viewer.entities.add({
            id: `route-segment-${idx}`,
            name: `${seg.startStation} - ${seg.endStation}`,
            polyline: { positions, width: 15, material: Cesium.Color.fromHsl(hue, 0.65, 0.5, 0.7) },
            label: {
              text: `${seg.startStation} → ${seg.endStation}`,
              font: '16px "Microsoft YaHei"', style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.fromCssColorString('#1890bd'),
              outlineColor: Cesium.Color.BLUE.withAlpha(0.7), outlineWidth: 2,
              pixelOffset: new Cesium.Cartesian2(0, -10), verticalOrigin: Cesium.VerticalOrigin.TOP
            }
          })
          this.miniViewer.entities.add({
            id: `mini-route-segment-${idx}`,
            name: `${seg.startStation} - ${seg.endStation}`,
            polyline: { positions, width: 4, material: Cesium.Color.fromHsl(hue, 0.65, 0.5, 0.7) },
            label: {
              text: `${seg.startStation} → ${seg.endStation}`,
              font: '14px "Microsoft YaHei"', style: Cesium.LabelStyle.FILL_AND_OUTLINE,
              fillColor: Cesium.Color.fromCssColorString('#1890bd'),
              outlineColor: Cesium.Color.BLUE.withAlpha(0.7), outlineWidth: 2,
              pixelOffset: new Cesium.Cartesian2(0, -10), verticalOrigin: Cesium.VerticalOrigin.TOP
            }
          })
        })

        /* ------- 基础点击 handler（起飞点 / 巡检圆） ------- */
        const handler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas)
        handler.setInputAction((click) => {
          this.handleMapClickForInspection(click)
          if (!this.pickingInspection) {
            const picked = this.viewer.scene.pickPosition(click.position)
            if (!Cesium.defined(picked)) return
            const c = Cesium.Cartographic.fromCartesian(picked)
            const lonNum = Cesium.Math.toDegrees(c.longitude)
            const latNum = Cesium.Math.toDegrees(c.latitude)
            const altNum = c.height
            this.form.takeoffPoint = `[${latNum.toFixed(6)}, ${lonNum.toFixed(6)}, ${altNum.toFixed(2)}]`
            this.viewer.entities.removeById('takeoff-point')
            this.viewer.entities.add({
              id: 'takeoff-point',
              position: Cesium.Cartesian3.fromDegrees(lonNum, latNum, altNum),
              point: { pixelSize: 10, color: Cesium.Color.YELLOW },
              label: { text: '起飞点', font: '14px sans-serif', fillColor: Cesium.Color.WHITE, style: Cesium.LabelStyle.FILL_AND_OUTLINE, outlineWidth: 2, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -12) }
            })
          }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
        handler.setInputAction((movement) => {
          this.updateInspectionRadiusOnMove(movement)
        }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)
        this.clickHandler = handler

        // 首次加载：预设 3D 航线 & 恢复覆盖物
        this.applyPreset3D()
        this.loadSavedRoute()
      })
    },

    /* =================== 任务模式：在图中持久化/恢复 =================== */
    persistCurrentRouteToSavedRoutes (taskIdArg) {
      const taskId = String(taskIdArg || this.taskIdLocal || '').trim()
      if (!taskId) return
      const routeData = {
        type: this.routeType,
        points:
          this.routeType === '航点飞行' ? JSON.parse(JSON.stringify(this.userPoints)) :
          this.routeType === '建图航拍' ? JSON.parse(JSON.stringify(this.gridPath)) :
          this.routeType === '带状航线' ? JSON.parse(JSON.stringify(this.stripPath)) : [],
        areaPoints: JSON.parse(JSON.stringify(this.userAreaPoints || [])),
        basePoints: this.routeType === '带状航线' ? JSON.parse(JSON.stringify(this.userPoints || [])) : [],
        turnaroundCenter: this.turnaroundCenter || null,
        turnaroundRadius: this.turnaroundRadius || 0,
        settings: JSON.parse(JSON.stringify(this.form))
      }
      try {
        const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
        saved[taskId] = routeData
        localStorage.setItem('savedRoutes', JSON.stringify(saved))
      } catch (e) {
        console.warn('[MapView] 持久化 savedRoutes 失败：', e)
      }
    },

    /* =================== 预设 3D 航线（原有） =================== */
    getLngLatPairsFromJson (raw) {
      if (Array.isArray(raw)) {
        if (Array.isArray(raw[0])) return raw
        if (typeof raw[0] === 'number' && raw.length % 2 === 0) {
          const pairs = []
          for (let i = 0; i < raw.length; i += 2) pairs.push([raw[i], raw[i + 1]])
          return pairs
        }
      }
      if (Array.isArray(raw?.routeData?.coords)) return this.getLngLatPairsFromJson(raw.routeData.coords)
      if (Array.isArray(raw?.coords)) return this.getLngLatPairsFromJson(raw.coords)
      if (Array.isArray(raw?.segments)) {
        const first = raw.segments[0]?.coords
        const last  = raw.segments[raw.segments.length - 1]?.coords
        if (first && last) return [...this.getLngLatPairsFromJson(first), ...this.getLngLatPairsFromJson(last)]
      }
      if (raw?.type === 'LineString' && Array.isArray(raw.coordinates)) return raw.coordinates
      if (raw?.type === 'Feature' && raw?.geometry?.type === 'LineString') return raw.geometry.coordinates
      if (raw?.type === 'FeatureCollection' && Array.isArray(raw.features)) {
        return raw.features.filter(f => f?.geometry?.type === 'LineString')
                           .map(f => f.geometry.coordinates).flat()
      }
      return []
    },
    clearPresetEndpoints () {
      if (!this.viewer) return
      ;[this.presetStartId, this.presetEndId, this.presetStartProjId, this.presetEndProjId]
        .forEach(id => this.viewer.entities.removeById(id))
    },
    addPresetEndpointsFromJson (json, height = 300) {
      if (!this.viewer) return
      const pts = this.getLngLatPairsFromJson(json)
      if (!pts || pts.length < 2) return
      const fix = (lng, lat) => {
        const swapped = Math.abs(lng) <= 90 && Math.abs(lat) > 90 && Math.abs(lat) <= 180
        return swapped ? [lat, lng] : [lng, lat]
      }
      const [lng1_raw, lat1_raw] = pts[0]
      const [lngN_raw, latN_raw] = pts[pts.length - 1]
      const [lng1, lat1] = fix(lng1_raw, lat1_raw)
      const [lngN, latN] = fix(lngN_raw, latN_raw)

      const addOne = (idPoint, idProj, lng, lat, labelText) => {
        this.viewer.entities.add({
          id: idPoint,
          position: Cesium.Cartesian3.fromDegrees(this.n(lng), this.n(lat), this.n(height)),
          point: { pixelSize: 10, color: Cesium.Color.RED, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: {
            text: labelText, font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP,
            pixelOffset: new Cesium.Cartesian2(12, -8), fillColor: Cesium.Color.WHITE, showBackground: true
          }
        })
        this.viewer.entities.add({
          id: idProj,
          polyline: {
            positions: [
              Cesium.Cartesian3.fromDegrees(this.n(lng), this.n(lat), this.n(height)),
              Cesium.Cartesian3.fromDegrees(this.n(lng), this.n(lat), 0)
            ],
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.YELLOW, dashLength: 10 })
          }
        })
      }

      this.clearPresetEndpoints()
      addOne(this.presetStartId, this.presetStartProjId, lng1, lat1, '起点')
      addOne(this.presetEndId,   this.presetEndProjId,   lngN, latN, '终点')
    },
    clear3DRouteEntities () {
      if (!this.viewer) return
      const ids = []
      this.viewer.entities.values.forEach((e) => {
        if (typeof e.id === 'string' && e.id.startsWith('route-3d-')) ids.push(e.id)
      })
      ids.forEach(id => this.viewer.entities.removeById(id))
    },
    load3DRouteFromJSON (raw, height = 300) {
      if (!this.viewer) return
      const toSegments = (data) => {
        if (!Array.isArray(data)) {
          if (Array.isArray(data?.segments)) return data.segments
          if (Array.isArray(data?.routes)) return data.routes
          if (Array.isArray(data?.routeData?.coords)) return [{ coords: data.routeData.coords }]
          if (data?.type === 'FeatureCollection' && Array.isArray(data.features)) {
            return data.features.filter(f => f?.geometry?.type === 'LineString')
                                .map(f => ({ coords: f.geometry.coordinates }))
          }
          if (data?.type === 'Feature' && data?.geometry?.type === 'LineString') return [{ coords: data.geometry.coordinates }]
          if (data?.type === 'LineString' && Array.isArray(data.coordinates)) return [{ coords: data.coordinates }]
          if (Array.isArray(data?.coords)) return [{ coords: data.coords }]
          return []
        }
        if (data.length > 0 && Array.isArray(data[0])) return [{ coords: data }]
        return data
      }

      const normalized = toSegments(raw)
      if (!normalized.length) return

      let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity, valid = 0
      normalized.forEach((seg, idx) => {
        let coords = seg.coords
        if (!Array.isArray(coords)) return

        if (Array.isArray(coords[0])) {
          const flat = []
          for (const pt of coords) {
            let [lng, lat] = pt
            const swapped = Math.abs(lng) <= 90 && Math.abs(lat) > 90
            if (swapped) [lng, lat] = [lat, lng]
            flat.push(lng, lat)
          }
          coords = flat
        }

        const [a, b] = coords
        if (typeof a === 'number' && typeof b === 'number') {
          const suspicious = Math.abs(a) <= 90 && Math.abs(b) > 90
          if (suspicious) {
            const tmp = []
            for (let i = 0; i < coords.length; i += 2) tmp.push(coords[i + 1], coords[i])
            coords = tmp
          }
        }
        if (coords.length < 4 || coords.length % 2 !== 0) return

        const positions = []
        for (let i = 0; i < coords.length; i += 2) {
          const lng = coords[i], lat = coords[i + 1]
          if (lng < -180 || lng > 180 || lat < -90 || lat > 90) return
          positions.push(Cesium.Cartesian3.fromDegrees(this.n(lng), this.n(lat), this.n(height)))
          minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng)
          minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat)
        }

        this.viewer.entities.add({
          id: `route-3d-${idx}`,
          polyline: {
            positions,
            width: 15,
            material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.35, color: Cesium.Color.fromCssColorString('#1E90FF') }),
            clampToGround: false
          }
        })
        valid++
      })

      if (!valid) return
      this.fitCameraToBounds(minLng, minLat, maxLng, maxLat, -45)
    },
    applyPreset3D () {
      if (!this.viewer || !this.preset3dKeyLocal) return
      const json = FILE_MAP[this.preset3dKeyLocal]
      if (!json) return
      this.clear3DRouteEntities()
      this.load3DRouteFromJSON(json, 500)
      this.addPresetEndpointsFromJson(json, 500)
      // ★ 根据 route3d_* / route_* 设置初始相机
      this.setInitialCameraForPreset(this.preset3dKeyLocal)
      this.animationPlaying = false
      this.viewer.clock.shouldAnimate = true //自动播放点位呼吸

      // 示例：route_1 添加呼吸高亮
      this.removeBreathingMarker('route1-focus-a')
      this.removeBreathingMarker('route1-focus-b')
      if (this.preset3dKeyLocal === 'route_1') {
        this.addBreathingMarker('route1-focus-a', 116.054938, 39.595313, { label: '进京车检', iconSize: 38, ringMin: 24, ringMax: 140, periodMs: 1600 })
        this.addBreathingMarker('route1-focus-b', 116.033867, 39.537162, { label: '拒马河大桥', iconSize: 38, ringMin: 24, ringMax: 140, periodMs: 1600 })
      }
    },

    /* =================== 航线：恢复/保存（含巡检圆） =================== */
    loadSavedRoute () {
      const allowRestoreOnPreset = this.wantRestore
      if (this.routeType === '预设航线' && !allowRestoreOnPreset) return

      this.isLoadingRoute = true
      try {
        const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
        this.savedRoutes = saved
        if (!this.taskIdLocal) return
        const route = saved[this.taskIdLocal]
        if (!route) return

        if (this.routeType === '预设航线') {
          this.restoreUserOverlays(route)
          return
        }

        this.routeType = route.type
        this.updateButtonVisibility()

        if (route.type === '航点飞行') {
          this.userPoints = this.coercePoints(route.points || [], this.flightHeight)
          if (this.userPoints.length >= 2) this.generateRouteFromPoints()
          this.restorePointEntities('user-point-', this.userPoints, true)
        } else if (route.type === '建图航拍') {
          this.gridPath = this.coercePoints(route.points || [], this.flightHeight)
          this.userAreaPoints = this.coercePoints(route.areaPoints || [], 0)
          if (this.gridPath.length >= 2) this.addDroneTrajectory(this.gridPath)
          this.drawAreaPolygon()
        } else if (route.type === '带状航线') {
          this.stripPath = this.coercePoints(route.points || [], this.flightHeight)
          this.userPoints = this.coercePoints(route.basePoints || [], this.flightHeight)
          if (this.stripPath.length >= 2) this.addDroneTrajectory(this.stripPath)
          this.restorePointEntities('user-point-', this.userPoints, true)
        }

        if (route.turnaroundCenter && route.turnaroundRadius > 0) {
          this.turnaroundCenter = { lng: this.n(route.turnaroundCenter.lng), lat: this.n(route.turnaroundCenter.lat) }
          this.turnaroundRadius = this.n(route.turnaroundRadius)
          this.drawTurnaroundCircle()
        }
      } catch (e) {
        console.error('加载航线失败', e)
        alert(`加载航线失败: ${e.message}`)
      } finally {
        this.isLoadingRoute = false
      }
    },
    restoreUserOverlays (route) {
      if (!this.viewer || !route) return
      const idsToRemove = []
      this.viewer.entities.values.forEach(e => {
        const id = String(e.id || '')
        if (
          id.startsWith('user-point-') ||
          id.startsWith('projection-line-') ||
          id.startsWith('area-point-') ||
          id === 'area-polygon' ||
          id === 'user-strip-preview' ||
          id === 'turnaround-circle' ||
          id === 'turnaround-point'
        ) idsToRemove.push(id)
      })
      idsToRemove.forEach(id => this.viewer.entities.removeById(id))

      if (Array.isArray(route.basePoints) && route.basePoints.length) {
        this.userPoints = this.coercePoints(route.basePoints, this.flightHeight)
        this.restorePointEntities('user-point-', this.userPoints, true)
      } else if (route.type === '航点飞行' && Array.isArray(route.points) && route.points.length) {
        this.userPoints = this.coercePoints(route.points, this.flightHeight)
        this.restorePointEntities('user-point-', this.userPoints, true)
      } else {
        this.userPoints = []
      }

      this.userAreaPoints = this.coercePoints(route.areaPoints || [], 0)
      this.drawAreaPolygon()

      if (route.type === '带状航线' && Array.isArray(route.points) && route.points.length >= 2) {
        this.stripPath = this.coercePoints(route.points, this.flightHeight)
        this.viewer.entities.add({
          id: 'user-strip-preview',
          polyline: {
            positions: this.stripPath.map(p => Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt)),
            width: 2,
            material: Cesium.Color.CYAN.withAlpha(0.6)
          }
        })
      } else {
        this.viewer.entities.removeById('user-strip-preview')
        this.stripPath = []
      }

      if (route.turnaroundCenter && route.turnaroundRadius > 0) {
        this.turnaroundCenter = { lng: this.n(route.turnaroundCenter.lng), lat: this.n(route.turnaroundCenter.lat) }
        this.turnaroundRadius = this.n(route.turnaroundRadius)
        this.drawTurnaroundCircle()
        this.viewer.entities.add({
          id: 'turnaround-point',
          position: Cesium.Cartesian3.fromDegrees(this.turnaroundCenter.lng, this.turnaroundCenter.lat, 0),
          point: { pixelSize: 10, color: Cesium.Color.YELLOW, outlineColor: Cesium.Color.BLACK, outlineWidth: 2 },
          label: { text: '折返点', font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP, pixelOffset: new Cesium.Cartesian2(12, -8), showBackground: true }
        })
      }
    },
    drawTurnaroundCircle () {
      this.viewer.entities.removeById('turnaround-circle')
      if (!this.turnaroundCenter || !this.turnaroundRadius) return
      this.viewer.entities.add({
        id: 'turnaround-circle',
        position: Cesium.Cartesian3.fromDegrees(this.n(this.turnaroundCenter.lng), this.n(this.turnaroundCenter.lat), 0),
        ellipse: {
          semiMajorAxis: this.n(this.turnaroundRadius),
          semiMinorAxis: this.n(this.turnaroundRadius),
          material: Cesium.Color.fromCssColorString('#1E90FF').withAlpha(0.25),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#1E90FF')
        }
      })
    },

    saveSettings () {
      if (!this.taskIdLocal) { alert('任务ID无效，无法保存设置'); return }
      const routeData = {
        type: this.routeType,
        points:
          this.routeType === '航点飞行' ? JSON.parse(JSON.stringify(this.userPoints)) :
          this.routeType === '建图航拍' ? JSON.parse(JSON.stringify(this.gridPath)) :
          this.routeType === '带状航线' ? JSON.parse(JSON.stringify(this.stripPath)) : [],
        areaPoints: JSON.parse(JSON.stringify(this.userAreaPoints || [])),
        basePoints: this.routeType === '带状航线' ? JSON.parse(JSON.stringify(this.userPoints || [])) : [],
        turnaroundCenter: this.turnaroundCenter || null,
        turnaroundRadius: this.turnaroundRadius || 0,
        settings: JSON.parse(JSON.stringify(this.form))
      }
      const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
      saved[this.taskIdLocal] = routeData
      localStorage.setItem('savedRoutes', JSON.stringify(saved))
      alert('设置已保存')
    },

    returnToRoutePlan () {
      try { if (!this.airspaceMode) this.saveSettings() } catch {}
      this.$emit('action', { type: 'back-to-menu' })
    },

    /* ================= 按钮显示（任务） ================= */
    updateButtonVisibility () {
      this.showButtons = {
        enablePointMark: this.routeType === '航点飞行',
        generatePointPath: this.routeType === '航点飞行',
        flightAnimation: this.routeType === '航点飞行' || this.routeType === '带状航线' || this.routeType === '预设航线',
        drawArea: this.routeType === '建图航拍',
        generateGrid: this.routeType === '建图航拍',
        previewGridPath: this.routeType === '建图航拍',
        generateStripPath: this.routeType === '带状航线'
      }
    },

    /* ================= 航点/区域/拖拽/动画（任务） ================= */
    restorePointEntities (prefix, points, draggable = false) {
      const pts = this.coercePoints(points, this.flightHeight)
      pts.forEach((p, i) => {
        const id = `${prefix}${i + 1}`
        const old = this.viewer.entities.getById(id)
        if (old) this.viewer.entities.remove(old)
        this.viewer.entities.add({
          id,
          position: Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt),
          point: { pixelSize: 10, color: this.selectedPointIndex === i ? Cesium.Color.YELLOW : Cesium.Color.RED, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: {
            text: `P${i + 1} (${p.alt.toFixed(0)}m)`,
            font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP,
            pixelOffset: new Cesium.Cartesian2(12, -8), fillColor: Cesium.Color.WHITE, showBackground: true
          }
        })
        this.viewer.entities.add({
          id: `projection-line-${i + 1}`,
          polyline: {
            positions: [
              Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt),
              Cesium.Cartesian3.fromDegrees(p.lng, p.lat, 0)
            ],
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({ color: Cesium.Color.YELLOW, dashLength: 10 })
          }
        })
      })
      if (draggable) this.attachDragHandler()
    },
    updateSelectedPointHeight () {
      if (this.routeType === '预设航线') return
      if (this.selectedPointIndex == null) return
      const i = this.selectedPointIndex
      if (i < 0 || i >= this.userPoints.length) return
      this.userPoints[i].alt = this.flightHeight
      const id = `user-point-${i + 1}`
      const e = this.viewer.entities.getById(id)
      if (e) {
        const p = this.normPoint(this.userPoints[i], this.flightHeight)
        e.position = Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt)
        e.label.text = `P${i + 1} (${this.flightHeight.toFixed(0)}m)`
        const line = this.viewer.entities.getById(`projection-line-${i + 1}`)
        if (line) {
          line.polyline.positions = [
            Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt),
            Cesium.Cartesian3.fromDegrees(p.lng, p.lat, 0)
          ]
        }
      }
    },

    toggleClickToAddPoint () {
      if (this.routeType === '预设航线') return alert('预设航线不可编辑航点')
      if (!this.clickPointEnabled) this.enableClickToAddPoint()
      else this.disableClickToAddPoint()
      this.clickPointEnabled = !this.clickPointEnabled
    },
    enableClickToAddPoint () { this.attachDragHandler() },
    disableClickToAddPoint () {
      if (this.clickHandler) { this.clickHandler.destroy(); this.clickHandler = null }
    },

    attachDragHandler () {
      if (this.routeType === '预设航线') return
      if (this.clickHandler) return
      this.clickHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas)

      // 左键：选中/新增航点
      this.clickHandler.setInputAction((movement) => {
        if (!this.drawAreaEnabled) return
        const pos = this.viewer.scene.pickPosition(movement.position)
        if (!Cesium.defined(pos)) return
        const c = Cesium.Cartographic.fromCartesian(pos)
        const lon = Cesium.Math.toDegrees(c.longitude), lat = Cesium.Math.toDegrees(c.latitude), alt = 0
        const idx = this.userAreaPoints.length + 1
        this.userAreaPoints.push({ lng: lon, lat, alt })

        // 只在“非空域模式”下显示绿色顶点与标签
        if (!this.airspaceMode) {
          this.viewer.entities.add({
            id: `area-point-${idx}`,
            position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
            point: { pixelSize: 10, color: Cesium.Color.LIME, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
            label: { text: `A${idx}`, font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP, pixelOffset: new Cesium.Cartesian2(12, -8), showBackground: true }
          })
        }

        this.updateAreaPolygonEntity()
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK)


      // 左键按下：开始拖动
      this.clickHandler.setInputAction((movement) => {
        const picked = this.viewer.scene.pick(movement.position)
        if (!Cesium.defined(picked) || !picked.id || typeof picked.id.id !== 'string') return
        if (!picked.id.id.startsWith('user-point-') && !picked.id.id.startsWith('area-point-')) return
        this._draggedEntity = picked.id
        this.viewer.scene.screenSpaceCameraController.enableRotate = false

        if (picked.id.id.startsWith('user-point-')) {
          const carto = Cesium.Cartographic.fromCartesian(this.viewer.scene.pickPosition(movement.position))
          if (carto) {
            const lon = Cesium.Math.toDegrees(carto.longitude)
            const lat = Cesium.Math.toDegrees(carto.latitude)
            const alt = carto.height + 20
            this._dragPromptEntity = this.viewer.entities.add({
              id: 'drag-prompt',
              position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
              label: {
                text: '拖拽移动经纬度',
                font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -10), fillColor: Cesium.Color.YELLOW,
                showBackground: true, backgroundColor: Cesium.Color.BLACK.withAlpha(0.7)
              }
            })
          }
        }
      }, Cesium.ScreenSpaceEventType.LEFT_DOWN)

      // 拖动中
      this.clickHandler.setInputAction((movement) => {
        if (!this._draggedEntity) return
        const newPos = this.viewer.scene.pickPosition(movement.endPosition)
        if (!Cesium.defined(newPos)) return
        const carto = Cesium.Cartographic.fromCartesian(newPos)
        const lon = Cesium.Math.toDegrees(carto.longitude)
        const lat = Cesium.Math.toDegrees(carto.latitude)
        const id = this._draggedEntity.id

        if (id.startsWith('user-point-')) {
          const idx = parseInt(id.split('-')[2], 10) - 1
          if (idx >= 0 && idx < this.userPoints.length) {
            const alt = this.userPoints[idx].alt
            this.userPoints[idx] = { lng: lon, lat, alt }
            this._draggedEntity.position.setValue(Cesium.Cartesian3.fromDegrees(lon, lat, alt))
            this._draggedEntity.label.text = `P${idx + 1} (${alt.toFixed(0)}m)`
            const line = this.viewer.entities.getById(`projection-line-${idx + 1}`)
            if (line) {
              line.polyline.positions = [
                Cesium.Cartesian3.fromDegrees(lon, lat, alt),
                Cesium.Cartesian3.fromDegrees(lon, lat, 0)
              ]
            }
            if (this._dragPromptEntity) this._dragPromptEntity.position.setValue(Cesium.Cartesian3.fromDegrees(lon, lat, alt + 20))
            this.selectedPointIndex = idx
            this.flightHeight = alt
          }
        } else if (id.startsWith('area-point-')) {
          const idx = parseInt(id.split('-')[2], 10) - 1
          if (idx >= 0 && idx < this.userAreaPoints.length) {
            this.userAreaPoints[idx] = { lng: lon, lat, alt: 0 }
            this._draggedEntity.position.setValue(Cesium.Cartesian3.fromDegrees(lon, lat, 0))
            this.updateAreaPolygonEntity()
          }
        }
      }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)

      // 松开
      this.clickHandler.setInputAction(() => {
        if (this._dragPromptEntity) { this.viewer.entities.remove(this._dragPromptEntity); this._dragPromptEntity = null }
        this._draggedEntity = null
        this.viewer.scene.screenSpaceCameraController.enableRotate = true
      }, Cesium.ScreenSpaceEventType.LEFT_UP)

      // 右键删除航点
      this.clickHandler.setInputAction((movement) => {
        const picked = this.viewer.scene.pick(movement.position)
        if (!Cesium.defined(picked) || !picked.id || !picked.id.id.startsWith('user-point-')) return
        const idx = parseInt(picked.id.id.split('-')[2], 10) - 1
        if (idx >= 0 && idx < this.userPoints.length) {
          this.viewer.entities.removeById(`user-point-${idx + 1}`)
          this.viewer.entities.removeById(`projection-line-${idx + 1}`)
          this.userPoints.splice(idx, 1)
          this.restorePointEntities('user-point-', this.userPoints, true)
          this.selectedPointIndex = null
          if (this.taskIdLocal) {
            const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
            saved[this.taskIdLocal] = { type: '航点飞行', points: JSON.parse(JSON.stringify(this.userPoints)) }
            localStorage.setItem('savedRoutes', JSON.stringify(saved))
          }
        }
        if (this._dragPromptEntity) {
          this.viewer.entities.removeById('drag-prompt')
          this._dragPromptEntity = null
        }
        this._draggedEntity = null
        this.viewer.scene.screenSpaceCameraController.enableRotate = true
      }, Cesium.ScreenSpaceEventType.RIGHT_CLICK)
    },

    generateRouteFromPoints () {
      if (this.routeType === '预设航线') return alert('预设航线不可编辑')
      if (this.userPoints.length < 2) return alert('请至少打两个点')
      this.viewer.entities.removeById('drone-path')
      this.viewer.entities.removeById('drone-entity')
      this.viewer.entities.removeById('view-cone')
      this.viewer.entities.removeById('debug-cone-vertex')
      if (this.coneMoveHandler) { this.coneMoveHandler.destroy(); this.coneMoveHandler = null }

      this.dronePath = this.coercePoints(this.userPoints, this.flightHeight)
      this.addDroneTrajectory(this.dronePath)
      this.addViewCone()
      this.enableViewConeRotation()

      if (this.taskIdLocal) {
        const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
        saved[this.taskIdLocal] = { type: '航点飞行', points: JSON.parse(JSON.stringify(this.userPoints)) }
        localStorage.setItem('savedRoutes', JSON.stringify(saved))
      }
    },
    addDroneTrajectory (path = this.dronePath) {
      const pts = this.coercePoints(path, this.flightHeight)
      if (!pts || pts.length < 2) return

      this.startTime = Cesium.JulianDate.now()
      this.stopTime = Cesium.JulianDate.addSeconds(this.startTime, pts.length * 2, new Cesium.JulianDate())

      const positions = pts.map(p => Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt))
      const oldPath = this.viewer.entities.getById('drone-path')
      if (oldPath) this.viewer.entities.remove(oldPath)
      this.viewer.entities.add({
        id: 'drone-path',
        polyline: { positions, width: 8, material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.5, color: Cesium.Color.CYAN }) }
      })

      const sampled = new Cesium.SampledPositionProperty()
      pts.forEach((p, i) => {
        const t = Cesium.JulianDate.addSeconds(this.startTime, i * 2, new Cesium.JulianDate())
        sampled.addSample(t, Cesium.Cartesian3.fromDegrees(p.lng, p.lat, p.alt))
      })

      const oldDrone = this.viewer.entities.getById('drone-entity')
      if (oldDrone) this.viewer.entities.remove(oldDrone)
      this.viewer.entities.add({
        id: 'drone-entity',
        availability: new Cesium.TimeIntervalCollection([new Cesium.TimeInterval({ start: this.startTime, stop: this.stopTime })]),
        position: sampled,
        point: { pixelSize: 10, color: Cesium.Color.BLUE, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
        path: { resolution: 1, material: new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.2, color: Cesium.Color.YELLOW }), width: 2 }
      })

      this.viewer.clock.startTime = this.startTime.clone()
      this.viewer.clock.stopTime = this.stopTime.clone()
      this.viewer.clock.currentTime = this.startTime.clone()
      this.viewer.clock.clockRange = Cesium.ClockRange.CLAMPED
      this.viewer.clock.multiplier = 1
      this.viewer.clock.shouldAnimate = this.animationPlaying
      if (this.viewer.timeline) this.viewer.timeline.zoomTo(this.startTime, this.stopTime)
    },
    addViewCone () {
      const oldCone = this.viewer.entities.getById('view-cone')
      if (oldCone) this.viewer.entities.remove(oldCone)
      const oldDebug = this.viewer.entities.getById('debug-cone-vertex')
      if (oldDebug) this.viewer.entities.remove(oldDebug)

      const coneLength = 100, coneRadius = 15
      this.viewer.entities.add({
        id: 'view-cone',
        position: new Cesium.CallbackProperty((time) => {
          const drone = this.viewer.entities.getById('drone-entity')
          if (!drone) return Cesium.Cartesian3.fromDegrees(0, 0, 0)
          return drone.position.getValue(time) || Cesium.Cartesian3.fromDegrees(0, 0, 0)
        }, false),
        orientation: new Cesium.CallbackProperty((time) => {
          const drone = this.viewer.entities.getById('drone-entity')
          if (!drone) return Cesium.Quaternion.IDENTITY
          const pos = drone.position.getValue(time)
          if (!pos) return Cesium.Quaternion.IDENTITY
          return Cesium.Transforms.headingPitchRollQuaternion(pos, new Cesium.HeadingPitchRoll(this.coneHeading, Cesium.Math.toRadians(-90), 0))
        }, false),
        cylinder: { length: coneLength, topRadius: 0, bottomRadius: coneRadius, material: Cesium.Color.YELLOW.withAlpha(0.5), outline: true, outlineColor: Cesium.Color.ORANGE }
      })

      this.viewer.entities.add({
        id: 'debug-cone-vertex',
        position: new Cesium.CallbackProperty((time) => {
          const drone = this.viewer.entities.getById('drone-entity')
          if (!drone) return Cesium.Cartesian3.fromDegrees(0, 0, 0)
          return drone.position.getValue(time)
        }, false),
        point: { pixelSize: 5, color: Cesium.Color.RED, outlineColor: Cesium.Color.WHITE, outlineWidth: 1 }
      })
    },
    enableViewConeRotation () {
      if (this.coneMoveHandler) return
      this.coneMoveHandler = new Cesium.ScreenSpaceEventHandler(this.viewer.scene.canvas)
      this.coneMoveHandler.setInputAction((movement) => {
        const earth = this.viewer.scene.pickPosition(movement.endPosition)
        if (!Cesium.defined(earth)) return
        const drone = this.viewer.entities.getById('drone-entity')
        if (!drone) return
        const pos = drone.position.getValue(this.viewer.clock.currentTime)
        if (!pos) return
        const from = Cesium.Cartographic.fromCartesian(pos)
        const to = Cesium.Cartographic.fromCartesian(earth)
        this.coneHeading = Math.atan2(to.longitude - from.longitude, to.latitude - from.latitude)
      }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)
    },
    toggleAnimation () {
      this.animationPlaying = !this.animationPlaying
      this.viewer.clock.shouldAnimate = this.animationPlaying
    },

    /* ================= 区域/网格/带状（任务） ================= */
    toggleDrawArea () {
      if (this.routeType === '预设航线') return alert('预设航线不可编辑区域')
      if (!this.drawAreaEnabled) this.enableDrawArea(); else this.disableDrawArea()
      this.drawAreaEnabled = !this.drawAreaEnabled
    },
    enableDrawArea () {
      if (!this.clickHandler) this.attachDragHandler()
      this.clickHandler.setInputAction((movement) => {
        if (!this.drawAreaEnabled) return
        const pos = this.viewer.scene.pickPosition(movement.position)
        if (!Cesium.defined(pos)) return
        const c = Cesium.Cartographic.fromCartesian(pos)
        const lon = Cesium.Math.toDegrees(c.longitude), lat = Cesium.Math.toDegrees(c.latitude), alt = 0
        const idx = this.userAreaPoints.length + 1
        this.userAreaPoints.push({ lng: lon, lat, alt })
        this.viewer.entities.add({
          id: `area-point-${idx}`,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
          point: { pixelSize: 10, color: Cesium.Color.LIME, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: { text: `A${idx}`, font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP, pixelOffset: new Cesium.Cartesian2(12, -8), showBackground: true }
        })
        this.updateAreaPolygonEntity()
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
    },
    disableDrawArea () {
      if (this.clickHandler) { this.clickHandler.destroy(); this.clickHandler = null }
      this.attachDragHandler()
    },
    updateAreaPolygonEntity () {
      const old = this.viewer.entities.getById('area-polygon')
      if (old) this.viewer.entities.remove(old)
      if (this.userAreaPoints.length < 3) return
      const arrHeights = this.userAreaPoints.flatMap(p => [this.n(p.lng), this.n(p.lat), this.n(p.alt)])
      this.viewer.entities.add({
        id: 'area-polygon',
        polygon: {
          hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(arrHeights),
          material: this.airspaceMode
            ? Cesium.Color.fromCssColorString(AIRSPACE_COLOR[this.airspaceForm.type] || '#6b7280').withAlpha(0.35)
            : Cesium.Color.BLUE.withAlpha(0.25),
          outline: true,
          outlineColor: this.airspaceMode
            ? Cesium.Color.fromCssColorString(AIRSPACE_COLOR[this.airspaceForm.type] || '#6b7280')
            : Cesium.Color.BLUE
        }
      })
    },

    drawAreaPolygon () {
      const old = this.viewer.entities.getById('area-polygon'); if (old) this.viewer.entities.remove(old)
      if (!this.userAreaPoints.length) return

      // 只在“非空域模式”下画绿色顶点与标签
      if (!this.airspaceMode) {
        this.userAreaPoints.forEach((p, idx) => {
          const id = `area-point-${idx + 1}`
          const e = this.viewer.entities.getById(id); if (e) this.viewer.entities.remove(e)
          this.viewer.entities.add({
            id,
            position: Cesium.Cartesian3.fromDegrees(this.n(p.lng), this.n(p.lat), 0),
            point: { pixelSize: 10, color: Cesium.Color.LIME, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
            label: { text: `A${idx + 1}`, font: '12px sans-serif', verticalOrigin: Cesium.VerticalOrigin.TOP, pixelOffset: new Cesium.Cartesian2(12, -8), showBackground: true }
          })
        })
      }

      this.updateAreaPolygonEntity()
      this.attachDragHandler()
    },

    getPolygonBounds (points) {
      const pts = this.coercePoints(points, 0)
      const lngs = pts.map(p => p.lng), lats = pts.map(p => p.lat)
      return { minLng: Math.min(...lngs), maxLng: Math.max(...lngs), minLat: Math.min(...lats), maxLat: Math.max(...lats) }
    },
    generateGridPath () {
      if (this.routeType === '预设航线') return alert('预设航线不可编辑')
      if (this.userAreaPoints.length < 3) return alert('请至少绘制三个点以形成多边形区域')
      this.gridPath = []
      const step = 80
      const bounds = this.getPolygonBounds(this.userAreaPoints)
      const stepLat = step / 111111
      const stepLng = step / (111111 * Math.cos(Cesium.Math.toRadians(bounds.minLat)))
      const minLat = bounds.minLat - stepLat / 2, maxLat = bounds.maxLat + stepLat / 2
      const minLng = bounds.minLng - stepLng / 2, maxLng = bounds.maxLng + stepLng / 2
      const polygon = { type: 'Polygon', coordinates: [this.userAreaPoints.map(p => [this.n(p.lng), this.n(p.lat)]).concat([[this.n(this.userAreaPoints[0].lng), this.n(this.userAreaPoints[0].lat)]])] }

      for (let lat = minLat; lat <= maxLat; lat += stepLat) {
        for (let lng = minLng; lng <= maxLng; lng += stepLng) {
          const point = turf.point([lng, lat])
          if (turf.booleanPointInPolygon(point, polygon)) this.gridPath.push({ lng, lat, alt: this.flightHeight })
        }
      }
      const grouped = {}
      this.gridPath.forEach(p => { const key = p.lat.toFixed(5); (grouped[key] ||= []).push(p) })
      let ordered = []
      Object.keys(grouped).sort((a, b) => parseFloat(a) - parseFloat(b)).forEach((key, i) => {
        const row = grouped[key].sort((a, b) => a.lng - b.lng)
        if (i % 2 === 1) row.reverse()
        ordered = ordered.concat(row)
      })
      this.gridPath = ordered

      if (this.gridPath.length > 1) {
        this.addDroneTrajectory(this.gridPath)
        if (this.taskIdLocal) {
          const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
          saved[this.taskIdLocal] = { type: '建图航拍', points: JSON.parse(JSON.stringify(this.gridPath)), areaPoints: JSON.parse(JSON.stringify(this.userAreaPoints)) }
          localStorage.setItem('savedRoutes', JSON.stringify(saved))
        }
      } else {
        alert('未生成有效网格路径，请检查多边形区域')
      }
    },
    previewGridPath () {
      if (this.gridPath.length < 2) return alert('请先生成航拍网格')
      this.toggleAnimation()
    },
    generateStripPath () {
      if (this.routeType === '预设航线') return alert('预设航线不可编辑')
      if (this.userPoints.length < 2) return alert('请至少打两个点以定义带状区域')
      this.stripPath = []
      const step = 5, width = 50
      const [p1, p2] = this.coercePoints(this.userPoints, this.flightHeight)
      const angle = Math.atan2(p2.lat - p1.lat, p2.lng - p1.lng)
      for (let offset = -width / 2; offset <= width / 2; offset += step) {
        const dx = (offset * Math.cos(angle + Math.PI / 2)) / 111111
        const dy = (offset * Math.sin(angle + Math.PI / 2)) / 111111
        this.stripPath.push(
          { lng: p1.lng + dx, lat: p1.lat + dy, alt: p1.alt },
          { lng: p2.lng + dx, lat: p2.lat + dy, alt: p2.alt }
        )
      }
      this.addDroneTrajectory(this.stripPath)
      if (this.taskIdLocal) {
        const saved = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
        saved[this.taskIdLocal] = { type: '带状航线', points: JSON.parse(JSON.stringify(this.stripPath)), basePoints: JSON.parse(JSON.stringify(this.userPoints)) }
        localStorage.setItem('savedRoutes', JSON.stringify(saved))
      }
    },

    /* ================= 任务弹窗（原有） ================= */
    openTaskDialog (edit = false, task = null) {
      this.editMode = edit
      if (edit && task) {
        this.currentTask = JSON.parse(JSON.stringify(task))
      } else if (edit && !task) {
        const tasks = JSON.parse(localStorage.getItem('inspectionTasks') || '{}')
        if (this.taskIdLocal && tasks[this.taskIdLocal]) this.currentTask = JSON.parse(JSON.stringify(tasks[this.taskIdLocal]))
      } else {
        this.currentTask = {
          id: `task-${Date.now()}`,
          name: '', taskType: '', type: [], takeoff: '',
          route_id: '', route: '', inspectCenter: '', inspectRadius: '',
          time_window: [], flightCount: 1, executionTime: 'immediate',
          customExecutionTime: '', expectedFinish: ''
        }
      }
      this.taskDialogVisible = true
    },
    submitTask () {
      if (!this.currentTask.id || !this.currentTask.taskType) {
        (this.$message?.warning || alert)('请填写任务ID并选择任务类型')
        return
      }
      try {
        const tasks = JSON.parse(localStorage.getItem('inspectionTasks') || '{}')
        tasks[this.currentTask.id] = {
          ...this.currentTask,
          routeType: this.routeType || '',
          preset3d: this.preset3dKeyLocal || '',
          preset3dKey: this.preset3dKeyLocal || ''
        }
        localStorage.setItem('inspectionTasks', JSON.stringify(tasks))
        this.persistCurrentRouteToSavedRoutes(this.currentTask.id)
      } catch (e) {
        console.error('保存任务失败：', e)
        ;(this.$message?.error || alert)('保存任务失败，请重试')
        return
      }
      this.taskDialogVisible = false
      this.openAirportEditor(this.currentTask.id, this.editMode ? 'edit' : 'create')
    },
    openAirportEditor (id, mode = '') {
      this.$emit('action', { type: 'open-airport-task', data: { id, mode, preset3dKey: this.preset3dKeyLocal || '' } })
    },
    updateInspectionTypes () { this.currentTask.type = [] },

    /* ================= 点位扫描：巡检圆 ================= */
    enablePickInspectionArea () {
      this.pickingInspection = true
      this.inspectionCenter = null
      this.inspectionRadius = 0
      if (this.viewer) {
        this.viewer.entities.removeById(this.inspectionCenterId)
        this.viewer.entities.removeById(this.inspectionCircleId)
      }
      this.taskDialogVisible = false
      ;(this.$message?.info || alert)('首次单击确定圆心，移动鼠标调整半径，第二次单击确定范围。')
    },
    handleMapClickForInspection (click) {
      if (!this.pickingInspection) return
      const carto = this.getCartographicFromClick(click)
      if (!carto) { this.$message?.warning?.('无法获取点击位置坐标'); return }

      if (!this.inspectionCenter) {
        // 第一次：定圆心
        this.inspectionCenter = carto
        const lon = Cesium.Math.toDegrees(carto.longitude)
        const lat = Cesium.Math.toDegrees(carto.latitude)
        this.viewer.entities.add({
          id: this.inspectionCenterId,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
          point: { pixelSize: 10, color: Cesium.Color.SKYBLUE, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
          label: { text: '巡检圆心', font: '14px sans-serif', fillColor: Cesium.Color.WHITE, style: Cesium.LabelStyle.FILL_AND_OUTLINE, outlineWidth: 2, verticalOrigin: Cesium.VerticalOrigin.TOP, pixelOffset: new Cesium.Cartesian2(12, -8), showBackground: true }
        })
        const radiusAccessor = new Cesium.CallbackProperty(() => Math.max(1, this.inspectionRadius), false)
        this.viewer.entities.add({
          id: this.inspectionCircleId,
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
          ellipse: { semiMajorAxis: radiusAccessor, semiMinorAxis: radiusAccessor, material: Cesium.Color.BLUE.withAlpha(0.25), outline: true, outlineColor: Cesium.Color.BLUE, height: 0 }
        })
      } else {
        // 第二次：固定半径，写回
        const cLon = Cesium.Math.toDegrees(this.inspectionCenter.longitude)
        const cLat = Cesium.Math.toDegrees(this.inspectionCenter.latitude)
        const radiusFixed = Math.round(Math.max(1, this.inspectionRadius))
        this.currentTask.inspectCenter = `${cLat.toFixed(6)}, ${cLon.toFixed(6)}`
        this.currentTask.inspectRadius = String(radiusFixed)

        this.turnaroundCenter = { lng: cLon, lat: cLat }
        this.turnaroundRadius = radiusFixed

        this.pickingInspection = false
        this.taskDialogVisible = true
        ;(this.$message?.success || alert)('巡检区域已确定')
      }
    },
    updateInspectionRadiusOnMove (movement) {
      if (!this.pickingInspection || !this.inspectionCenter) return
      const scene = this.viewer.scene
      const camera = this.viewer.camera

      let targetCarto = null
      if (scene.pickPositionSupported) {
        const cartesian = scene.pickPosition(movement.endPosition)
        if (Cesium.defined(cartesian)) targetCarto = Cesium.Cartographic.fromCartesian(cartesian)
      }
      if (!targetCarto) {
        const ray = camera.getPickRay(movement.endPosition)
        if (ray) {
          const cartesian = scene.globe.pick(ray, scene)
          if (Cesium.defined(cartesian)) targetCarto = Cesium.Cartographic.fromCartesian(cartesian)
        }
      }
      if (!targetCarto) {
        const ellipsoidCartesian = camera.pickEllipsoid(movement.endPosition, Cesium.Ellipsoid.WGS84)
        if (Cesium.defined(ellipsoidCartesian)) targetCarto = Cesium.Cartographic.fromCartesian(ellipsoidCartesian)
      }
      if (!targetCarto) return

      const geodesic = new Cesium.EllipsoidGeodesic(this.inspectionCenter, targetCarto)
      const d = geodesic.surfaceDistance || 0
      this.inspectionRadius = d
    },
    getCartographicFromClick (click) {
      const scene = this.viewer.scene
      const camera = this.viewer.camera
      if (scene.pickPositionSupported) {
        const cartesian = scene.pickPosition(click.position)
        if (Cesium.defined(cartesian)) return Cesium.Cartographic.fromCartesian(cartesian)
      }
      const ray = camera.getPickRay(click.position)
      if (ray) {
        const cartesian = scene.globe.pick(ray, scene)
        if (Cesium.defined(cartesian)) return Cesium.Cartographic.fromCartesian(cartesian)
      }
      const ellipsoidCartesian = camera.pickEllipsoid(click.position, Cesium.Ellipsoid.WGS84)
      if (Cesium.defined(ellipsoidCartesian)) return Cesium.Cartographic.fromCartesian(ellipsoidCartesian)
      return null
    },

    /* ========================= 空域模式 ========================= */
    /** 进入空域模式（由 RouteShell 通过 openPayload 触发） */
    enterAirspaceMode (payload = {}) {
      // 关闭任务模式按钮显示 & 切换到“空域编辑”
      this.airspaceMode = true
      this.airspaceDrawing = !!payload.drawNew
      this.activeTab = 'airspace'

      // 清理任务相关可视对象
      this.viewer && this.viewer.entities.values
        .filter(e => String(e.id || '').startsWith('drone-') || String(e.id || '').startsWith('view-cone'))
        .forEach(e => this.viewer.entities.remove(e))

      // 读取/初始化空域数据（兼容 validFrom/validTo、note）
      this.airspaceIdLocal = String(payload.airspaceId || payload.id || `air-${Date.now()}`)
      this.airspaceForm.name = payload.name || ''
      this.airspaceForm.type = payload.airspaceType || '危险区'
      this.airspaceForm.cover = payload.cover || ''
      this.airspaceForm.start = payload.start || payload.validFrom || ''
      this.airspaceForm.end = payload.end || payload.validTo || ''
      this.airspaceForm.remark = payload.remark || payload.note || ''

      // 载入多边形（若给定）
      const poly = payload.polygon || []
      this.userAreaPoints = this.coercePoints(poly, 0)
      this.drawAreaPolygon()
      if (this.userAreaPoints.length) this.fitCameraToPoints(this.userAreaPoints)

      // 若要求立即绘制，则开启绘制
      if (this.airspaceDrawing) {
        this.drawAreaEnabled = true
        this.enableDrawArea()
      } else {
        this.drawAreaEnabled = false
      }

      // 防御式清理：空域模式下不显示任何 area-point-* 顶点
      let _i = 1
      while (this.viewer && this.viewer.entities.getById(`area-point-${_i}`)) {
        this.viewer.entities.removeById(`area-point-${_i}`)
        _i++
      }
      },



    /** 退出空域模式（回到任务 UI；默认不清空多边形，除非 forceClear=true） */
    exitAirspaceMode (forceClear = false) {
      if (!this.airspaceMode) return
      this.airspaceMode = false
      this.airspaceDrawing = false
      if (forceClear) {
        this.userAreaPoints = []
        this.viewer && this.viewer.entities.removeById('area-polygon')
      }
      this.updateButtonVisibility()
      this.activeTab = 'base'
    },

    /** 开/关绘制（替换区域） */
    toggleAirspaceDrawing () {
      if (!this.airspaceDrawing) {
        // 开始绘制：清空旧多边形
        this.userAreaPoints = []
        this.viewer && this.viewer.entities.removeById('area-polygon')
        let i = 1; while (this.viewer && this.viewer.entities.getById(`area-point-${i}`)) { this.viewer.entities.removeById(`area-point-${i}`); i++ }
        this.drawAreaEnabled = true
        this.enableDrawArea()
      } else {
        // 结束绘制
        this.drawAreaEnabled = false
        this.disableDrawArea()
      }
      this.airspaceDrawing = !this.airspaceDrawing
    },

    /** 取消空域编辑：仅退出空域模式 */
    cancelAirspaceEdit () {
      this.exitAirspaceMode(false)
      ;(this.$message?.info || alert)('已取消空域编辑')
    },

    /** 截图作为封面 */
    captureCover () {
      try {
        const url = this.viewer?.scene?.canvas?.toDataURL('image/png')
        if (url) {
          this.airspaceForm.cover = url
          ;(this.$message?.success || alert)('已设置封面')
        }
      } catch (e) {
        console.warn('截图失败：', e)
        ;(this.$message?.error || alert)('截图失败，请检查浏览器权限')
      }
    },

    /** 保存空域到本地，并通知壳组件与列表页刷新 */
    saveAirspace () {
      if (!this.canSaveAirspace) {
        (this.$message?.warning || alert)('请先绘制空域多边形并填写名称/类型')
        return
      }
      const points = this.userAreaPoints.map(p => ({ lng: this.n(p.lng), lat: this.n(p.lat) }))
      const centerFeature = turf.centerOfMass({ type: 'Polygon', coordinates: [[...points.map(p => [p.lng, p.lat]), [points[0].lng, points[0].lat]]] })
      const center = centerFeature?.geometry?.coordinates || []
      const saved = {
        id: this.airspaceIdLocal,
        name: this.airspaceForm.name,
        type: this.airspaceForm.type,
        polygon: points,
        center: Array.isArray(center) ? { lng: center[0], lat: center[1] } : null,
        validFrom: this.airspaceForm.start || '',
        validTo: this.airspaceForm.end || '',
        note: this.airspaceForm.remark || '',
        cover: this.airspaceForm.cover || '',
        updatedAt: Date.now()
      }
      try {
        const dict = JSON.parse(localStorage.getItem('airspaces') || '{}')
        dict[saved.id] = saved
        localStorage.setItem('airspaces', JSON.stringify(dict))
      } catch (e) {
        console.error('保存空域失败：', e)
        ;(this.$message?.error || alert)('保存空域失败')
        return
      }

      /* ============================ FIX-2 ============================
       * 1) 广播给 Airspace.vue（它在 window 上监听 'airspace-updated'）
       * 2) 也通过组件事件通知父壳（若有监听）
       * ============================================================= */
      window.dispatchEvent(new CustomEvent('airspace-updated', { detail: saved }))   // 全局事件，列表页立即刷新
      this.$emit('action', { type: 'airspace-updated', data: saved })               // 组件事件，供壳组件联动

      ;(this.$message?.success || alert)('空域已保存')
      // 如需保存后返回列表：可改为 this.exitAirspaceMode(true) 或 this.$emit('action', { type:'back-to-menu' })
    },

    /* ================= 右侧卡片开合 ================= */
    toggleConfigCard () {
      this.isConfigCollapsed = !this.isConfigCollapsed
    }
  }
}
</script>

<style scoped>
/* 右侧配置卡片样式 */
.config-card {
  position: fixed; top: 20px; right: 20px;
  width: 400px; min-height: 600px; max-height: 90vh;
  padding: 20px; overflow-y: auto;
  background-color: #1e1e1e; color: #fff; border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3); z-index: 1000;
  transition: transform 0.3s ease;
}
.config-card.collapsed { transform: translateX(400px); }

/* 折叠按钮 */
.toggle-config-btn {
  position: absolute; top: 0; left: 0; width: 30px; height: 30px;
  background-color: #1e1e1e; color: #1e1e1e; border: none; border-radius: 4px 0 0 4px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  box-shadow: -2px 2px 4px rgba(0,0,0,.2); z-index: 1001;
}

/* 表单两列 */
.section { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.section-left, .section-right { width: 48%; }

/* 操作按钮组（任务） */
.btn-group { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; }
.btn-group button {
  background-color: #2c3e50; color: white; border: none; padding: 12px 18px;
  border-radius: 8px; font-weight: 600; font-size: 14px; cursor: pointer;
  box-shadow: 0 4px 6px rgba(0,0,0,.15);
}
.btn-group button:hover { background-color: #34495e; }
.btn-group button:active { background-color: #1f2d3d; }

/* 保存按钮 */
.save-settings-btn {
  background-color: #28a745; color: white; border: none; padding: 12px 18px;
  border-radius: 8px; font-weight: 600; font-size: 14px; cursor: pointer;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
}

/* 未选择类型提示 */
.no-buttons-message {
  background-color: rgba(255,0,0,.8); color: white; padding: 10px; border-radius: 8px; font-size: 14px; margin-top: 16px;
}

/* 返回菜单按钮 */
.return-menu-btn {
  position: absolute; bottom: 80px; left: 20px;
  background-color: #007bff; color: white; border: none; padding: 12px 18px;
  border-radius: 8px; font-weight: 600; font-size: 14px; cursor: pointer;
  box-shadow: 0 4px 6px rgba(0,0,0,.15); z-index: 1000;
}
.return-menu-btn:hover { background-color: #0056b3; }
.return-menu-btn:active { background-color: #004085; }

/* 迷你地图去掉默认控件 */
#mini-view .cesium-viewer-toolbar,
#mini-view .cesium-viewer-animationContainer,
#mini-view .cesium-viewer-timelineContainer,
#mini-view .cesium-viewer-fullscreenContainer,
#mini-view .cesium-viewer-bottom,
#mini-view .cesium-infoBox,
#mini-view .cesium-selection-wrapper {
  display: none !important;
}
#mini-view canvas { outline: none; }
</style>
