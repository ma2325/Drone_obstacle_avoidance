<!-- src/components/TaskLine/Airspace.vue -->
<template>
  <div class="airspace-wrap">
    <!-- 搜索栏（第一行） -->
    <div class="filters">
      <label class="f-label">空域名称</label>
      <el-input v-model="filters.keyword" placeholder="请输入空域名称" style="width: 200px;" />

      <label class="f-label">有效时间</label>
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 260px;"
      />

      <label class="f-label">空域类型</label>
      <el-select v-model="filters.type" placeholder="请选择空域类型" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option v-for="t in types" :key="t" :label="t" :value="t" />
      </el-select>

      <el-button @click="reset">重置</el-button>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <!-- 第二行：创建按钮 -->
    <div class="actions-row">
      <el-button type="primary" @click="openCreateDialog">创建空域</el-button>
    </div>

    <!-- 分组 + 卡片 -->
    <div v-for="(group, ym) in groupedByMonth" :key="ym" class="month-group">
      <div class="month-title">{{ ym }}</div>

      <div class="task-card-container">
        <div
          v-for="item in group"
          :key="item.id"
          class="task-card"
        >
          <!-- 删除按钮（右上角），阻止冒泡避免触发整卡片点击 -->
          <el-button
            class="card-delete"
            type="danger"
            link
            @click.stop="deleteAirspace(item.id)"
          >
            删除
          </el-button>

          <!-- 缩略图 / 封面：优先 cover，再退回 thumbUrl -->
          <img
            :src="item.cover || item.thumbUrl || placeholder"
            class="task-thumb-left"
            alt="空域缩略图"
            @click="goToMap(item)"
          />

          <div class="task-info-right">
            <div class="task-header">
              <div class="task-title" @click="goToMap(item)">{{ item.name }}</div>
              <el-tag size="small" :type="typeTag(item.type)">{{ item.type }}</el-tag>
            </div>

            <div class="task-line">创建时间：{{ item.createdAt }}</div>
            <div class="task-line">有效时间：{{ item.validFrom || '-' }} - {{ item.validTo || '-' }}</div>
            <div class="task-line ellipsis">备注信息：{{ item.note || '-' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pager">
      <el-pagination
        :total="filteredList.length"
        :page-size="pageSize"
        :current-page="currentPage"
        :page-sizes="[9, 12, 24, 48]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
    </div>

    <!-- 创建空域（深色弹窗） -->
    <el-dialog v-model="dialogVisible" title="创建空域" width="560px" class="dark-dialog">
      <div class="dialog-content">
        <div class="section">
          <h3 class="section-title">选择空域类型</h3>
          <div class="option-group">
            <el-radio-group v-model="form.type" class="radio-group square-button">
              <el-radio-button v-for="t in types" :key="t" :value="t">
                <div class="icon-radio"><span>{{ t }}</span></div>
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">空域名称</h3>
          <el-input v-model="form.name" placeholder="请输入空域名称" />
        </div>

        <div class="section two">
          <div>
            <h3 class="section-title">开始日期</h3>
            <el-date-picker v-model="form.validFrom" type="date" placeholder="开始日期" style="width: 100%;" />
          </div>
          <div>
            <h3 class="section-title">结束日期</h3>
            <el-date-picker v-model="form.validTo" type="date" placeholder="结束日期" style="width: 100%;" />
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">备注信息</h3>
          <el-input v-model="form.note" placeholder="请输入相关信息" />
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible=false" class="cancel-btn">取消</el-button>
          <el-button type="primary" @click="submitCreate" class="confirm-btn">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * Airspace.vue — 空域列表页
 * - 卡片支持删除（同步移除 localStorage）
 * - 缩略图兼容 cover / thumbUrl
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const emit = defineEmits(['action'])

/** 常量 */
const STORAGE_KEY = 'AIRSPACE_DICT'
const types = ['禁飞区','适飞区','限飞区','危险区','保护区']
const placeholder = '/media/thumbnails/default.png'

/** 列表数据 */
const dictRef = ref({})
const listRef = ref([])
restoreFromStorage()

/** 过滤与分页 */
const filters = ref({ keyword:'', dateRange:null, type:'' })
const currentPage = ref(1)
const pageSize = ref(9)

const filteredList = computed(() => {
  let arr = [...listRef.value]
  const kw = (filters.value.keyword || '').trim().toLowerCase()
  if (kw) arr = arr.filter(i => (i.name || '').toLowerCase().includes(kw))
  if (filters.value.type) arr = arr.filter(i => i.type === filters.value.type)
  if (Array.isArray(filters.value.dateRange) && filters.value.dateRange.length === 2) {
    const [s, e] = filters.value.dateRange
    const st = new Date(s).getTime()
    const et = new Date(e).getTime()
    arr = arr.filter(i => {
      const a = i.validFrom ? new Date(i.validFrom).getTime() : 0
      const b = i.validTo   ? new Date(i.validTo).getTime()   : 0
      return (!st || a >= st) && (!et || b <= et)
    })
  }
  return arr
})
const paged = computed(() =>
  filteredList.value.slice((currentPage.value - 1) * pageSize.value, currentPage.value * pageSize.value)
)

/** 分组（按月份） */
const groupedByMonth = computed(() => {
  const map = {}
  paged.value.forEach(item => {
    const ym = (item.createdAt || '').slice(0,7).replace('-', '年') + '月' || '未分组'
    if (!map[ym]) map[ym] = []
    map[ym].push(item)
  })
  return map
})

/** 弹窗表单 */
const dialogVisible = ref(false)
const form = ref({ name:'', type:'禁飞区', validFrom:'', validTo:'', note:'' })

function openCreateDialog () {
  form.value = { name:'', type:'禁飞区', validFrom:'', validTo:'', note:'' }
  dialogVisible.value = true
}

function submitCreate () {
  if (!form.value.name?.trim()) return ElMessage.error('空域名称不能为空')
  const id = `AS-${Date.now()}`
  const now = new Date()
  const createdAt = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`
  const obj = {
    id,
    name: form.value.name.trim(),
    type: form.value.type,
    validFrom: form.value.validFrom || '',
    validTo: form.value.validTo || '',
    note: form.value.note || '',
    cover: '',           // 由 MapView 截图回写
    thumbUrl: '',
    polygon: [],
    createdAt
  }
  dictRef.value[id] = obj
  persist()
  listRef.value.unshift(obj)

  dialogVisible.value = false
  ElMessage.success('空域创建成功，进入绘制态')

  emit('action', {
    type: 'open-map-from-airspace',
    data: {
      airspaceId: id,
      name: obj.name,
      airspaceType: obj.type,
      polygon: [],
      drawNew: true,
      restore: true
    }
  })
}

/** 卡片 → 地图 */
function goToMap (item) {
  emit('action', {
    type: 'open-map-from-airspace',
    data: {
      airspaceId: item.id,
      name: item.name,
      airspaceType: item.type,
      polygon: item.polygon || [],
      center: item.polygon?.[0] || null,
      drawNew: false,
      restore: true
    }
  })
}

/** 删除卡片 */
function deleteAirspace (id) {
  ElMessageBox.confirm('确定要删除这个空域吗？此操作不可撤销。', '提示', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    // 1) 删除本地字典
    delete dictRef.value[id]
    persist()
    // 2) 列表移除
    const idx = listRef.value.findIndex(x => x.id === id)
    if (idx !== -1) listRef.value.splice(idx, 1)
    ElMessage.success('已删除')
  }).catch(() => {})
}

/** 本地存取 */
function persist () {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(dictRef.value)) } catch {}
}
function restoreFromStorage () {
  try {
    const d = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    if (d && typeof d === 'object') {
      dictRef.value = d
      listRef.value = Object.values(d).sort((a,b) => (b.createdAt||'').localeCompare(a.createdAt||''))
    }
  } catch {
    dictRef.value = {}
    listRef.value = []
  }
}

/** MapView 保存回写（airspace-updated） */
let off = null
onMounted(() => {
  const h = (e) => {
    const data = e.detail || {}
    if (!data?.id) return
    const old = dictRef.value[data.id] || {}
    const merged = { ...old, ...data }     // 包含 cover / polygon / type / name 等
    dictRef.value[data.id] = merged
    persist()
    const i = listRef.value.findIndex(x => x.id === data.id)
    if (i !== -1) listRef.value.splice(i, 1)
    listRef.value.unshift(merged)
    ElMessage.success('空域已保存')
  }
  window.addEventListener('airspace-updated', h)
  off = () => window.removeEventListener('airspace-updated', h)
})
onUnmounted(() => { off && off() })

/** 工具 */
function typeTag (t) {
  switch (t) {
    case '禁飞区': return 'danger'
    case '限飞区': return 'warning'
    case '危险区': return 'warning'
    case '保护区': return 'success'
    default: return 'info'
  }
}

/** 搜索 / 分页 */
function search () { currentPage.value = 1 }
function reset () { filters.value = { keyword:'', dateRange:null, type:'' }; currentPage.value = 1 }
function handlePageChange (v) { currentPage.value = v }
function handlePageSizeChange (v) { pageSize.value = v; currentPage.value = 1 }
</script>

<style scoped>
.airspace-wrap { padding: 14px 10px; }

/* 搜索栏 */
.filters {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px;
}
.f-label { font-weight: 600; width: 80px; text-align: right; color: #303133; }

/* 第二行：创建按钮 */
.actions-row { margin-bottom: 16px; }

/* ===== 卡片样式 ===== */
.task-card-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

.task-card {
  position: relative;                  /* 为右上角删除按钮定位 */
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s ease;
}
.task-card:hover { transform: translateY(-2px); }

/* 删除按钮（右上角） */
.card-delete {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 2;
}

/* 缩略图（左） */
.task-thumb-left {
  height: 160px;
  width: 200px;
  border-right: 1px solid #e0e0e0;
  flex-shrink: 0;
  cursor: pointer;
}

/* 信息区（右） */
.task-info-right {
  flex: 1;
  padding: 10px 16px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.task-header {
  display: flex; justify-content: space-between; align-items: center;
  font-weight: bold; font-size: 14px; margin-bottom: 4px;
}
.task-title { font-weight: 600; color: #111827; cursor: pointer; }
.task-line { margin: 2px 0; color: #6b7280; }
.ellipsis { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 分组标题与分页 */
.month-group { margin-bottom: 16px; }
.month-title { font-weight: 600; color: #6b7280; margin: 8px 0; }
.pager { display: flex; justify-content: flex-end; margin-top: 10px; }

/* 深色弹窗（与 RoutePlan 统一） */
:deep(.dark-dialog) { background-color: #1f1f1f !important; color: #ffffff !important; border-radius: 8px !important; }
:deep(.dark-dialog .el-dialog__header) { padding: 16px 20px; border-bottom: 1px solid #444; margin-right: 0; background-color: #1f1f1f; }
:deep(.dark-dialog .el-dialog__title) { font-size: 16px; font-weight: 600; color: #ffffff !important; }
.dialog-content { padding: 20px; background-color: #1f1f1f; }
.section { margin-bottom: 20px; }
.section.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.section-title { font-size: 14px; color: #f0f0f0; margin-bottom: 10px; font-weight: 600; }
.option-group { margin-left: 4px; }
.radio-group { display: flex; flex-wrap: wrap; gap: 20px 25px; }
.square-button :deep(.el-radio-button__inner) {
  width: 143px; height: 90px; display: flex; align-items: center; justify-content: center;
  border-radius: 5px; font-size: 14px; font-weight: 600; text-align: center;
  background-color: #9eb0ff2f; color: #ffffff; border-color: #444444ba; transition: all .2s;
}
.icon-radio { display: flex; flex-direction: column; align-items: center; gap: 6px; }
:deep(.dark-dialog .el-radio-button__inner:hover) { border-color: #409EFF; color: #409EFF; }
:deep(.dark-dialog .el-radio-button.is-active .el-radio-button__inner) { background-color: #409EFF; border-color: #409EFF; color: #ffffff; }
.dialog-footer { background-color: #1f1f1f; border-top: 1px solid #444444ba; display: flex; justify-content: flex-end; padding: 12px 20px; }
.cancel-btn, .confirm-btn { padding: 8px 20px; border-radius: 4px; }
.cancel-btn { margin-right: 12px; }
</style>
