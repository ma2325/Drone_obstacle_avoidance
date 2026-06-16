<!-- src/components/TaskLine/RouteShell.vue -->
<template>
  <div class="shell menu-module-dark">
    <!-- 航线任务列表 -->
    <RoutePlan
      v-show="currentView === 'RoutePlan'"
      :preset-routes="[]"
      :all-tasks="[]"
      @action="handleAction"
    />

    <!-- MapView：保持挂载，用 v-show 切换，避免 keep-alive 子节点为空的问题 -->
    <MapView
      v-show="currentView === 'MapView'"
      :type="mapState.type"
      :task-id="mapState.taskId"
      :start-station="mapState.startStation"
      :preset3d-key="mapState.preset3dKey"
      :restore="mapState.restore"
      :lock="mapState.lock"
      :nav-nonce="mapState.navNonce"
      :open-payload="mapPayload"
      :payload-nonce="payloadNonce"
      @action="handleAction"
    />

    <!-- 空域管理页 -->
    <Airspace
      v-show="currentView === 'Airspace'"
      @action="handleAction"
    />

    <!-- 任务编排页 -->
    <AirportTask2
      v-show="currentView === 'AirportTask2'"
      :prefill-id="airportState.prefillId"
      :prefill-mode="airportState.prefillMode"
      @action="handleAction"
    />
  </div>
</template>

<script>
import RoutePlan from './RoutePlan.vue'
import MapView from './MapView.vue'
import AirportTask2 from './AirportTask2.vue'
import Airspace from './Airspace.vue'

/** 从 localStorage 读取空域字典（与 Airspace.vue 使用同一 KEY） */
const AIRSPACE_STORAGE_KEY = 'AIRSPACE_DICT'
function readAirspaceById (id) {
  try {
    const dict = JSON.parse(localStorage.getItem(AIRSPACE_STORAGE_KEY) || '{}')
    return dict?.[id] || null
  } catch { return null }
}

export default {
  name: 'RouteShell',
  components: { RoutePlan, MapView, AirportTask2, Airspace },

  data () {
    return {
      // RoutePlan | MapView | AirportTask2 | Airspace
      currentView: 'RoutePlan',

      // 传入 MapView 的空域负载（非空即触发 airspaceMode）
      mapPayload: null,
      payloadNonce: 0, // 与 MapView 协议：变更此值可强制其侦听到 payload 刷新

      // 传入 MapView 的基础 props
      mapState: {
        type: '航点飞行',
        taskId: '',
        startStation: '',
        preset3dKey: '',
        restore: true,
        lock: false,
        navNonce: 0
      },

      // AirportTask2 的预填
      airportState: { prefillId: '', prefillMode: '' },

      // 本组件内部的解除函数
      _unwatchRoute: null,
      _offRouteShellAction: null
    }
  },

  created () {
    // 首次根据路由同步视图
    this.syncFromRoute()
  },

  mounted () {
    // 兜底：全局监听来自 AirportTask2 等处的广播
    this._offRouteShellAction = (e) => {
      const evt = e?.detail
      if (!evt) return
      this.handleAction(evt)
    }
    window.addEventListener('route-shell-action', this._offRouteShellAction)

    // 🔁 关键：监听路由 query 改变（例如 /route?view=airspace）
    this._unwatchRoute = this.$watch(
      () => this.$route?.query,
      () => this.syncFromRoute(),
      { deep: true }
    )
  },

  // 被 keep-alive 重新显示时再同步一次，保证空域页可见时状态正确
  activated () {
    this.syncFromRoute()
  },

  beforeUnmount () {
    if (this._offRouteShellAction) {
      window.removeEventListener('route-shell-action', this._offRouteShellAction)
    }
    if (this._unwatchRoute) this._unwatchRoute()
  },

  methods: {
    /** === 根据当前路由同步视图（支持 view=plan|map|airspace|airport） === */
    syncFromRoute () {
      const q = this.$route?.query || {}
      const view = String(q.view || '').toLowerCase()

      if (view === 'map') {
        // 透传 query 到 openMap（保持与你原来一致）
        const isAirspace = (q.airspace === '1' || q.airspace === 'true')
        const payloadFromQuery = (() => {
          if (!isAirspace) return null
          const id = q.airspaceId || q.id
          if (!id) return null
          const obj = readAirspaceById(id)
          return obj
            ? { ...obj, type: 'open-map-from-airspace', airspaceId: obj.id, drawNew: false, restore: true }
            : null
        })()

        this.openMap({
          mapType: q.type || '',
          taskId: q.taskId || '',
          startStation: q.startStation || '',
          preset3dKey: q.preset3d || q.preset || '',
          restore: q.restore === '1' || q.restore === 'true',
          lock: q.lock === '1' || q.lock === 'true',
          source: isAirspace ? 'airspace' : undefined,
          __airspaceFromQuery__: payloadFromQuery
        })
      } else if (view === 'airspace') {
        // ✅ 切换到空域页
        this.currentView = 'Airspace'
        this.mapPayload = null
        // 可选：通知空域页刷新
        window.dispatchEvent(new CustomEvent('airspace-refresh'))
      } else if (view === 'airport') {
        this.currentView = 'AirportTask2'
      } else if (view === 'plan') {
        this.currentView = 'RoutePlan'
      }
      // 其它情况：保持当前
    },

    /* 全局 action 入口 */
    handleAction ({ type, data }) {
      switch (type) {
        /* ========== 进入地图 ========== */
        case 'open-map':
        case 'open-map-from-airport':
          this.openMap({ ...data })
          break

        case 'open-map-from-airspace':
          // 打标来源为空域，并把空域负载传递过去
          this.openMap({ ...data, mapType: '空域编辑', source: 'airspace' })
          break

        /* ========== 从地图返回 ========== */
        case 'back-to-menu':
          this.currentView = 'RoutePlan'
          this.mapPayload = null
          // 同步路由（可选）
          this.$router?.replace({ path: '/route', query: { view: 'plan' } }).catch(() => {})
          break

        case 'back-to-airspace':
          this.currentView = 'Airspace'
          this.mapPayload = null
          this.$router?.replace({ path: '/route', query: { view: 'airspace' } }).catch(() => {})
          window.dispatchEvent(new CustomEvent('airspace-refresh'))
          break

        /* ========== 页面切换 ========== */
        case 'open-airspace':
          this.currentView = 'Airspace'
          this.mapPayload = null
          this.$router?.replace({ path: '/route', query: { view: 'airspace' } }).catch(() => {})
          window.dispatchEvent(new CustomEvent('airspace-refresh'))
          break

        case 'open-airport-task': {
          const { id, mode } = data || {}
          this.airportState = { prefillId: id || '', prefillMode: mode || '' }
          this.currentView = 'AirportTask2'
          this.$router?.replace({ path: '/route', query: { view: 'airport' } }).catch(() => {})
          break
        }

        case 'open-route-plan':
          this.currentView = 'RoutePlan'
          this.$router?.replace({ path: '/route', query: { view: 'plan' } }).catch(() => {})
          break

        /* ========== MapView 内部上抛 ========== */
        case 'airspace-updated':
          // 保存后，如需返回空域列表，可在这里统一切换
          // this.currentView = 'Airspace'
          // this.$router?.replace({ path: '/route', query: { view: 'airspace' } }).catch(() => {})
          window.dispatchEvent(new CustomEvent('airspace-refresh'))
          break

        default:
          console.warn('[RouteShell] 未识别的 action:', type, data)
      }
    },

    /**
     * 统一的「进入地图」
     * - 普通任务：{ mapType, taskId, startStation, preset3dKey, restore, lock }
     * - 预设航线：{ preset3dKey, taskId?: 'preset:xxx' }
     * - 空域编辑：{ source:'airspace', airspaceId, name, airspaceType, polygon, drawNew, ... }
     */
    openMap (data = {}) {
      const {
        mapType, taskId = '', startStation = '', preset3dKey = '', restore, lock, source
      } = data

      const isPreset   = !!preset3dKey
      const cleanedId  = String(taskId || '').replace(/^preset:/, '')
      const aliasId    = isPreset ? `preset:${preset3dKey}` : cleanedId
      const finalType  = mapType || (isPreset ? '预设航线' : '航点飞行')

      // 同 key 的预设航线重复打开 → 仅重置相机
      const shouldBump =
        isPreset &&
        this.currentView === 'MapView' &&
        this.mapState.preset3dKey === preset3dKey

      // 传入 MapView 的基础 props
      this.mapState = {
        type: finalType,
        taskId: aliasId,
        startStation: startStation || '',
        preset3dKey: preset3dKey || '',
        restore: typeof restore === 'boolean' ? restore : !isPreset,
        lock:    typeof lock    === 'boolean' ? lock    :  isPreset,
        navNonce: shouldBump ? Date.now() : this.mapState.navNonce
      }

      // 处理空域 payload（关键修复）
      if (source === 'airspace') {
        this.payloadNonce++
        // 优先使用从 query 还原出来的空域对象；否则就用 data 里传来的（来自 Airspace.vue 的 emit）
        const payload = data.__airspaceFromQuery__ || data
        // 统一打上类型标识，便于 MapView watcher 识别
        this.mapPayload = { ...payload, type: 'open-map-from-airspace' }
      } else {
        this.mapPayload = null
      }

      this.$nextTick(() => {
        this.currentView = 'MapView'
        // 同步路由（便于深链/刷新留在地图）
        const query = {
          view: 'map',
          type: finalType || '',
          taskId: aliasId || '',
          startStation: startStation || '',
          preset3d: preset3dKey || '',
          restore: (typeof this.mapState.restore === 'boolean' && this.mapState.restore) ? '1' : '0',
          lock: (typeof this.mapState.lock === 'boolean' && this.mapState.lock) ? '1' : '0'
        }
        if (source === 'airspace') {
          query.airspace = '1'
          const pid = (data.__airspaceFromQuery__?.id) || data.airspaceId || data.id
          if (pid) query.airspaceId = pid
        }

        this.$router?.replace({ path: '/route', query }).catch(() => {})

        console.log('[RouteShell] switch to MapView with state =', this.mapState, 'payload =', this.mapPayload)

        // 让 Cesium 重新计算画布
        setTimeout(() => { window.dispatchEvent(new Event('resize')) }, 0)
      })
    }
  }
}
</script>

<style scoped>
.shell { width: 100%; height: 100%; }
</style>
