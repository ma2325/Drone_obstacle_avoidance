<template>
  <div style="padding: 20px;">
    <!-- 顶部：只保留“选择周” -->
    <div style="margin-bottom: 14px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="f-label">选择周</span>
        <el-select v-model="weekKey" style="width: 160px" @change="onWeekChange">
          <el-option v-for="w in weekOptions" :key="w" :label="w" :value="w" />
        </el-select>
      </div>
    </div>

    <!-- 固定表头：设置 max-height 即可（宽高不变） -->
    <el-table
      :data="tableDataEnhanced"
      row-key="groupId"
      stripe
      border
      :fit="true"
      :max-height="640"
      style="width: 100%;"
      empty-text="暂无数据"
    >
      <!-- ========= 板块1：基本信息========= -->
      <el-table-column align="center">
        <template #header><div class="sec-head">基本信息</div></template>

        <el-table-column class-name="sec-cell" label="任务ID"   prop="groupId" width="70" />
        <el-table-column class-name="sec-cell" label="航线Key"  prop="preset3d" width="90" />
        <el-table-column class-name="sec-cell" label="任务名称"  prop="name" min-width="150" />
        <el-table-column class-name="sec-cell" label="任务类型"  prop="taskType" width="110" />

        <!-- 巡检类型：彩色圆点 + 文字 -->
        <el-table-column class-name="sec-cell" label="巡检类型" min-width="180">
          <template #default="{ row }">
            <div class="type-wrap">
              <span
                v-for="(t, idx) in (row.type || [])"
                :key="idx"
                class="type-item"
              >
                <i class="dot" :style="{ '--dot': typeDotColor(t) }"></i>
                <span class="type-text">{{ t }}</span>
              </span>
              <span v-if="!row.type || !row.type.length">-</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column class-name="sec-cell" label="航线里程"  prop="route" width="110">
          <template #default="{ row }">{{ row.route || '-' }}</template>
        </el-table-column>
      </el-table-column>

      <!-- ========= 板块2：执行要求 ========= -->
      <el-table-column align="center">
        <template #header><div class="sec-head">执行要求</div></template>

        <el-table-column class-name="sec-cell" label="本周执行频次要求" width="90">
          <template #default="{ row }">{{ row.require_min_weekly ?? '-' }}</template>
        </el-table-column>

        <el-table-column class-name="sec-cell" label="分日要求" min-width="90">
          <template #default="{ row }">
            <div v-if="row.require_by_weekday && Object.keys(row.require_by_weekday).length">
              <el-tag v-for="(n, d) in row.require_by_weekday" :key="d" class="mr6">
                {{ weekdayName(d) }} ≥ {{ n }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ========= 板块3：当前完成情况========= -->
      <el-table-column align="center">
        <template #header><div class="sec-head">当前完成情况</div></template>

        <el-table-column class-name="sec-cell" label="本周已执行" width="105">
          <template #default="{ row }">{{ row.doneWeekly }}</template>
        </el-table-column>

        <!-- 分日完成：周X = 实际；满足=绿框，不满足=红框 -->
        <el-table-column class-name="sec-cell" label="分日完成" min-width="90">
          <template #default="{ row }">
            <div v-if="mergeDayKeys(row.require_by_weekday, row.doneByDay).length">
              <el-tag
                v-for="d in mergeDayKeys(row.require_by_weekday, row.doneByDay)"
                :key="d"
                :class="['mr6', getDayTagClass(row, d)]"
              >
                {{ weekdayName(d) }} = {{ (row.doneByDay && row.doneByDay[d]) || 0 }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <!-- 剩余执行次数：只显示 > 0，红色，不加粗 -->
        <el-table-column class-name="sec-cell" label="剩余执行次数" width="110">
          <template #default="{ row }">
            <span v-if="row.remainWeekly > 0" class="remain-red">{{ row.remainWeekly }}</span>
          </template>
        </el-table-column>

        <!-- 执行状态：进度条 + 悬浮提示 x/n -->
        <el-table-column class-name="sec-cell" label="执行状态" width="150">
          <template #default="{ row }">
            <el-tooltip :content="statusTooltip(row)" placement="top">
              <el-progress
                :percentage="statusPercent(row)"
                :stroke-width="12"
                :color="progressColor(row)"
                :show-text="false"
              />
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 执行时间：展示 JSON 中所有时间（exec_at / executionTime，多条） -->
        <el-table-column class-name="sec-cell" label="执行时间" width="150">
          <template #default="{ row }">
            <div v-if="row.execTimes && row.execTimes.length">
              <el-tag v-for="(t, i) in row.execTimes" :key="i" type="info" effect="plain" class="mr6 mb4">
                {{ t }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import weeklySeed from '@/test-data/taskData_week.json'
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  loadStore, on as busOn,
  getWeekKey,
  importWeeklySnapshot, importWeeklySnapshotAll,
  setAirportThreshold
} from '@/shared/routeWeekly'

const DEFAULT_THRESHOLD = 2
const AIRPORT_PUSH_PREFIX = 'airport_push_'

const ROUTE_TO_TASK = Object.freeze({
  route_0:'X-0', route_1:'X-1', route_2:'X-2', route_3:'X-3', route_4:'X-4',
  route_5:'X-5', route_6:'X-6', route_7:'X-7', route_8:'X-8', route_9:'X-9',
  route_10:'X-10', route_11:'X-11', route_12:'X-12', route_13:'X-13', route_14:'X-14',
  route_21:'D-1',
})
const toTaskGroup = (rk) => ROUTE_TO_TASK[rk] || rk

const storeRef = ref(loadStore())
const weekKey  = ref(getWeekKey())
const weekOptions = ref(generateRecentWeeks(8))

/* ---------- utils: weekday & date ---------- */
const weekdayName = (d) => {
  const map = {1:'周一',2:'周二',3:'周三',4:'周四',5:'周五',6:'周六',7:'周日'}
  const k = String(d)
  return map[k] || `周${k}`
}
function ymdOf(str){
  if (!str || typeof str !== 'string') return null
  const m = str.match(/^(\d{4}-\d{2}-\d{2})/)
  return m ? m[1] : null
}
function isoWeekday(dateStr){
  try {
    const d = new Date(dateStr + 'T00:00:00')
    let wd = d.getDay()
    return wd === 0 ? 7 : wd
  } catch { return null }
}

/* 合并“有要求/有完成”的日键 → 升序 1..7 */
const mergeDayKeys = (need = {}, done = {}) => {
  const s = new Set([...Object.keys(need || {}), ...Object.keys(done || {})])
  return Array.from(s).sort((a,b) => Number(a) - Number(b))
}

/* 分日标签：满足=绿，不满足=红（无要求视为满足） */
function getDayTagClass(row, d){
  const need = (row.require_by_weekday && row.require_by_weekday[d]) || 0
  const actual = (row.doneByDay && row.doneByDay[d]) || 0
  return actual >= need ? 'tag-ok' : 'tag-bad'
}

/* —— 巡检类型：每种类型一种颜色 —— */
const TYPE_DOT_COLORS = {
  '桥梁巡检':   '#EFDCCE',
  '边坡巡检':   '#888C91',
  '抛洒物识别': '#CDBDC0',
  '团雾检测':   '#AEA5B8',
  '拥堵点检测': '#6378AF',
  '病害识别':   '#8B91B5'
}
function typeDotColor(name){
  if (TYPE_DOT_COLORS[name]) return TYPE_DOT_COLORS[name]
  if (/桥|边坡/.test(name || '')) return '#BFB0D9'
  if (/雾|拥堵|抛洒|病害|识别|检测/.test(name || '')) return '#A9C6DF'
  return '#C0CBD9'
}

/* ============== 新增：分日要求键名规范化 ============== */
function normalizeWeekdayKey(k){
  if (k == null) return null
  const s = String(k).trim()
  if (/^\d+$/.test(s)) {
    let n = +s
    if (n === 0) n = 7
    if (n >= 1 && n <= 7) return String(n)
  }
  const dict = {
    '周一':1,'周二':2,'周三':3,'周四':4,'周五':5,'周六':6,'周日':7,'周天':7,
    'mon':1,'monday':1,'tue':2,'tues':2,'tuesday':2,'wed':3,'weds':3,'wednesday':3,
    'thu':4,'thur':4,'thurs':4,'thursday':4,'fri':5,'friday':5,
    'sat':6,'saturday':6,'sun':7,'sunday':7
  }
  const key = s.toLowerCase()
  return dict[key] ? String(dict[key]) : null
}

/* ---------- 基础 tableData（代表行） ---------- */
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
      drone: last?.drone || first?.drone || '-',
      priority: last?.priority || first?.priority || '-',
      status: last?.status || first?.status || '待执行',
      executionTime: last?.executionTime || first?.executionTime || '',
      exec_at: last?.exec_at || first?.exec_at || ''
    })
  })
  rows.sort((a,b) => String(a.groupId).localeCompare(String(b.groupId), 'zh-Hans-CN', { numeric: true }))
  return rows
})

/* ---------- 规则读取（带分日键名规范化） ---------- */
const rulesByRoute = computed(() => {
  const wk = storeRef.value?.weeks?.[weekKey.value] || {}
  const rules = wk.rules || {}
  const norm = {}
  for (const rk of Object.keys(rules)) {
    const r = rules[rk] || {}
    const minW = Number.isFinite(r.require_min_weekly) ? Number(r.require_min_weekly) : null
    const byDay = {}
    if (r.require_by_weekday && typeof r.require_by_weekday === 'object') {
      for (const rawKey of Object.keys(r.require_by_weekday)) {
        const k = normalizeWeekdayKey(rawKey)
        const n = Number(r.require_by_weekday[rawKey])
        if (k && Number.isFinite(n) && n > 0) byDay[k] = n
      }
    }
    norm[rk] = { require_min_weekly: minW, require_by_weekday: byDay }
  }
  return norm
})

/* ---------- 实际完成统计（含日统计） ---------- */
const execStatsByRoute = computed(() => {
  const wk = storeRef.value?.weeks?.[weekKey.value] || {}
  const subset = wk.subset || {}
  const stats = {}
  for (const rk of Object.keys(subset)) {
    const arr = (subset[rk] || []).filter(t => !t?._countShadow)
    let doneWeekly = 0
    const doneByDay = {}

    arr.forEach(t => {
      const ok = (t.status === '已完成' || t.status === '完成')
      if (!ok) return
      doneWeekly += 1
      const ymd = t.exec_at || ymdOf(t.executionTime)
      if (ymd) {
        const wd = isoWeekday(ymd)
        if (wd) doneByDay[wd] = (doneByDay[wd] || 0) + 1
      }
    })

    stats[rk] = { doneWeekly, doneByDay }
  }
  return stats
})

/* ---------- 执行时间列表（原样采集 JSON，可多条） ---------- */
const execTimesByRoute = computed(() => {
  const wk = storeRef.value?.weeks?.[weekKey.value] || {}
  const subset = wk.subset || {}
  const out = {}
  for (const rk of Object.keys(subset)) {
    const arr = (subset[rk] || []).filter(t => !t?._countShadow)
    const list = []
    arr.forEach(t => {
      if (t && typeof t.exec_at === 'string' && t.exec_at.trim()) list.push(String(t.exec_at).trim())
      if (t && typeof t.executionTime === 'string' && t.executionTime.trim()) list.push(String(t.executionTime).trim())
    })
    out[rk] = list
  }
  return out
})

/* ---------- 推送清单（保持原逻辑） ---------- */
const pushList = computed(() => {
  const out = []
  for (const row of tableData.value) {
    const rk = row.preset3d
    const rules = rulesByRoute.value?.[rk] || {}
    const { doneWeekly, doneByDay } = execStatsByRoute.value?.[rk] || { doneWeekly: 0, doneByDay: {} }

    const reqMin = Number.isFinite(rules.require_min_weekly) ? rules.require_min_weekly : 0
    const remainWeekly = Math.max((reqMin || 0) - (doneWeekly || 0), 0)

    const needByDay = rules.require_by_weekday || {}
    const remainByDay = {}
    for (const d of Object.keys(needByDay)) {
      const need = needByDay[d] || 0
      const done = doneByDay?.[d] || 0
      if (need > done) remainByDay[d] = need - done
    }

    if (remainWeekly > 0 || Object.keys(remainByDay).length) {
      out.push({ routeKey: rk, groupId: row.groupId, needWeekly: reqMin, doneWeekly, remainWeekly, needByDay, doneByDay, remainByDay })
    }
  }
  return out
})
function broadcastAirportPush(wk, list){
  try { window.dispatchEvent(new CustomEvent('airport-push-update', { detail: { weekKey: wk, list } })) } catch {}
}
watch([pushList, weekKey], () => {
  const wk = weekKey.value
  try { localStorage.setItem(`${AIRPORT_PUSH_PREFIX}${wk}`, JSON.stringify(pushList.value || [])) } catch {}
  broadcastAirportPush(wk, pushList.value || [])
}, { immediate: true })

/* ----------合并规则与完成度---------- */
const tableDataEnhanced = computed(() => {
  return (tableData.value || []).map(row => {
    const rk = row.preset3d
    const rules = rulesByRoute.value?.[rk] || {}
    const exec  = execStatsByRoute.value?.[rk] || { doneWeekly: 0, doneByDay: {} }
    const reqMin   = Number.isFinite(rules.require_min_weekly) ? rules.require_min_weekly : null
    const needByDay = rules.require_by_weekday || {}
    const remainWeekly = Math.max((reqMin || 0) - (exec.doneWeekly || 0), 0)
    const times = execTimesByRoute.value?.[rk] || []

    return {
      ...row,
      require_min_weekly: reqMin,
      require_by_weekday: needByDay,
      doneWeekly: exec.doneWeekly,
      doneByDay: exec.doneByDay,
      remainWeekly,
      execTimes: times
    }
  })
})

/* ---------- 进度条百分比 & 颜色 ---------- */
function statusPercent(row){
  const need = Number.isFinite(row.require_min_weekly) ? row.require_min_weekly : 0
  const done = Number.isFinite(row.doneWeekly) ? row.doneWeekly : 0
  if (!need) return 0
  return Math.min(100, Math.round((done / need) * 100))
}
function statusTooltip(row){
  const need = Number.isFinite(row.require_min_weekly) ? row.require_min_weekly : 0
  const done = Number.isFinite(row.doneWeekly) ? row.doneWeekly : 0
  return need > 0 ? `${done}/${need}` : '无周频次要求'
}
function progressColor(row){
  const pct = statusPercent(row)
  return pct >= 100 ? '#67C23A' : '#E6A23C'
}

/* ---------- 生命周期 ---------- */
let offWeekly
onMounted(async () => {
  setAirportThreshold(DEFAULT_THRESHOLD)
  importWeeklySnapshotAll(weeklySeed, { mode: 'merge' })
  offWeekly = busOn('weekly-updated', (snap) => { if (snap) storeRef.value = snap })
})
onUnmounted(() => { offWeekly && offWeekly() })

function onWeekChange(){
  nextTick(() => {})
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

:deep(.el-table .el-table__row) { height: auto; }
:deep(.el-table .el-table__header-wrapper th) { height: 30px; line-height: 50px; }
:deep(.el-table .cell) { line-height: 24px; }

/* —— 表头标题 —— */
.sec-head {
  /* background: var(--sec-head-bg) */
  border-bottom: 1px solid rgba(0,0,0,.04);
  font-weight: 700;
  padding: 8px 0;
  user-select: none;
}

/* 固定表头时的衔接*/
:deep(.el-table__header-wrapper) { z-index: 2; position: sticky; top: 0; }

.mr6 { margin-right: 6px; }
.mb4 { margin-bottom: 4px; }

/* —— 巡检类型：彩色圆点 + 文字 —— */
.type-wrap{ display:flex; flex-wrap:wrap; gap:8px 12px; }
.type-item{ display:inline-flex; align-items:center; gap:8px; }
.dot{
  width:10px; height:10px; border-radius:50%;
  background: var(--dot);
  box-shadow: 0 0 0 1px rgba(0,0,0,.06) inset, 0 1px 0 rgba(255,255,255,.6);
}
.type-text{ font-weight: 500; }

/* —— 分日完成标签（保留） —— */
:deep(.tag-ok.el-tag){
  background: #eef9f0;
  border-color: #67C23A;
  color: #67C23A;
}
:deep(.tag-bad.el-tag){
  background: #fdeeee;
  border-color: #F56C6C;
  color: #F56C6C;
}

/* —— 剩余执行次数（仅非零显示，保留） —— */
.remain-red { color: #F56C6C; font-weight: 400; }
</style>
