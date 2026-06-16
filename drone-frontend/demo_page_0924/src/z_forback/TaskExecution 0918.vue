<template>
  <div style="padding: 20px;">

    <!-- 顶部：只保留“选择周”，阈值与+1按钮已移除 -->
    <div style="margin-bottom: 14px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="f-label">选择周</span>
        <el-select v-model="weekKey" style="width: 160px" @change="onWeekChange">
          <el-option v-for="w in weekOptions" :key="w" :label="w" :value="w" />
        </el-select>
      </div>
    </div>

    <!-- 表格：按“组别”合并（每个 route 仅一行），不显示删除操作列 -->
    <el-table :data="tableData" row-key="groupId" stripe border :fit="true" style="width: 100%;">
      <el-table-column label="任务ID" prop="groupId" width="120" />
      <el-table-column label="航线Key" prop="preset3d" width="120" />
      <el-table-column label="航线编号" prop="route_id" width="120" />
      <el-table-column label="任务名称" prop="name" min-width="180" />
      <el-table-column label="任务类型" prop="taskType" width="120" />

      <el-table-column label="巡检类型" width="220">
        <template #default="{ row }">
          {{ Array.isArray(row.type) && row.type.length ? row.type.join('、') : '-' }}
        </template>
      </el-table-column>

      <el-table-column label="航线里程" prop="route" width="120">
        <template #default="{ row }">{{ row.route || '-' }}</template>
      </el-table-column>

      <el-table-column label="起飞点" prop="takeoff" width="120" />

      <el-table-column label="时间窗" width="160">
        <template #default="{ row }">
          {{ Array.isArray(row.time_window) && row.time_window.length ? row.time_window.join('-') : '-' }}
        </template>
      </el-table-column>

      <el-table-column label="飞行趟数" prop="flightCount" width="100">
        <template #default="{ row }">{{ row.flightCount ?? '-' }}</template>
      </el-table-column>

      <el-table-column label="执勤无人机" prop="drone" width="140">
        <template #default="{ row }">{{ row.drone || '-' }}</template>
      </el-table-column>

      <el-table-column label="优先级" prop="priority" width="100">
        <template #default="{ row }">{{ row.priority || '-' }}</template>
      </el-table-column>

      <el-table-column label="执行状态" prop="status" width="120">
        <template #default="{ row }">{{ row.status || '待执行' }}</template>
      </el-table-column>

      <el-table-column label="执行时间" prop="executionTime" width="160">
        <template #default="{ row }">{{ row.executionTime || '-' }}</template>
      </el-table-column>

      <el-table-column label="异常记录" prop="exceptionRecord" width="160">
        <template #default="{ row }">{{ row.exceptionRecord || '-' }}</template>
      </el-table-column>

      <el-table-column label="识别结果数量" prop="recognitionCount" width="140">
        <template #default="{ row }">{{ row.recognitionCount || '-' }}</template>
      </el-table-column>

      <el-table-column label="精度指标" prop="accuracyMetric" width="120">
        <template #default="{ row }">{{ row.accuracyMetric || '-' }}</template>
      </el-table-column>

      <el-table-column label="时间窗符合率" prop="timeWindowCompliance" width="140">
        <template #default="{ row }">{{ row.timeWindowCompliance || '-' }}</template>
      </el-table-column>

      <el-table-column label="完成率" prop="completionRate" width="120">
        <template #default="{ row }">{{ row.completionRate || '-' }}</template>
      </el-table-column>

      <el-table-column label="飞行日志（时长/趟数/里程）" prop="flightLog" width="220">
        <template #default="{ row }">{{ row.flightLog || '-' }}</template>
      </el-table-column>

      <el-table-column label="电池使用次数" prop="batteryUsageCount" width="140">
        <template #default="{ row }">{{ row.batteryUsageCount || '-' }}</template>
      </el-table-column>

      <el-table-column label="设备健康度" prop="deviceHealth" width="120">
        <template #default="{ row }">{{ row.deviceHealth || '-' }}</template>
      </el-table-column>

      <!-- ✅ 最后一列：本周执行次数（带上下箭头，可加减；最小不会低于“真实任务条数”） -->
      <el-table-column label="本周执行次数" width="180" fixed="right">
        <template #default="{ row }">
          <el-input-number
            :min="minCountByRoute[row.preset3d] ?? 0"
            :step="1"
            :max="9999"
            v-model="countsDraftObj[row.preset3d]"
            @change="onCountChange(row.preset3d, $event)"
            :disabled="(minCountByRoute[row.preset3d] ?? 0) >= (countsByRoute[row.preset3d] ?? 0)
                      && (countsDraftObj[row.preset3d] ?? 0) < (minCountByRoute[row.preset3d] ?? 0)"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import weeklySeed from '@/test-data/taskData_week.json'
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  loadStore,
  on as busOn,
  getWeekKey,
  listAirportSubset,
  importAirportJson,
  addTaskToWeek,
  removeTaskFromWeek,
  setAirportThreshold,
  listCountsByRoute
} from '@/shared/routeWeekly'

/* —— 常量 —— */
const DEFAULT_THRESHOLD = 2                 // 阈值：仅在代码中生效，不显示 UI
const SHADOW_KEY = 'weekly_count_shadows'   // 记录各周各 route 的影子任务 id，便于回收

/* —— route_* → 任务组ID（X-* / D-*）映射 —— */
const ROUTE_TO_TASK = Object.freeze({
  route_0:  'X-0', route_1:  'X-1',  route_2:  'X-2',  route_3:  'X-3',  route_4:  'X-4',
  route_5:  'X-5', route_6:  'X-6',  route_7:  'X-7',  route_8:  'X-8',  route_9:  'X-9',
  route_10: 'X-10',route_11: 'X-11', route_12: 'X-12', route_13: 'X-13', route_14: 'X-14',
  route_21: 'D-1',
})
const toTaskGroup = (routeKey) => ROUTE_TO_TASK[routeKey] || routeKey

/* —— 状态 —— */
const storeRef = ref(loadStore())
const weekKey = ref(getWeekKey())
const weekOptions = ref(generateRecentWeeks(8))

/* —— utils：影子 id 持久化 —— */
function loadShadowDict() {
  try { return JSON.parse(localStorage.getItem(SHADOW_KEY) || '{}') } catch { return {} }
}
function saveShadowDict(dict){ localStorage.setItem(SHADOW_KEY, JSON.stringify(dict || {})) }
function getShadowIds(week, routeKey) {
  const all = loadShadowDict()
  return all?.[week]?.[routeKey] ? [...all[week][routeKey]] : []
}
function pushShadowId(week, routeKey, id) {
  const all = loadShadowDict()
  if (!all[week]) all[week] = {}
  if (!Array.isArray(all[week][routeKey])) all[week][routeKey] = []
  all[week][routeKey].push(id); saveShadowDict(all)
}
function popShadowId(week, routeKey) {
  const all = loadShadowDict()
  if (!all?.[week]?.[routeKey]?.length) return null
  const id = all[week][routeKey].pop()
  saveShadowDict(all); return id
}

/* —— 合并为“组行”：代表行取最后一条非影子任务（若全为影子，则取最后一条） —— */
const tableData = computed(() => {
  const wk = storeRef.value?.weeks?.[weekKey.value] || {}
  const subset = wk.subset || {}
  const rows = []

  Object.keys(subset).forEach(routeKey => {
    const arr = Array.isArray(subset[routeKey]) ? subset[routeKey] : []
    if (!arr.length) return
    const nonShadow = arr.filter(t => !t?._countShadow)
    const last = nonShadow.length ? nonShadow[nonShadow.length - 1] : arr[arr.length - 1]
    const first = nonShadow.length ? nonShadow[0] : arr[0]

    // 巡检类型并集（忽略影子）
    const tset = new Set()
    nonShadow.forEach(t => Array.isArray(t.type) && t.type.forEach(x => x && tset.add(x)))
    const typeUnion = Array.from(tset)

    rows.push({
      groupId: toTaskGroup(routeKey),
      preset3d: routeKey,
      route_id: last?.route_id || first?.route_id || '',
      name: last?.name || first?.name || `${routeKey}-例检`,
      taskType: last?.taskType || (typeUnion.some(x => ['桥梁巡检','边坡巡检'].includes(x)) && !typeUnion.some(x => ['抛洒物识别','团雾检测','病害识别','拥堵点检测'].includes(x)) ? '点位扫描' : '线路扫描'),
      type: typeUnion,
      route: last?.route || first?.route || '-',
      takeoff: last?.takeoff || first?.takeoff || '-',
      time_window: Array.isArray(last?.time_window) && last.time_window.length ? last.time_window
                   : (Array.isArray(first?.time_window) ? first.time_window : []),
      flightCount: last?.flightCount ?? first?.flightCount ?? '-',
      drone: last?.drone || first?.drone || '-',
      priority: last?.priority || first?.priority || '-',
      status: last?.status || first?.status || '待执行',
      executionTime: last?.executionTime || first?.executionTime || '-',
      exceptionRecord: last?.exceptionRecord || first?.exceptionRecord || '-',
      recognitionCount: last?.recognitionCount || first?.recognitionCount || '-',
      accuracyMetric: last?.accuracyMetric || first?.accuracyMetric || '-',
      timeWindowCompliance: last?.timeWindowCompliance || first?.timeWindowCompliance || '-',
      completionRate: last?.completionRate || first?.completionRate || '-',
      flightLog: last?.flightLog || first?.flightLog || '-',
      batteryUsageCount: last?.batteryUsageCount || first?.batteryUsageCount || '-',
      deviceHealth: last?.deviceHealth || first?.deviceHealth || '-'
    })
  })

  // 排序：按 groupId 自然序
  rows.sort((a,b) => String(a.groupId).localeCompare(String(b.groupId), 'zh-Hans-CN', { numeric: true }))
  return rows
})

/* —— counts：route 级别（周库 counts 优先；否则回退为 subset[rk].length），并计算“真实最小值=非影子条数” —— */
const countsByRoute = computed(() => {
  const fromStore = (typeof listCountsByRoute === 'function' ? (listCountsByRoute(weekKey.value) || {}) : {})
  const subset = storeRef.value?.weeks?.[weekKey.value]?.subset || {}
  const out = { ...fromStore }
  for (const rk of Object.keys(subset)) {
    if (out[rk] == null) out[rk] = Array.isArray(subset[rk]) ? subset[rk].length : 0
  }
  return out
})
const minCountByRoute = computed(() => {
  const subset = storeRef.value?.weeks?.[weekKey.value]?.subset || {}
  const out = {}
  for (const rk of Object.keys(subset)) {
    const arr = Array.isArray(subset[rk]) ? subset[rk] : []
    out[rk] = arr.filter(t => !t?._countShadow).length
  }
  return out
})

/* —— counts 的“草稿态”（用于 v-model 双向绑定） —— */
const countsDraft = ref({})
watch([countsByRoute, weekKey], () => {
  countsDraft.value = { ...(countsByRoute.value || {}) }
}, { immediate: true })

const countsDraftObj = computed({
  get(){ return countsDraft.value },
  set(v){ countsDraft.value = v }
})

/* —— 改变次数：通过添加/删除“影子任务”来增减 —— */
function onCountChange(routeKey, newVal) {
  const wk = weekKey.value
  const now = Number(countsByRoute.value?.[routeKey] || 0)
  const realMin = Number(minCountByRoute.value?.[routeKey] || 0)
  const target = Math.max(realMin, Number(newVal) || 0)
  countsDraft.value[routeKey] = target

  const diff = target - now
  if (diff === 0) return

  if (diff > 0) {
    // 增加：添加 diff 个影子任务
    for (let i = 0; i < diff; i++) addShadowTask(routeKey)
  } else {
    // 减少：仅删除影子任务，不能低于真实条数；若本地索引无记录，兜底去 subset 中逆序查找影子项
    for (let i = 0; i < Math.abs(diff); i++) {
      let id = popShadowId(wk, routeKey)
      if (!id) {
        const subset = storeRef.value?.weeks?.[wk]?.subset || {}
        const arr = Array.isArray(subset[routeKey]) ? subset[routeKey] : []
        for (let j = arr.length - 1; j >= 0; j--) {
          const t = arr[j]
          if (t && t._countShadow) { id = t.id; break }
        }
      }
      if (!id) break
      removeTaskFromWeek(id, routeKey, wk)
    }
  }
}

/* —— 影子任务：只用于计数，不参与显示（代表行已忽略影子）；克隆代表行关键字段更稳 —— */
function addShadowTask(routeKey) {
  const wk = weekKey.value
  const id = `shadow_${Date.now()}_${Math.random().toString(36).slice(2,8)}`
  const subset = storeRef.value?.weeks?.[wk]?.subset || {}
  const arr = Array.isArray(subset[routeKey]) ? subset[routeKey] : []
  const nonShadow = arr.filter(t => !t?._countShadow)
  const refRow = nonShadow.length ? nonShadow[nonShadow.length - 1] : arr[arr.length - 1] || {}

  const shadow = {
    id,
    preset3d: routeKey,
    preset3dKey: routeKey,
    groupId: toTaskGroup(routeKey),
    name: refRow?.name || `${routeKey}-计数占位`,
    taskType: refRow?.taskType || '线路扫描',
    type: Array.isArray(refRow?.type) ? [...refRow.type] : [],
    _countShadow: true,  // ★ 标记影子
    route_id: refRow?.route_id || '',
    takeoff: refRow?.takeoff || '',
    time_window: Array.isArray(refRow?.time_window) ? [...refRow.time_window] : [],
    flightCount: Number.isFinite(refRow?.flightCount) ? refRow.flightCount : 0,
    executionTime: '',
    drone: '',
    status: '待执行'
  }
  addTaskToWeek(shadow, wk)
  pushShadowId(wk, routeKey, id)
}

/* —— 订阅广播 / 初始化：默认阈值只在代码里写入（不显示 UI） —— */
let offWeekly
onMounted(() => {
  // 阈值写入（AirportTask2 会据此筛选“≤阈值”的航线进入日任务）
  setAirportThreshold(DEFAULT_THRESHOLD)

  // 仅补缺：把本周周库里没有的 seed 条目补进来（按 route#id 判重）
  const wk = getWeekKey()
  try {
    const existing = new Set((listAirportSubset(wk) || []).map(x => `${x.preset3d}#${x.id}`))
    const toAdd = (Array.isArray(weeklySeed) ? weeklySeed : [])
      .filter(x => x && x.id != null && x.preset3d)
      .filter(x => !existing.has(`${x.preset3d}#${x.id}`))
    if (toAdd.length) importAirportJson(toAdd, { weekKey: wk, mode: 'merge' })
  } catch {
    importAirportJson(Array.isArray(weeklySeed) ? weeklySeed : [], { weekKey: wk, mode: 'merge' })
  }

  offWeekly = busOn('weekly-updated', (snap) => { if (snap) storeRef.value = snap })
})
onUnmounted(() => { offWeekly && offWeekly() })

/* —— 事件 & 小工具 —— */
function onWeekChange(){
  nextTick(() => { countsDraft.value = { ...(countsByRoute.value || {}) } })
  // 切周时也同步阈值，避免跨周 config 差异
  setAirportThreshold(DEFAULT_THRESHOLD)
}
function generateRecentWeeks(n = 8) {
  const list = []
  const base = new Date()
  for (let i = 0; i < n; i++) {
    const d = new Date(base); d.setDate(d.getDate() - i * 7)
    list.push(getWeekKey(d))
  }
  return list
}
</script>

<style scoped>
.f-label { font-weight: 600; width: auto; color: #303133; }
::v-deep(.el-table .el-table__row) { height: auto; }
::v-deep(.el-table .el-table__header-wrapper th) { height: 30px; line-height: 50px; }
::v-deep(.el-table .cell) { line-height: 24px; }
</style>
