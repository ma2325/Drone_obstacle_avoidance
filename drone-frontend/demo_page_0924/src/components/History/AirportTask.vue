<template>
  <div style="padding: 20px 10px;">
    <!-- 搜索栏 -->
    <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center;">
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务名称</label>
      <el-input v-model="filters.name" placeholder="请输入任务名称" style="width: 200px;" />

      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">执行日期</label>
      <el-date-picker
        v-model="filters.date"
        type="date"
        placeholder="执行日期"
        style="width: 300px;"
      />

      <el-button type="primary" @click="search">搜索</el-button>
      <el-button @click="reset">重置</el-button>
    </div>

    <!-- 数据表格 -->
    <el-table :data="pagedData" stripe border style="width: 100%;">
      <el-table-column label="" type="index" width="45" />
      <el-table-column prop="name" label="任务名称" />
      <el-table-column label="执行时间" width="220">
        <template #default="{ row }">
          <div style="line-height: 1.5;">
            <div>{{ row.startTime }}</div>
            <div>{{ row.endTime }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="任务类型" />
      <el-table-column prop="route" label="飞行航线" />
      <el-table-column prop="drone" label="执行无人机" />
      <el-table-column prop="creator" label="创建人" />
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <div style="display: flex; gap: 5px; justify-content: center;">
            <el-button type="text" size="small">回放</el-button>
            <el-button type="text" size="small" @click="openMediaDrawer(row)">媒体文件</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页控件 -->
    <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
      <el-pagination
        :total="filteredData.length"
        :page-size="pageSize"
        :current-page="currentPage"
        :page-sizes="[5, 10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
    </div>

    <!-- 媒体文件弹窗 -->
    <el-dialog
      v-model="mediaDrawerVisible"
      title="媒体文件"
      width="60%"
      :close-on-click-modal="false"
      :append-to-body="true"
    >
      <el-tabs v-model="currentMediaTab" @tab-change="handleTabChange">
        <el-tab-pane label="图片" name="image" />
        <el-tab-pane label="视频" name="video" />
      </el-tabs>

      <el-table :data="currentMediaList" border style="width: 100%; margin-top: 10px;">
        <el-table-column prop="fileName" label="文件名称" />
        <el-table-column prop="filePath" label="文件路径" />
        <el-table-column prop="model" label="机型类型" />
        <el-table-column prop="createTime" label="创建时间" />
        <el-table-column label="预览" width="180">
          <template #default="{ row }">
            <div v-if="currentMediaTab === 'image'">
              <img :src="row.url" alt="预览图" style="width: 120px; height: auto;" />
            </div>
            <div v-else-if="currentMediaTab === 'video'">
              <video :src="row.url" controls style="width: 160px; max-height: 100px;" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-link type="primary" @click="handleDownload(row)">下载</el-link>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
        <el-pagination
          :total="currentMediaList.length"
          :page-size="20"
          layout="total, sizes, prev, pager, next, jumper"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import tasks from '@/test-data/tasks.json'

/** ========= 本地假数据（无需接口） ========= */
const allData = ref(tasks)
  
/** ========= 媒体弹窗 ========= */
const mediaDrawerVisible = ref(false)
const currentMediaTab = ref('image')
const imageMediaList = ref([])
const videoMediaList = ref([])

const currentMediaList = computed(() =>
  currentMediaTab.value === 'image' ? imageMediaList.value : videoMediaList.value
)

function openMediaDrawer(row) {
  // 把素材放到 /public/media 下（见下方说明）
  imageMediaList.value = [
    { fileName: '任务示例_1.jpg', filePath: '/media/img1.jpg',  model: 'Mavic 3E', createTime: '2025-07-01 10:00', url: '/media/img1.jpg' },
    { fileName: '任务示例_2.jpg', filePath: '/media/img2.jpg',  model: 'M300 RTK', createTime: '2025-07-02 09:20', url: '/media/img2.jpg' }
  ]
  videoMediaList.value = [
    { fileName: '片段_1.mp4',     filePath: '/media/video1.mp4', model: 'M300 RTK', createTime: '2025-07-01 14:32', url: '/media/video1.mp4' }
  ]
  currentMediaTab.value = 'image'
  mediaDrawerVisible.value = true
}
function handleTabChange() {
  /* 需要的话在切换时重置分页等 */
}
function handleDownload(row) {
  const link = document.createElement('a')
  link.href = row.url
  link.download = row.fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/** ========= 搜索 & 分页 ========= */
const filters = ref({ name: '', date: null })
const currentPage = ref(1)
const pageSize = ref(10)

const filteredData = computed(() => {
  let result = allData.value

  // 名称模糊匹配
  if (filters.value.name) {
    const key = filters.value.name.trim()
    result = result.filter(item => item.name.includes(key))
  }

  // 执行日期过滤（选中的日期需落在任务起止日期之间）
  if (filters.value.date instanceof Date) {
    const y = filters.value.date.getFullYear()
    const m = String(filters.value.date.getMonth() + 1).padStart(2, '0')
    const d = String(filters.value.date.getDate()).padStart(2, '0')
    const selectedDateStr = `${y}-${m}-${d}`

    result = result.filter(item => {
      const startDateStr = item.startTime.slice(0, 10)
      const endDateStr   = item.endTime.slice(0, 10)
      return selectedDateStr >= startDateStr && selectedDateStr <= endDateStr
    })
  }

  return result
})

const pagedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

const search = () => { currentPage.value = 1 }
const reset = () => { filters.value.name = ''; filters.value.date = null; currentPage.value = 1 }
const handlePageChange = (val) => { currentPage.value = val }
const handlePageSizeChange = (val) => { pageSize.value = val; currentPage.value = 1 }
</script>

<style scoped>
/* 表格行高 */
::v-deep(.el-table .el-table__row) { height: 38px; }
/* 表头高度和文字垂直居中 */
::v-deep(.el-table .el-table__header-wrapper th) {
  height: 30px;
  line-height: 50px;
}
/* 内容行高 */
::v-deep(.el-table .cell) { line-height: 35px; }
</style>
