<!-- src/components/Device/DeviceAirport.vue -->
<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

/** ===== 数据源 ===== */
import baseDrones   from '@/test-data/droneDataTask.json'  // 无人机兜底
import stations     from '@/test-data/station.json'         // 收费站
import baseAirports from '@/test-data/airports.json'        // 机场(=Dock)兜底

/** ===== 本地存储 & 事件 ===== */
const STORAGE_DRONES   = 'droneList'    // 无人机页也在用
const STORAGE_AIRPORTS = 'airportList'  // 保持 key 不变，内部结构已更新为“Dock 列表”
const EVT_DRONES   = 'drones-updated'
const EVT_AIRPORTS = 'airports-updated'
const busEmit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }))

/** ===== 工具 ===== */
const labelStation = (name) => (name ? `${name}收费站` : '')

/** ===== 载入 & 持久化 ===== */
const allDrones = ref([])
const loadDrones = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_DRONES) || '[]')
    allDrones.value = (Array.isArray(saved) && saved.length) ? saved : baseDrones
  } catch { allDrones.value = baseDrones }
}

const airports = ref([]) // 每条即一台 Dock：{id, station, dockModel, dockSN, lng, lat, droneName}
const loadAirports = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_AIRPORTS) || '[]')
    airports.value = (Array.isArray(saved) && saved.length) ? saved : baseAirports
  } catch { airports.value = baseAirports }

  // 兜底：补齐经纬度
  const byStation = new Map(stations.map(s => [s.name, s]))
  airports.value.forEach(a => {
    const s = byStation.get(a.station)
    if (s && (a.lng == null || a.lat == null)) { a.lng = s.lng; a.lat = s.lat }
  })
}

const persistAirports = () => {
  localStorage.setItem(STORAGE_AIRPORTS, JSON.stringify(airports.value))
  busEmit(EVT_AIRPORTS, airports.value)
}
const persistDrones = () => {
  localStorage.setItem(STORAGE_DRONES, JSON.stringify(allDrones.value))
  busEmit(EVT_DRONES, allDrones.value)
}

/** ===== 自适应表高 ===== */
const winH = ref(window.innerHeight)
const onResize = () => (winH.value = window.innerHeight)
onMounted(() => {
  loadDrones()
  loadAirports()
  window.addEventListener('resize', onResize)
  window.addEventListener(EVT_DRONES, loadDrones) // 无人机页变动实时同步
})
onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener(EVT_DRONES, loadDrones)
})
const tableHeight = computed(() => Math.max(360, winH.value - 220))

/** ===== 过滤/搜索/分页 ===== */
const q = ref('')                         // 机场名/无人机/序列号 关键字
const stationFilter = ref('')
const modelFilter = ref('')

const stationOptions = stations.map(s => s.name)
const modelOptions = computed(() => {
  const set = new Set(airports.value.map(a => a.dockModel).filter(Boolean))
  // 常见型号兜底
  ;['DJI Dock 2 Mini', 'DJI Dock 2'].forEach(m => set.add(m))
  return Array.from(set)
})

const filtered = computed(() => {
  let arr = airports.value
  const kw = q.value.trim().toLowerCase()
  if (kw) {
    arr = arr.filter(a =>
      `${a.dockSN || ''}${a.dockModel || ''}${a.station || ''}${a.droneName || ''}`
        .toLowerCase().includes(kw)
    )
  }
  if (stationFilter.value) arr = arr.filter(a => a.station === stationFilter.value)
  if (modelFilter.value)   arr = arr.filter(a => a.dockModel === modelFilter.value)
  return arr
})

const page = ref(1)
const pageSize = ref(10)
const paged = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value)
)
const search = () => (page.value = 1)
const reset = () => { q.value=''; stationFilter.value=''; modelFilter.value=''; page.value=1 }

/** ===== 分配逻辑：每个机场(=Dock)仅可绑定一架无人机 ===== */
// 映射：无人机名 -> 机场 id
const assignedMap = computed(() => {
  const m = new Map()
  airports.value.forEach(a => { if (a.droneName) m.set(a.droneName, a.id) })
  return m
})

/** 当前行可选无人机（已绑定其它机场的禁用，除非就是本行） */
const droneOptionsFor = (row) => {
  const taken = assignedMap.value
  return allDrones.value.map(d => {
    const holder = taken.get(d.name)
    const disabled = holder && holder !== row.id
    const label = `${d.name}（${d.takeoff || '未放置'}）`
    return { label, value: d.name, disabled }
  })
}

/** 指派/清空无人机 */
const assignDrone = (row, newName) => {
  const prev = row.droneName || ''

  // 1) 解除上一台的占用
  if (prev && prev !== newName) {
    const oldD = allDrones.value.find(x => x.name === prev)
    if (oldD) oldD.takeoff = '' // 解绑 -> 清空位置
  }

  // 2) 新选择为空 => 仅清空与持久化
  if (!newName) {
    row.droneName = ''
    persistAirports(); persistDrones()
    return
  }

  // 3) 新选择：若在其它机场已占用 => 先从其它机场清掉
  airports.value.forEach(a => {
    if (a.id !== row.id && a.droneName === newName) a.droneName = ''
  })

  // 4) 更新本机场绑定 + 无人机位置（以机场站点为准）
  row.droneName = newName
  const d = allDrones.value.find(x => x.name === newName)
  if (d) d.takeoff = labelStation(row.station)

  persistAirports()
  persistDrones()
  ElMessage.success('已更新绑定关系')
}

/** 删除机场（Dock） */
const removeAirport = (row) => {
  ElMessageBox.confirm(`确定删除机场【${row.dockSN || row.id}】吗？`, '提示', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
  }).then(() => {
    // 清空绑定无人机的位置
    if (row.droneName) {
      const d = allDrones.value.find(x => x.name === row.droneName)
      if (d) d.takeoff = ''
    }
    airports.value = airports.value.filter(a => a !== row)
    persistAirports(); persistDrones()
    ElMessage.success('已删除')
  }).catch(() => {})
}

/** ===== 新增机场（Dock） ===== */
const addVisible = ref(false)
const form = reactive({
  station: '',          // 站点（纯名称）
  dockModel: 'DJI Dock 2 Mini',
  dockSN: '',
  droneName: ''
})
const openAdd = () => {
  form.station  = ''
  form.dockModel = 'DJI Dock 2 Mini'
  form.dockSN   = ''
  form.droneName = ''
  addVisible.value = true
  nextTick()
}
const nextId = () =>
  (airports.value.map(i => Number(i.id) || 0).sort((a, b) => b - a)[0] || 0) + 1

const addSubmit = () => {
  if (!form.station)   return ElMessage.warning('请选择站点')
  if (!form.dockSN)    return ElMessage.warning('请输入 Dock SN')

  // 若所选无人机已被其它机场占用，先清掉
  if (form.droneName) {
    airports.value.forEach(a => { if (a.droneName === form.droneName) a.droneName = '' })
  }

  const st = stations.find(s => s.name === form.station) || { lng:'', lat:'' }
  const record = {
    id: nextId(),
    station: form.station,
    dockModel: form.dockModel,
    dockSN: form.dockSN,
    lng: st.lng, lat: st.lat,
    droneName: form.droneName || ''
  }
  airports.value.unshift(record)

  // 更新无人机位置
  if (form.droneName) {
    const d = allDrones.value.find(x => x.name === form.droneName)
    if (d) d.takeoff = labelStation(form.station)
  }

  persistAirports(); persistDrones()
  addVisible.value = false
  ElMessage.success('新增机场成功')
}

/** ===== UI 辅助 ===== */
const statusDotStyle = { width:'8px', height:'8px', display:'inline-block', borderRadius:'50%', marginRight:'6px', background:'#409EFF' }
</script>

<template>
  <div class="wrap">
    <!-- 工具栏（和无人机页对齐） -->
    <div class="toolbar">
      <div class="left">
        <span class="label">关键词</span>
        <el-input v-model="q" placeholder="Dock SN / 型号 / 站点 / 无人机" style="width:260px" @keydown.enter="search" />

        <span class="label">站点</span>
        <el-select v-model="stationFilter" placeholder="全部站点" style="width:200px">
          <el-option label="全部" value="" />
          <el-option v-for="s in stationOptions" :key="s" :label="s + '收费站'" :value="s" />
        </el-select>

        <span class="label">Dock型号</span>
        <el-select v-model="modelFilter" placeholder="全部型号" style="width:180px">
          <el-option label="全部" value="" />
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>

        <el-button type="primary" @click="search">搜索</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <div class="right">
        <el-button type="primary" @click="openAdd">新增机场</el-button>
      </div>
    </div>

    <!-- 表格 -->
    <el-table :data="paged" border stripe :height="tableHeight" style="width:100%">
      <el-table-column prop="id" label="机场ID" width="90" />
      <el-table-column label="站点" width="170">
        <template #default="{ row }">{{ labelStation(row.station) }}</template>
      </el-table-column>
      <el-table-column prop="dockModel" label="Dock型号" width="160" />
      <el-table-column prop="dockSN" label="Dock SN" width="160" />
      <el-table-column label="经纬度" width="200">
        <template #default="{ row }">{{ row.lng }}, {{ row.lat }}</template>
      </el-table-column>

      <el-table-column label="当前无人机" width="160">
        <template #default="{ row }">
          <span v-if="row.droneName"><i :style="statusDotStyle"></i>{{ row.droneName }}</span>
          <span v-else style="color:#909399">-</span>
        </template>
      </el-table-column>

      <el-table-column label="指派无人机" width="320">
        <template #default="{ row }">
          <el-select
            v-model="row.droneName"
            clearable filterable placeholder="选择无人机"
            style="width:300px"
            @change="(v)=>assignDrone(row, v)"
          >
            <el-option
              v-for="opt in droneOptionsFor(row)"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
              :disabled="opt.disabled"
            />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="操作" width="120" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="danger" size="small" @click="removeAirport(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        :total="filtered.length"
        :page-size="pageSize"
        :current-page="page"
        :page-sizes="[5,10,20,50]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="(v)=>page=v"
        @size-change="(v)=>{pageSize=v; page=1}"
      />
    </div>

    <!-- 新增 Dock 弹窗 -->
    <el-dialog v-model="addVisible" title="新增机场（Dock）" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="站点">
          <el-select v-model="form.station" placeholder="请选择收费站" style="width:100%">
            <el-option v-for="s in stationOptions" :key="s" :label="s + '收费站'" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="Dock型号">
          <el-select v-model="form.dockModel" style="width:100%">
            <el-option label="DJI Dock 2 Mini" value="DJI Dock 2 Mini" />
            <el-option label="DJI Dock 2" value="DJI Dock 2" />
          </el-select>
        </el-form-item>
        <el-form-item label="Dock SN">
          <el-input v-model="form.dockSN" placeholder="如 DK-0001" />
        </el-form-item>
        <el-form-item label="绑定无人机">
          <el-select v-model="form.droneName" clearable filterable placeholder="可先不选" style="width:100%">
            <el-option
              v-for="d in allDrones"
              :key="d.name"
              :label="`${d.name}（${d.takeoff || '未放置'}）`"
              :value="d.name"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible=false">取消</el-button>
        <el-button type="primary" @click="addSubmit">新增</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wrap { padding: 25px 12px 12px; }
/* 第一個像素調上方空的間距 */
.toolbar {
  display:flex; align-items:center; justify-content:space-between;
  background:#fff; padding:8px 12px; margin-bottom:10px;
  border:1px solid #ebeef5; border-radius:4px;
}
.toolbar .label { margin:0 8px 0 16px; color:#606266; }
.left { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.right { display:flex; align-items:center; gap:8px; }

.pagination{
  padding:10px; background:#fff; border:1px solid #ebeef5; border-top:none;
  display:flex; justify-content:flex-end; border-radius:0 0 4px 4px;
}
:deep(.el-table .el-table__header-wrapper th){ height:34px; }
:deep(.el-table .cell){ line-height:28px; padding:8px; }
</style>
