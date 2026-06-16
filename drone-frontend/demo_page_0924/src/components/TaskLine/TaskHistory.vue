<template>
  <div class="history-wrap">
    <!-- 顶部筛选 -->
    <div class="toolbar">
      <div class="left">
        <el-select v-model="selectedRoute" clearable filterable placeholder="按航线筛选（可空）" style="width: 220px;">
          <el-option v-for="rid in allRoutes" :key="rid" :label="rid" :value="rid" />
        </el-select>

        <el-date-picker
          v-model="weekRange"
          type="daterange"
          unlink-panels
          range-separator="至"
          start-placeholder="起始日期"
          end-placeholder="结束日期"
          :shortcuts="dateShortcuts"
          value-format="YYYY-MM-DD"
          style="width: 360px;"
        />
        <el-button @click="resetFilters">重置</el-button>
      </div>
      <div class="right">
        <el-switch v-model="showGrid" active-text="网格" />
      </div>
    </div>

    <!-- 图1：每周完成总数 -->
    <el-card shadow="never" class="card">
      <div class="card-title">每周完成总数</div>
      <div ref="lineRef" class="chart"></div>
    </el-card>

    <!-- 图2：按周内工作日堆叠 -->
    <el-card shadow="never" class="card">
      <div class="card-title">周内分日完成分布</div>
      <div ref="barRef" class="chart"></div>
    </el-card>

    <!-- 空态 -->
    <div v-if="!hasData" class="empty">
      暂无历史数据（或筛选条件过严）
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { loadStore, addWeeklyListener } from '@/shared/routeWeekly'

/* ===================== 色卡与主题（增强区分度） ===================== */
const PALETTE = {
  cream:     '#EFDCCE', // 周一：浅米
  mistGrey:  '#CDBDC0', // 周二：灰粉
  lilac:     '#AEA5B8', // 周三：浅紫
  hazeBlue:  '#8B91B5', // 周四：灰蓝
  slateBlue: '#6378AF', // 周五：雾蓝（主色）
  deepLilac: '#888C91', // 周六：灰
  deepBlue:  '#4A4F4E'  // 周日：黑
}
const COLOR_SET = [
  PALETTE.cream,
  PALETTE.mistGrey,
  PALETTE.lilac,
  PALETTE.hazeBlue,
  PALETTE.slateBlue,
  PALETTE.deepLilac,
  PALETTE.deepBlue
]
const TEXT_COLOR = '#6B6A72'
const AXIS_COLOR = '#CFC7CF'
const CARD_BG    = '#FBF8F5'

/* ===================== 状态 ===================== */
const store = ref(loadStore())
const lineRef = ref(null)
const barRef  = ref(null)
let lineChart = null
let barChart  = null
let offWeekly = null

const selectedRoute = ref('')
const weekRange = ref(null)
const showGrid = ref(true)

/* ===================== 工具 ===================== */
const weekdayName = (d) => ({1:'周一',2:'周二',3:'周三',4:'周四',5:'周五',6:'周六',7:'周日'})[String(d)] || d
const ymdOf = (s) => (typeof s === 'string' && s.match(/^(\d{4}-\d{2}-\d{2})/)?.[1]) || null
function isoWeekday(dateStr){
  try { const d = new Date(dateStr + 'T00:00:00'); const wd = d.getDay(); return wd === 0 ? 7 : wd } catch { return null }
}

/* ===================== 数据汇总 ===================== */
const perWeekStats = computed(() => {
  const db = store.value || {}, weeks = db.weeks || {}, out = {}
  for (const wkKey of Object.keys(weeks)) {
    const subset = weeks[wkKey]?.subset || {}
    let total = 0
    const byWeekday = {1:0,2:0,3:0,4:0,5:0,6:0,7:0}
    for (const rid of Object.keys(subset)) {
      if (selectedRoute.value && rid !== selectedRoute.value) continue
      const arr = Array.isArray(subset[rid]) ? subset[rid] : []
      arr.forEach(t => {
        const ok = (t.status === '已完成' || t.status === '完成'); if (!ok) return
        const ymd = t.exec_at || ymdOf(t.executionTime)
        if (weekRange.value && Array.isArray(weekRange.value)) {
          const [start, end] = weekRange.value
          if (ymd && ((start && ymd < start) || (end && ymd > end))) return
        }
        total += 1
        const wd = ymd ? isoWeekday(ymd) : null
        if (wd) byWeekday[wd] = (byWeekday[wd] || 0) + 1
      })
    }
    out[wkKey] = { total, byWeekday }
  }
  return out
})

const weekKeysSorted = computed(() => Object.keys(perWeekStats.value || {}).sort((a,b)=>a.localeCompare(b,'en',{numeric:true})))
const hasData = computed(() => weekKeysSorted.value.some(k => (perWeekStats.value?.[k]?.total || 0) > 0))
const allRoutes = computed(() => {
  const set = new Set(); const weeks = (store.value||{}).weeks || {}
  Object.keys(weeks).forEach(wk => Object.keys(weeks[wk]?.subset || {}).forEach(r => set.add(r)))
  return Array.from(set).sort((a,b)=>a.localeCompare(b,'en',{numeric:true}))
})

const fmt = (d) => d.toISOString().slice(0,10)
const dateShortcuts = [
  { text: '最近7天',  value: () => { const end=new Date(), start=new Date(); start.setDate(end.getDate()-6);  return [fmt(start),fmt(end)] } },
  { text: '最近30天', value: () => { const end=new Date(), start=new Date(); start.setDate(end.getDate()-29); return [fmt(start),fmt(end)] } }
]

/* ===================== 图表（按色卡） ===================== */
function buildLineOption() {
  const x = weekKeysSorted.value
  const y = x.map(k => perWeekStats.value?.[k]?.total || 0)
  return {
    color: [PALETTE.slateBlue],
    tooltip: { trigger: 'axis' },
    grid: showGrid.value ? { left: 40, right: 20, top: 30, bottom: 40 } : { left: 10, right: 10, top: 10, bottom: 10 },
    xAxis: {
      type: 'category', data: x,
      axisLine: { lineStyle: { color: AXIS_COLOR }}, axisTick: { show: false },
      axisLabel: { color: TEXT_COLOR }
    },
    yAxis: {
      type: 'value', name: '完成数',
      nameTextStyle: { color: TEXT_COLOR },
      axisLine: { lineStyle: { color: AXIS_COLOR }},
      splitLine: { lineStyle: { color: AXIS_COLOR, opacity: 0.35 }},
      axisLabel: { color: TEXT_COLOR }
    },
    series: [{
      type: 'line', name: '每周完成', data: y, smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { width: 3 }, itemStyle: { borderColor: '#fff', borderWidth: 1 },
      areaStyle: {
        opacity: 0.18,
        color: new echarts.graphic.LinearGradient(0,0,0,1,[
          { offset: 0, color: PALETTE.slateBlue }, { offset: 1, color: 'rgba(99,120,175,0)' }
        ])
      }
    }]
  }
}

function buildBarOption() {
  const x = weekKeysSorted.value
  const stacks = {1:[],2:[],3:[],4:[],5:[],6:[],7:[]}
  x.forEach(k => { const m = perWeekStats.value?.[k]?.byWeekday || {}; for (let d=1; d<=7; d++) stacks[d].push(m[d] || 0) })

  // 更深一点的描边色
  const borderColorOf = (hex) => {
    try {
      const v = hex.replace('#','')
      const r = Math.max(0, parseInt(v.slice(0,2),16) - 28)
      const g = Math.max(0, parseInt(v.slice(2,4),16) - 28)
      const b = Math.max(0, parseInt(v.slice(4,6),16) - 28)
      return `rgb(${r},${g},${b})`
    } catch { return '#666' }
  }

  const gridBase = showGrid.value
    ? { left: 50, right: 20, top: 50, bottom: 72, containLabel: true }
    : { left: 10, right: 10, top: 10, bottom: 72, containLabel: true }

  return {
    color: COLOR_SET,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true },
    legend: {
      data: [1,2,3,4,5,6,7].map(weekdayName),
      type: 'scroll', orient: 'horizontal', bottom: 6, left: 'center',
      itemWidth: 14, itemHeight: 10, textStyle: { color: TEXT_COLOR }
    },
    grid: gridBase,
    xAxis: {
      type: 'category', data: x,
      axisLine: { lineStyle: { color: AXIS_COLOR }},
      axisTick: { show: false, alignWithLabel: true },
      axisLabel: { color: TEXT_COLOR }
    },
    yAxis: {
      type: 'value', name: '完成数',
      nameTextStyle: { color: TEXT_COLOR },
      axisLine: { lineStyle: { color: AXIS_COLOR }},
      splitLine: { lineStyle: { color: AXIS_COLOR, opacity: 0.35 }},
      axisLabel: { color: TEXT_COLOR }
    },
    // —— 关键：让柱子占满灰框（类目带宽）——
    barCategoryGap: '10%', // 类目间距 
    barGap: '0%',         // 堆叠稳定
    series: [1,2,3,4,5,6,7].map((d, i) => ({
      type: 'bar',
      name: weekdayName(d),
      stack: 'weekday',
      // 不设置 barWidth / barMaxWidth，自适应并用满带宽
      emphasis: { focus: 'series', itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.15)' } },
      itemStyle: { borderRadius: [4,4,0,0], borderWidth: 1, borderColor: borderColorOf(COLOR_SET[i]) },
      data: stacks[d]
    }))
  }
}

function renderCharts() {
  if (!lineRef.value || !barRef.value) return
  if (!lineChart) lineChart = echarts.init(lineRef.value)
  if (!barChart)  barChart  = echarts.init(barRef.value)
  lineChart.setOption(buildLineOption())
  barChart.setOption(buildBarOption())
}

function resetFilters() { selectedRoute.value = ''; weekRange.value = null }

/* ===================== 生命周期 & 监听 ===================== */
onMounted(async () => {
  await nextTick()
  renderCharts()
  window.addEventListener('resize', onResize)
  offWeekly = addWeeklyListener((snapshot) => {
    store.value = snapshot || loadStore()
    nextTick().then(renderCharts)
  })
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  offWeekly && offWeekly()
  if (lineChart) { lineChart.dispose(); lineChart = null }
  if (barChart)  { barChart.dispose();  barChart  = null }
})
function onResize(){ lineChart && lineChart.resize(); barChart && barChart.resize() }
watch([store, selectedRoute, weekRange, showGrid], () => nextTick().then(renderCharts))
</script>

<style scoped>
.history-wrap {
  display: flex; flex-direction: column; gap: 8px;
  padding-top: 10px; padding-left: 12px;
  background: #FBF8F5; /* 淡米色基调 */
}
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 4px; gap: 8px; flex-wrap: wrap;
}
.toolbar .left { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

/* 统一控件主色为雾蓝（局部覆盖） */
:deep(.el-button--primary),
:deep(.el-switch.is-checked .el-switch__core),
:deep(.el-select .el-input.is-focus .el-input__wrapper),
:deep(.el-date-editor .el-input.is-focus .el-input__wrapper) {
  --el-color-primary: #6378AF;
}

.card {
  border-radius: 12px;
  background: #FFFFFF;
  border: 1px solid #EADFDA; /* 接近 #EFDCCE */
}
.card-title { font-weight: 700; margin-bottom: 8px; color: #6B6A72; }
.chart { width: 100%; height: 280px; } /* 这里可调高度 */
.empty { text-align: center; padding: 24px; color: #8B91B5; }
</style>
