<template>
  <div style="padding: 20px 10px;"></div>
  <div>
    <!-- 搜索栏：用于过滤任务ID、任务类型和巡检类型 -->
    <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务ID</label>
      <el-input v-model="filters.id" placeholder="请输入任务ID" style="width: 200px;" />
      
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务类型</label>
      <el-select v-model="filters.taskType" placeholder="请选择任务类型" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option label="区域扫描" value="区域扫描" />
        <el-option label="点位扫描" value="点位扫描" />
      </el-select>
      
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">巡检类型</label>
      <el-select v-model="filters.type" placeholder="请选择巡检类型" style="width: 200px;" multiple>
        <el-option label="全部" value="" />
        <el-option v-for="type in allInspectionTypes" :key="type" :label="type" :value="type" />
      </el-select>

      <el-button @click="reset">重置</el-button>
      <el-button @click="clearTypeFilter">清除类型</el-button>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <!-- 新建任务按钮：触发新建任务弹窗 -->
    <el-button type="primary" @click="openTaskDialog(null)" style="margin-left: 10px; margin-bottom: 10px;">新建任务</el-button>

    <!-- 新建/修改任务弹窗：动态显示巡检类型根据任务类型 -->
    <el-dialog v-model="taskDialogVisible" :title="editMode ? '修改任务' : '新建任务'" width="500px">
      <el-form :model="currentTask" label-width="100px">
        <el-form-item label="任务ID">
          <el-input v-model="currentTask.id" placeholder="请输入任务ID" :disabled="editMode" />
        </el-form-item>

        <el-form-item label="任务类型">
          <el-select v-model="currentTask.taskType" placeholder="请选择任务类型" @change="updateInspectionTypes">
            <el-option label="区域扫描" value="区域扫描" />
            <el-option label="点位扫描" value="点位扫描" />
          </el-select>
        </el-form-item>

        <el-form-item label="巡检类型">
          <el-checkbox-group v-model="currentTask.type">
            <!-- 根据任务类型动态显示巡检类型 -->
            <el-checkbox v-if="currentTask.taskType === '区域扫描'" v-for="option in areaTypes" :key="option" :label="option">{{ option }}</el-checkbox>
            <el-checkbox v-if="currentTask.taskType === '点位扫描'" v-for="option in pointTypes" :key="option" :label="option">{{ option }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="起飞点">
          <el-select v-model="currentTask.takeoff" placeholder="请选择起飞点">
            <el-option label="杜家坎收费站" value="杜家坎收费站" />
            <el-option label="琉璃河收费站" value="琉璃河收费站" />
            <el-option label="涿州北收费站" value="涿州北收费站" />
            <el-option label="涿州收费站" value="涿州收费站" />
            <el-option label="高碑店收费站" value="高碑店收费站" />
            <el-option label="定兴收费站" value="定兴收费站" />
            <el-option label="徐水收费站" value="徐水收费站" />
            <el-option label="保定北收费站" value="保定北收费站" />
            <el-option label="保定收费站" value="保定收费站" />
            <el-option label="清苑收费站" value="清苑收费站" />
            <el-option label="望都收费站" value="望都收费站" />
            <el-option label="定州收费站" value="定州收费站" />
            <el-option label="新乐收费站" value="新乐收费站" />
            <el-option label="藁城北收费站" value="藁城北收费站" />
            <el-option label="石家庄机场收费站" value="石家庄机场收费站" />
            <el-option label="石家庄北收费站" value="石家庄北收费站" />
            <el-option label="石家庄收费站" value="石家庄收费站" />
          </el-select>
        </el-form-item>

        <el-form-item label="航线编号">
          <el-input v-model="currentTask.route_id" placeholder="请输入航线编号" />
        </el-form-item>

        <el-form-item label="航线里程">
          <el-input v-model="currentTask.route" placeholder="请输入航线里程" />
        </el-form-item>

        <el-form-item label="折返点设置">
          <el-input v-model="currentTask.turnaround" placeholder="请输入折返点设置" />
        </el-form-item>

        <el-form-item label="时间窗">
          <el-time-picker
            v-model="currentTask.time_window"
            is-range
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="HH:mm"
            value-format="HH:mm"
          />
        </el-form-item>

        <el-form-item label="飞行趟数">
          <el-input v-model="currentTask.flightCount" placeholder="请输入飞行趟数" />
        </el-form-item>

        <el-form-item label="执勤无人机">
          <el-input v-model="currentTask.drone" placeholder="请选择执勤无人机" readonly />
          <el-button type="primary" @click="openDroneDialog" style="margin-top: 10px;">选择无人机</el-button>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTask">确定</el-button>
      </template>
    </el-dialog>

    <!-- 选择无人机弹窗：后续设计 -->
    <el-dialog v-model="droneDialogVisible" title="选择无人机" width="600px">
      <p>无人机选择表格（后续设计）</p>
      <el-table :data="[]" style="width: 100%;">
      </el-table>

      <template #footer>
        <el-button @click="droneDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="selectDrone">确定</el-button>
      </template>
    </el-dialog>

    <!-- 数据表格：显示任务详情，优化列宽均衡 -->
    <el-table :data="pagedData" stripe border :fit="true" style="width: 100%;">
      <el-table-column label="" type="index" width="50" /> <!-- 序号列 -->
      <el-table-column prop="id" label="任务ID" width="120" />
      <el-table-column prop="taskType" label="任务类型" width="120" />
      <el-table-column prop="type" label="巡检类型" width="130">
        <template #default="{ row }">
          <div v-for="(type, index) in row.type" :key="index" style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="margin-right: 8px;">{{ type }}</span>
            <el-icon><Check /></el-icon>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="route_id" label="航线编号" width="120" />
      <el-table-column prop="route" label="航线里程" width="150" />
      <el-table-column prop="takeoff" label="起飞点" width="120" />
      <el-table-column prop="turnaround" label="折返点设置" width="150" />
      <el-table-column prop="time_window" label="时间窗" width="120">
        <template #default="{ row }">
          {{ row.time_window ? row.time_window.join('-') : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="flightCount" label="飞行趟数" width="90">
        <template #default="{ row }">
          {{ row.flightCount || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="执勤无人机" width="130">
        <template #default="{ row }">
          {{ row.drone }}
          <el-button type="text" size="small" @click="openDroneDialogForRow(row)">选择</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right" align="center">
        <template #default="{ row }">
          <div style="display: flex; gap: 10px; justify-content: center;">
            <el-button type="text" size="small" @click="openTaskDialog(row)">修改</el-button>
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

    <!-- 媒体文件弹窗：保留原有 -->
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
import { ref, computed, watch } from 'vue'
import { ElMessage, ElIcon } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import taskData from '@/assets/taskData_all.json'

// 巡检类型常量
const areaTypes = ['抛洒物识别', '团雾检测', '病害识别', '拥堵点检测'] // 区域扫描的巡检类型
const pointTypes = ['桥梁巡检', '边坡巡检'] // 点位扫描的巡检类型
const allInspectionTypes = [...areaTypes, ...pointTypes] // 所有巡检类型，用于搜索栏

const allData = ref(taskData.map(item => {
  const hasAreaType = item.type.some(t => areaTypes.includes(t))
  const hasPointType = item.type.some(t => pointTypes.includes(t))
  let taskType = '区域扫描' // 默认值
  if (hasPointType && !hasAreaType) {
    taskType = '点位扫描' // 仅当包含点位类型且无区域类型时设为点位扫描
  }
  return { ...item, taskType }
}))

const taskDialogVisible = ref(false)
const droneDialogVisible = ref(false)
const editMode = ref(false)
const currentTask = ref({
  id: '',
  taskType: '区域扫描', // 默认任务类型
  type: [],
  route: '',
  takeoff: '',
  route_id: '',
  turnaround: '',
  time_window: null,
  flightCount: '', // 新增飞行趟数
  drone: ''
})

// 更新巡检类型选项，根据任务类型动态调整
const updateInspectionTypes = () => {
  currentTask.value.type = [] // 清空原有巡检类型
}

// 打开任务弹窗：新增或修改
const openTaskDialog = (row) => {
  if (row) {
    editMode.value = true
    currentTask.value = { ...row }
  } else {
    editMode.value = false
    currentTask.value = {
      id: '',
      taskType: '区域扫描',
      type: [],
      route: '',
      takeoff: '',
      route_id: '',
      turnaround: '',
      time_window: null,
      flightCount: '',
      drone: ''
    }
  }
  updateInspectionTypes() // 打开时更新巡检类型
  taskDialogVisible.value = true
}

// 提交任务：新增或修改
const submitTask = () => {
  if (editMode.value) {
    const index = allData.value.findIndex(item => item.id === currentTask.value.id)
    if (index !== -1) {
      allData.value[index] = { ...currentTask.value }
      ElMessage.success('任务修改成功')
    }
  } else {
    currentTask.value.id = `T-${allData.value.length + 1}`
    allData.value.unshift({ ...currentTask.value })
    ElMessage.success('任务创建成功')
  }
  taskDialogVisible.value = false
}

// 打开无人机选择弹窗
const openDroneDialog = () => {
  droneDialogVisible.value = true
}

const openDroneDialogForRow = (row) => {
  openDroneDialog()
}

const selectDrone = () => {
  currentTask.value.drone = '选中的无人机'
  droneDialogVisible.value = false
}

// 搜索过滤与分页
const filters = ref({ id: '', taskType: '', type: [] })
const currentPage = ref(1)
const pageSize = ref(5)

const filteredData = computed(() => {
  let result = allData.value

  if (filters.value.id) {
    result = result.filter(item => item.id.includes(filters.value.id))
  }

  if (filters.value.taskType) {
    result = result.filter(item => item.taskType === filters.value.taskType)
  }

  if (filters.value.type.length > 0) {
    result = result.filter(item => filters.value.type.every(t => item.type.includes(t)))
  }

  return result
})

const pagedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredData.value.slice(start, start + pageSize.value)
})

const search = () => { currentPage.value = 1 }
const reset = () => {
  filters.value = { id: '', taskType: '', type: [] }
  currentPage.value = 1
}
const clearTypeFilter = () => {
  filters.value.type = []
}

const handlePageChange = val => { currentPage.value = val }
const handlePageSizeChange = val => {
  pageSize.value = val
  currentPage.value = 1
}

// 媒体弹窗功能
const mediaDrawerVisible = ref(false)
const currentMediaTab = ref('image')
const imageMediaList = ref([])
const videoMediaList = ref([])

const currentMediaList = computed(() => {
  return currentMediaTab.value === 'image' ? imageMediaList.value : videoMediaList.value
})

const openMediaDrawer = async (row) => {
  mediaDrawerVisible.value = true
  currentMediaTab.value = 'image'

  await new Promise(resolve => setTimeout(resolve, 500))
  imageMediaList.value = [
    { fileName: `${row.name}_图片1.jpg`, filePath: '/media/img1.jpg', model: '型号A', createTime: '2025-07-01', url: '/media/img1.jpg' }
  ]
  videoMediaList.value = [
    { fileName: `${row.name}_视频1.mp4`, filePath: '/media/video1.mp4', model: '型号B', createTime: '2025-07-02', url: '/media/video1.mp4' }
  ]
}

const handleTabChange = (tab) => {
  console.log('切换媒体类型：', tab)
}

const handleDownload = (row) => {
  const link = document.createElement('a')
  link.href = row.url
  link.download = row.fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const deleteTask = (row) => {
  allData.value = allData.value.filter(item => item.id !== row.id)
  ElMessage.success('任务已删除')
}
</script>

<style scoped>
.type-item {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.type-item .el-icon {
  color: #67c23a;
  font-size: 16px;
  margin-left: 8px;
}

::v-deep(.el-table .el-table__row) {
  height: auto;
}
::v-deep(.el-table .el-table__header-wrapper th) {
  height: 30px;
  line-height: 50px;
}
::v-deep(.el-table .cell) {
  line-height: 24px;
}
</style>