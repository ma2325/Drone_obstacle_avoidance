<template>
  <div style="padding: 20px;">
    <h2>任务完成情况</h2>
    <!-- 搜索栏 -->
    <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务ID</label>
      <el-input v-model="filters.id" placeholder="请输入任务ID" style="width: 200px;" @input="filterData" />
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">任务类型</label>
      <el-select v-model="filters.taskType" placeholder="请选择任务类型" style="width: 200px;" @change="filterData">
        <el-option label="全部" value="" />
        <el-option label="区域扫描" value="区域扫描" />
        <el-option label="点位扫描" value="点位扫描" />
      </el-select>
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">巡检类型</label>
      <el-select v-model="filters.type" placeholder="请选择巡检类型" style="width: 200px;" multiple @change="filterData">
        <el-option label="全部" value="" />
        <el-option v-for="type in allInspectionTypes" :key="type" :label="type" :value="type" />
      </el-select>
      <el-button @click="resetFilters">重置</el-button>
    </div>
    <!-- 任务执行情况表格 -->
    <el-table :data="filteredExecutionData" stripe border :fit="true" style="width: 100%; margin-top: 20px;">
      <el-table-column label="任务ID" prop="id" width="120" />
      <el-table-column label="任务类型" prop="taskType" width="120" />
      <el-table-column label="巡检类型" prop="type" width="130">
        <template #default="{ row }">
          <div v-for="(type, index) in row.type" :key="index" style="display: flex; align-items: center; margin-bottom: 4px;">
            <span style="margin-right: 8px;">{{ type }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="航线编号" prop="route_id" width="120" />
      <el-table-column label="航线里程" prop="route" width="150" />
      <el-table-column label="起飞点" prop="takeoff" width="120" />
      <el-table-column label="折返点设置" prop="turnaround" width="150" />
      <el-table-column label="时间窗" prop="time_window" width="120">
        <template #default="{ row }">
          {{ row.time_window ? row.time_window.join('-') : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="飞行趟数" prop="flightCount" width="90">
        <template #default="{ row }">
          {{ row.flightCount || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="执勤无人机" prop="drone" width="130">
        <template #default="{ row }">
          {{ row.drone || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="优先级" prop="priority" width="100">
        <template #default="{ row }">
          {{ row.priority || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="执行状态" prop="status" width="150">
        <template #default="{ row }">
          {{ row.status || '待执行' }}
        </template>
      </el-table-column>
      <el-table-column label="执行时间" prop="executionTime" width="150">
        <template #default="{ row }">
          {{ row.executionTime || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="异常记录" prop="exceptionRecord" width="150">
        <template #default="{ row }">
          {{ row.exceptionRecord || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="识别结果数量" prop="recognitionCount" width="150">
        <template #default="{ row }">
          {{ row.recognitionCount || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="精度指标" prop="accuracyMetric" width="120">
        <template #default="{ row }">
          {{ row.accuracyMetric || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="时间窗符合率" prop="timeWindowCompliance" width="150">
        <template #default="{ row }">
          {{ row.timeWindowCompliance || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="完成率" prop="completionRate" width="120">
        <template #default="{ row }">
          {{ row.completionRate || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="飞行日志（时长/趟数/里程）" prop="flightLog" width="200">
        <template #default="{ row }">
          {{ row.flightLog || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="电池使用次数" prop="batteryUsageCount" width="150">
        <template #default="{ row }">
          {{ row.batteryUsageCount || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="设备健康度" prop="deviceHealth" width="120">
        <template #default="{ row }">
          {{ row.deviceHealth || '-' }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

// 从路由中获取初始任务数据
const route = useRoute()
const executionData = ref([])

// 解析 query 参数中的任务数据
onMounted(() => {
  if (route.query.tasks) {
    try {
      executionData.value = JSON.parse(route.query.tasks)
      console.log('接收到的任务数据:', executionData.value)
    } catch (error) {
      console.error('解析任务数据失败:', error)
    }
  } else {
    console.warn('未接收到任务数据')
  }
})

// 巡检类型常量，与 AirportTask2 保持一致
const areaTypes = ['抛洒物识别', '团雾检测', '病害识别', '拥堵点检测']
const pointTypes = ['桥梁巡检', '边坡巡检']
const allInspectionTypes = [...areaTypes, ...pointTypes]

// 筛选条件
const filters = ref({
  id: '',
  taskType: '',
  type: []
})

// 过滤数据
const filteredExecutionData = computed(() => {
  let result = executionData.value.map(task => ({
    ...task,
    route_id: task.route_id || '-',
    route: task.route || '-',
    takeoff: task.takeoff || '-',
    turnaround: task.turnaround || '-',
    time_window: task.time_window || null,
    flightCount: task.flightCount || '-',
    drone: task.drone || '-',
    status: task.status || '待执行',
    executionTime: task.executionTime || '-',
    priority: task.priority || '-',
    exceptionRecord: task.exceptionRecord || '-',
    recognitionCount: task.recognitionCount || '-',
    accuracyMetric: task.accuracyMetric || '-',
    timeWindowCompliance: task.timeWindowCompliance || '-',
    completionRate: task.completionRate || '-',
    flightLog: task.flightLog || '-',
    batteryUsageCount: task.batteryUsageCount || '-',
    deviceHealth: task.deviceHealth || '-'
  }))

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

// 重置筛选条件
const resetFilters = () => {
  filters.value = { id: '', taskType: '', type: [] }
}

// 实时过滤
const filterData = () => {
  // 触发 computed 的重新计算
}
</script>

<style scoped>
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