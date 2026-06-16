<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import droneRaw from '../../test-data/droneDataTask.json'
import stations from '../../test-data/station.json'

// —— 共享存储 & 事件 —— //
const STORAGE_DRONES = 'droneList'
const EVT_DRONES = 'drones-updated'

/** —— 高度自适应 —— */
const winH = ref(window.innerHeight)
const onResize = () => (winH.value = window.innerHeight)
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
const tableHeight = computed(() => Math.max(360, winH.value - 240))

/** —— 收费站选项 —— */
const stationOptions = stations.map(s => ({
  label: `${s.name}收费站`,   // 展示名
  value: s.name,              // 仅存“纯站名”
  lng: s.lng,
  lat: s.lat
}))
const takeoffOptions = computed(() => stationOptions.map(s => s.label))

/** —— 原始数据 → 规范字段 —— */
const withStationSuffix = (v='') => (v ? (/收费站$/.test(v) ? v : `${v}收费站`) : '')
const normalize = (d, i) => ({
  id: d.id ?? i + 1,
  name: d.name || `无人机${i + 1}`,
  deviceSN: d.deviceSN || d.sn || d.snCode || `SN-${String(i + 1).padStart(4, '0')}`,
  dockModel: d.dockModel || d.dock || 'DJI Dock 2 Mini',
  deviceModel: d.deviceModel || (d.model && /Matrice|M350|350/i.test(d.model) ? 'M350 RTK' : 'Mavic 3'),
  takeoff: withStationSuffix(d.takeoff || ''), // 统一加“收费站”
  status: d.status || '空闲中',
  battery: d.battery ?? 100,
  enduranceMileage: d.enduranceMileage ?? 25,
  model: d.model || (d.deviceModel && /350|Matrice/i.test(d.deviceModel) ? 'DJI Matrice 350 RTK' : 'DJI Mavic 3')
})
const list = ref(droneRaw.map(normalize))

// 读写 localStorage（页面互通）
const loadDrones = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_DRONES) || '[]')
    if (Array.isArray(saved) && saved.length) {
      list.value = saved
    } else {
      persistDrones()
    }
  } catch { persistDrones() }
}
const persistDrones = () => {
  localStorage.setItem(STORAGE_DRONES, JSON.stringify(list.value))
  window.dispatchEvent(new CustomEvent(EVT_DRONES))   // 通知其它页面刷新
}
onMounted(loadDrones)

/** —— 过滤 / 分页 —— */
const q = ref('')
const takeoffFilter = ref('')
const search = () => { page.value = 1 }
const reset = () => { q.value = ''; takeoffFilter.value = ''; page.value = 1 }

const filtered = computed(() => {
  let arr = list.value
  const kw = q.value.trim().toLowerCase()
  if (kw) arr = arr.filter(i => (`${i.id}${i.name}${i.deviceSN}`).toLowerCase().includes(kw))
  if (takeoffFilter.value) arr = arr.filter(i => i.takeoff === takeoffFilter.value)
  return arr
})

const page = ref(1)
const pageSize = ref(10)
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))

/** —— 新增 / 删除 —— */
const addVisible = ref(false)
const form = reactive({
  name: '',
  deviceSN: '',
  dockModel: 'DJI Dock 2 Mini',
  deviceModel: 'Mavic 3',
  model: 'DJI Mavic 3',
  stationName: '',       // 仅存“纯站名”，如“徐水”
  status: '空闲中',
  battery: 100,
  enduranceMileage: 25
})
const openAdd = () => {
  form.name = ''
  form.deviceSN = ''
  form.dockModel = 'DJI Dock 2 Mini'
  form.deviceModel = 'Mavic 3'
  form.model = 'DJI Mavic 3'
  form.stationName = ''
  form.status = '空闲中'
  form.battery = 100
  form.enduranceMileage = 25
  addVisible.value = true
}
const nextId = () => (list.value.map(i => Number(i.id) || 0).sort((a, b) => b - a)[0] || 0) + 1

const addSubmit = () => {
  // 组合起飞点展示名 + 经纬度（如需）
  const sel = stationOptions.find(s => s.value === form.stationName)
  const takeoffLabel = sel ? sel.label : withStationSuffix(form.stationName || '')
  list.value.unshift({
    id: nextId(),
    name: form.name || `无人机${Date.now()}`,
    deviceSN: form.deviceSN || `SN-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
    dockModel: form.dockModel || 'DJI Dock 2 Mini',
    deviceModel: form.deviceModel || 'Mavic 3',
    takeoff: takeoffLabel,
    status: form.status || '空闲中',
    battery: Number(form.battery) || 100,
    enduranceMileage: Number(form.enduranceMileage) || 25,
    model: form.model || 'DJI Mavic 3',
    // position: sel ? [sel.lng, sel.lat] : null, // 若后面需要地图，可解开
  })
  addVisible.value = false
  ElMessage.success('新增成功')
  persistDrones()
}

const removeRow = (row) => {
  ElMessageBox.confirm(`确定删除【${row.name}】吗？`, '提示', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消'
  })
    .then(() => {
      list.value = list.value.filter(i => i !== row)
      ElMessage.success('已删除')
      persistDrones()
    })
    .catch(() => {})
}

/** —— 显示辅助 —— */
const statusColor = (s) => s === '空闲中' ? '#67C23A' : s === '工作中' ? '#F56C6C' : '#E6A23C'
</script>

<template>
  <div class="wrap">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="left">
        <span class="label">设备名称</span>
        <el-input
          v-model="q"
          placeholder="输入设备名称/编号/SN 搜索"
          style="width: 260px"
          @keydown.enter="search"
        />
        <span class="label">起飞点</span>
        <el-select v-model="takeoffFilter" placeholder="请选择收费站" style="width: 200px;">
          <el-option label="全部" value="" />
          <el-option v-for="s in takeoffOptions" :key="s" :label="s" :value="s" />
        </el-select>

        <el-button type="primary" @click="search">搜索</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <div class="right">
        <!-- 新增是蓝色 -->
        <el-button type="primary" @click="openAdd">新增设备</el-button>
      </div>
    </div>

    <!-- 表格 -->
    <el-table :data="paged" border stripe :height="tableHeight" style="width: 100%">
      <el-table-column prop="id" label="设备编号" width="100" />
      <el-table-column prop="name" label="设备名称" width="140" />
      <el-table-column prop="deviceSN" label="设备SN" width="160" />
      <el-table-column prop="dockModel" label="Dock型号" width="140" />
      <el-table-column prop="deviceModel" label="设备型号" width="120" />
      <el-table-column prop="takeoff" label="位置信息" width="160" />

      <el-table-column label="当前状态" width="120">
        <template #default="{ row }">
          <span class="status">
            <i class="dot" :style="{ backgroundColor: statusColor(row.status) }" />
            {{ row.status }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="电量" width="90">
        <template #default="{ row }">{{ row.battery }}%</template>
      </el-table-column>
      <el-table-column prop="enduranceMileage" label="续航里程(km)" width="120" />
      <el-table-column prop="model" label="整机型号" width="160" />

      <!-- 操作列：删除是红色 -->
      <el-table-column label="操作" width="120" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="danger" size="small" @click="removeRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        :total="filtered.length"
        :page-size="pageSize"
        :current-page="page"
        :page-sizes="[5, 10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="(v)=>page=v"
        @size-change="(v)=>{pageSize=v;page=1}"
      />
    </div>

    <!-- 新增弹窗 -->
    <el-dialog v-model="addVisible" title="新增设备" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="设备名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="设备SN"><el-input v-model="form.deviceSN" /></el-form-item>
        <el-form-item label="Dock型号"><el-input v-model="form.dockModel" /></el-form-item>
        <el-form-item label="设备型号"><el-input v-model="form.deviceModel" /></el-form-item>
        <el-form-item label="整机型号"><el-input v-model="form.model" /></el-form-item>

        <!-- 位置信息：收费站选择（只存纯站名） -->
        <el-form-item label="位置信息">
          <el-select v-model="form.stationName" placeholder="请选择收费站" style="width: 100%">
            <el-option
              v-for="s in stationOptions"
              :key="s.value"
              :label="s.label"
              :value="s.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 200px">
            <el-option label="空闲中" value="空闲中" />
            <el-option label="工作中" value="工作中" />
            <el-option label="充换电" value="充换电" />
          </el-select>
        </el-form-item>
        <el-form-item label="电量(%)"><el-input v-model.number="form.battery" /></el-form-item>
        <el-form-item label="续航里程(km)">
          <el-input v-model.number="form.enduranceMileage" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <!-- 新增按钮是蓝色 -->
        <el-button type="primary" @click="addSubmit">新增</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wrap { padding: 25px 12px 12px; }
/* 第一個像素調上方空的間距 */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; padding: 10px 12px; margin-bottom: 12px;
  border: 1px solid #ebeef5; border-radius: 4px;
}
.toolbar .label { margin: 0 8px 0 16px; color: #606266; }
.left { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.right { display: flex; align-items: center; gap: 8px; }

.status { color: #606266; display: inline-flex; align-items: center; }
.dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; display: inline-block; }

.pagination {
  padding: 10px; background: #fff; border: 1px solid #ebeef5; border-top: none;
  display: flex; justify-content: flex-end; border-radius: 0 0 4px 4px;
}
:deep(.el-table .el-table__header-wrapper th){ height: 34px; }
:deep(.el-table .cell){ line-height: 28px; padding: 8px; }
</style>
