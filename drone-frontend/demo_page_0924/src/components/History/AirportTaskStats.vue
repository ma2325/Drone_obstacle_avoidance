<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import tasks from '../../test-data/airportTasks.json'


// ------- 选择器（左：周；右：日） -------
const weekAnchor = ref(new Date('2025-04-07')) // 初始一周（周一）
const dayAnchor  = ref(new Date('2025-04-13'))

// ------- 图表实例 -------
let lineChart, barChart
const lineRef = ref(null)
const barRef  = ref(null)

// ------- 工具 -------
const fmtDate = (d) => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
const parseDate = (s) => {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}
const getWeekRange = (anchor) => {
  // 以周一为一周的起点
  const d = new Date(anchor)
  const day = d.getDay() || 7 // 周日=0 -> 7
  const monday = new Date(d)
  monday.setDate(d.getDate() - (day - 1))
  const days = Array.from({ length: 7 }).map((_, i) => {
    const x = new Date(monday)
    x.setDate(monday.getDate() + i)
    return x
  })
  return { monday, days }
}

// ------- 数据聚合 -------
// 折线：同一周内，按“机巢/天”聚合（pictures+videos）
const buildLineSeries = () => {
  const { days } = getWeekRange(weekAnchor.value)
  const dayStrs = days.map(fmtDate)
  const taskTypes = Array.from(new Set(tasks.map(t => t.taskType)))

  const series = taskTypes.map(name => {
    const arr = dayStrs.map(ds => {
      const rows = tasks.filter(t => t.taskType === name && t.date === ds)
      const sum = rows.reduce((s, r) => s + (r.pictures + r.videos), 0)
      return sum
    })
    return { name, type: 'line', smooth: true, symbol: 'circle', data: arr }
  })
  const xAxis = ['周一','周二','周三','周四','周五','周六','周日']
  return { xAxis, series, legend: taskTypes }
}

// 柱状：选中“某一天”，按机巢汇总 pictures、videos
const buildBarSeries = () => {
  const day = fmtDate(dayAnchor.value)
  const rows = tasks.filter(t => t.date === day)
  const x = rows.map(r => r.taskType)
  const pic = rows.map(r => r.pictures)
  const vid = rows.map(r => r.videos)
  return { x, pic, vid }
}

// ------- 渲染 -------
const renderLine = () => {
  const { xAxis, series, legend } = buildLineSeries()
  lineChart?.dispose()
  lineChart = echarts.init(lineRef.value)
  lineChart.setOption({
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    tooltip: { trigger: 'axis' },
    legend: { data: legend, top: 0 },
    xAxis: { type: 'category', data: xAxis },
    yAxis: { type: 'value' },
    series
  })
}

const renderBar = () => {
  const { x, pic, vid } = buildBarSeries()
  barChart?.dispose()
  barChart = echarts.init(barRef.value)
  barChart.setOption({
    grid: { left: 40, right: 20, top: 40, bottom: 40 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['图片','视频'], top: 0 },
    xAxis: { type: 'category', data: x },
    yAxis: { type: 'value' },
    series: [
      { name: '图片', type: 'bar', data: pic },
      { name: '视频', type: 'bar', data: vid }
    ]
  })
}

const renderAll = async () => {
  await nextTick()
  renderLine()
  renderBar()
}

const handleResize = () => {
  lineChart?.resize()
  barChart?.resize()
}

onMounted(() => {
  renderAll()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  lineChart?.dispose()
  barChart?.dispose()
})

watch(weekAnchor, renderLine)
watch(dayAnchor, renderBar)
</script>

<template>
  <div class="wrap">
    <div class="toolbar">
      <div class="left">
        <span class="label">选择周</span>
        <el-date-picker
          v-model="weekAnchor"
          type="week"
          format="第 ww 周"
          placeholder="选择周"
          style="width: 140px;"
        />
      </div>
      <div class="right">
        <span class="label">选择日期</span>
        <el-date-picker
          v-model="dayAnchor"
          type="date"
          placeholder="选择日期"
          style="width: 140px;"
        />
      </div>
    </div>

    <div class="charts">
      <div class="chart">
        <div ref="lineRef" class="chart-canvas"></div>
        <div class="title">任务类型统计</div>
      </div>
      <div class="chart">
        <div ref="barRef" class="chart-canvas"></div>
        <div class="title">任务数据统计</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap { padding: 12px 16px; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.toolbar .label { margin-right: 8px; color:#666; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 80px;   /* 調上下間距 */}
.chart { background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 2px 6px rgba(0,0,0,.06); }
.chart-canvas { width: 100%; height: 360px; }
.title { text-align: center; margin-top: 6px; color:#333; font-weight: 600; }
@media (max-width: 1200px) {
  .charts { grid-template-columns: 1fr; }
}
</style>
