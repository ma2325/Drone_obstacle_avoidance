<template>
  <div style="padding: 20px 10px;;"></div>
    <div>
      <!-- 搜索栏 -->
      <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
        <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务名称</label>
        <el-input v-model="filters.name" placeholder="请输入任务名称" style="width: 200px;" />
        
        <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">执行日期</label>
        <el-date-picker
          v-model="filters.date"
          type="date"
          placeholder="执行日期"
          style="width: 200px;"
        />

        <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务类型</label>
        <el-select v-model="filters.type" placeholder="请选择任务类型" style="width: 200px;">
          <el-option label="全部" value="" />
          <el-option label="立即任务" value="立即任务" />
          <el-option label="定时任务" value="定时任务" />
        </el-select>

        <el-button @click="reset">重置</el-button>
        <el-button type="primary" @click="search">搜索</el-button>
      </div>

    <!-- 新建任务按钮 -->
<el-button type="primary" @click="openTaskDialog" style="margin-left: 10px; margin-bottom: 10px;">新建任务</el-button>

<!---------------------------新建任务弹窗 ---------------------------------->
<el-dialog v-model="taskDialogVisible" title="机场任务" width="500px">
  <el-form :model="newTask" label-width="100px">
    <el-form-item label="任务名称">
      <el-input v-model="newTask.name" placeholder="请输入任务名称" />
    </el-form-item>

    <el-form-item label="任务类型">
      <el-select v-model="newTask.type" placeholder="请选择任务类型">
        <el-option label="立即执行" value="立即任务" />
        <el-option label="定时任务" value="定时任务" />
      </el-select>
    </el-form-item>

    <el-form-item label="执行机场">
      <el-select v-model="newTask.location" placeholder="请选择执行机场">
        <el-option label="松江新城" value="松江新城" />
        <el-option label="嘉定基地" value="嘉定基地" />
      </el-select>
    </el-form-item>

    <el-form-item label="任务航线">
      <el-select v-model="newTask.route" placeholder="请选择任务航线">
        <el-option label="测试0412" value="测试0412" />
        <el-option label="张三测试任务A" value="张三测试任务A" />
      </el-select>
    </el-form-item>

    <el-form-item label="返航高度(m)">
      <el-input-number v-model="newTask.cruise" :min="30" :max="500" />
    </el-form-item>

    <el-form-item label="失控动作">
      <el-select v-model="newTask.activity" placeholder="请选择">
        <el-option label="自动返航" value="自动返航" />
        <el-option label="悬停" value="悬停" />
        <el-option label="退出航线并返航" value="退出航线并返航" />
      </el-select>
    </el-form-item>
  </el-form>

  <template #footer>
    <el-button @click="taskDialogVisible = false">取消</el-button>
    <el-button type="primary" @click="submitTask">确定</el-button>
  </template>
</el-dialog>
<!----------------------------新建任务弹窗结束----------------------------------->
 
    <!-- 数据表格 -->
    <el-table :data="pagedData" stripe border style="width: 100%;">
      <el-table-column label="" type="index" width="30" />
      <el-table-column prop="name" label="任务名称" width="95" />
      <el-table-column label="计划时间" width="170">
        <template #default="{ row }">
          <div style="line-height: 1.5;">
            <div>{{ row.planStartTime }}</div>
            <div>{{ row.planEndTime }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="执行时间" width="170">
        <template #default="{ row }">
          <div style="line-height: 1.5;">
            <div>{{ row.startTime }}</div>
            <div>{{ row.endTime }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="任务执行状态" width="110">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="type" label="任务类型" width="90" />
      <el-table-column prop="route" label="飞行路线" width="90" />
      <el-table-column prop="location" label="执行机场" width="90" />
      <el-table-column prop="cruise" label="巡航高度(m)" width="105" />
      <el-table-column prop="activity" label="航线中失联动作" width="125" />
      <el-table-column prop="creator" label="创建人" width="90" />
      <el-table-column prop="media" label="媒体上传" width="100">
        <template #default="{ row }">
          <span v-if="row.media === '无媒体文件'">{{ row.media }}</span>
          <el-button v-else type="text" @click="openMediaDrawer(row)">{{ row.media }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="205" fixed="right" align="center">
        <template #default="{ row }">
          <div style="display: flex; gap: 1px;justify-content: center;">
            <el-button type="text" size="small">回放</el-button>
            <el-button type="text" size="small" @click="openMediaDrawer(row)">媒体文件</el-button>
            <el-button type="text" size="small" @click="deleteTask(row)">删除</el-button>
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
        <el-table-column label="操作" width="100">
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
import { ElMessage } from 'element-plus'  // 用于错误提示
import taskData from '@/assets/taskData_all.json'//数据导入
const allData = ref(taskData)

// ========== 原始任务数据 ==========
// const allData = ref([
//   {
//     name: '测试任务A',
//     startTime: '2025-04-13 08:00:00',
//     endTime: '2025-04-13 10:00:00',
//     planStartTime: '2025-04-12 12:00:00',
//     planEndTime: '2025-04-12 18:00:00',
//     status: '完成',
//     type: '立即任务',
//     route: '航线A',
//     location: '松江机场',
//     cruise: '120',
//     activity: '返航降落',
//     creator: 'user1',
//     media: '无媒体文件'
//   },
//   {
//     name: '测试任务B',
//     startTime: '2025-04-14 09:00:00',
//     endTime: '2025-04-14 11:30:00',
//     planStartTime: '2025-04-13 14:00:00',
//     planEndTime: '2025-04-13 20:00:00',
//     status: '执行中',
//     type: '定时任务',
//     route: '航线B',
//     location: '嘉定机场',
//     cruise: '100',
//     activity: '悬停',
//     creator: 'user2',
//     media: '待上传(1/2)'
//   },
//   {
//     name: '测试任务C',
//     startTime: '2025-04-13 23:00:00',
//     endTime: '2025-04-14 01:00:00',
//     planStartTime: '2025-04-12 15:00:00',
//     planEndTime: '2025-04-12 16:00:00',
//     status: '失败',
//     type: '立即任务',
//     route: '航线C',
//     location: '青浦机场',
//     cruise: '90',
//     activity: '中断返航',
//     creator: 'user3',
//     media: '无媒体文件'
//   }
// ])

// ========== x新建任务弹窗逻辑 + 数据插入 ？ ==========
const taskDialogVisible = ref(false)
const newTask = ref({
  name: '',
  type: '立即任务',
  location: '',
  route: '',
  cruise: 100,
  activity: '自动返航'


})

// ========== 打开弹窗方法 ？ ===========
const openTaskDialog = () => {
  taskDialogVisible.value = true
}

// ========== 提交任务到表格 ？ ===========
const submitTask = () => {
  const now = new Date()
  const format = (d) => d.toISOString().slice(0, 19).replace('T', ' ')
  const timeStr = format(now)

  const task = {
    ...newTask.value,
    planStartTime: timeStr,
    planEndTime: timeStr,
    startTime: timeStr,
    endTime: timeStr,
    status: '完成',
    creator: 'adminPC',
    media: '待上传(1/2)'
  }

  allData.value.unshift(task)
  taskDialogVisible.value = false
  ElMessage.success('任务创建成功')
}

// ========== 搜索过滤与分页 ==========
const filters = ref({ name: '', date: null, type: '' })
const currentPage = ref(1)
const pageSize = ref(10)

const filteredData = computed(() => {
  let result = allData.value

  // 名称过滤
  if (filters.value.name) {
    result = result.filter(item => item.name.includes(filters.value.name))
  }

  // 日期过滤（执行时间区间）
  if (filters.value.date) {
    const y = filters.value.date.getFullYear()
    const m = String(filters.value.date.getMonth() + 1).padStart(2, '0')
    const d = String(filters.value.date.getDate()).padStart(2, '0')
    const selectedDateStr = `${y}-${m}-${d}`

    result = result.filter(item => {
      const startDateStr = item.startTime.slice(0, 10)
      const endDateStr = item.endTime.slice(0, 10)
      return selectedDateStr >= startDateStr && selectedDateStr <= endDateStr
    })
  }

  // 任务类型过滤
  if (filters.value.type) {
    result = result.filter(item => item.type === filters.value.type)
  }

  return result
})

const pagedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

const search = () => { currentPage.value = 1 }
const reset = () => {
  filters.value = { name: '', date: null, type: '' }
  currentPage.value = 1
}

const handlePageChange = val => { currentPage.value = val }
const handlePageSizeChange = val => {
  pageSize.value = val
  currentPage.value = 1
}

// 状态颜色映射
const getStatusType = (status) => {
  switch(status) {
    case '执行中': return 'warning'
    case '完成': return 'success'
    case '失败': return 'danger'
    default: return 'info'
  }
}

// ========== 媒体弹窗功能 ==========
const mediaDrawerVisible = ref(false)              // 弹窗显示状态
const currentMediaTab = ref('image')               // 当前媒体类型 tab（image / video）
const imageMediaList = ref([])                     // 图片数据列表
const videoMediaList = ref([])                     // 视频数据列表
const loadingMedia = ref(false)                    // 是否加载中（可用于添加 loading 效果）

// 当前媒体列表（图片或视频）
const currentMediaList = computed(() => {
  return currentMediaTab.value === 'image' ? imageMediaList.value : videoMediaList.value
})

/**
 * 打开媒体弹窗，加载对应任务的媒体数据（模拟接口）
 */
const openMediaDrawer = async (row) => {
  console.log('打开媒体文件弹窗', row)
  mediaDrawerVisible.value = true
  currentMediaTab.value = 'image'
  loadingMedia.value = true

  try {
    // 👇 模拟后端接口延迟
    await new Promise(resolve => setTimeout(resolve, 500))

    // 👇 模拟媒体数据（实际可替换成接口返回的数据）
    imageMediaList.value = [
      {
        fileName: `${row.name}_图片1.jpg`,
        filePath: '/media/img1.jpg',
        model: '型号A',
        createTime: '2025-07-01',
        url: '/media/img1.jpg'
      }
    ]

    videoMediaList.value = [
      {
        fileName: `${row.name}_视频1.mp4`,
        filePath: '/media/video1.mp4',
        model: '型号B',
        createTime: '2025-07-02',
        url: '/media/video1.mp4'
      }
    ]
  } catch (err) {
    ElMessage.error('媒体文件加载失败')
    imageMediaList.value = []
    videoMediaList.value = []
  } finally {
    loadingMedia.value = false
  }
}

/**
 * 切换 Tab 时（图片 / 视频）
 */
const handleTabChange = (tab) => {
  console.log('切换媒体类型：', tab)
}

/**
 * 下载媒体文件
 */
const handleDownload = (row) => {
  const link = document.createElement('a')
  link.href = row.url
  link.download = row.fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}


// ========== 任务删除 ==========
const deleteTask = (row) => {
  allData.value = allData.value.filter(item => item !== row)
  ElMessage.success('任务已删除')
}
</script>


<style scoped>
::v-deep(.el-table .el-table__row) {
  height: 38px;
}
::v-deep(.el-table .el-table__header-wrapper th) {
  height: 30px;
  line-height: 50px;
}
::v-deep(.el-table .cell) {
  line-height: 35px;
}
</style>
