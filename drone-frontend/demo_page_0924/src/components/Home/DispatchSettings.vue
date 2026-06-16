<template>
  <el-form :model="form" label-width="80px">
    <!-- 任务类型 -->
    <el-form-item label="任务类型">
      <el-select v-model="form.taskType" placeholder="请选择任务类型" :teleported="false">
        <el-option label="巡逻" value="巡逻" />
        <el-option label="拍照" value="拍照" />
        <el-option label="视频录制" value="视频录制" />
        <el-option label="搜救" value="搜救" />
        <el-option label="火情侦测" value="火情侦测" />
        <el-option label="环保监测" value="环保监测" />
        <el-option label="运送物资" value="运送物资" />
      </el-select>
    </el-form-item>

    <!-- 起飞点 -->
    <el-form-item label="起飞点">
      <el-radio-group v-model="form.startMode" style="margin-bottom: 8px;">
        <el-radio-button label="current">使用当前位置</el-radio-button>
        <el-radio-button label="manual">地图选点</el-radio-button>
      </el-radio-group>

      <el-input v-if="form.startMode === 'manual'" v-model="form.start" placeholder="地图选点或输入坐标">
        <template #append>
          <el-button @click="$emit('action', { type: 'select-on-map', field: 'start' })">地图选点</el-button>
        </template>
      </el-input>

      <el-input v-else v-model="form.start" :disabled="true" placeholder="自动填入当前位置" />

      <!-- 当前坐标展示 -->
      <!-- <div v-if="currentPosition" style="margin-top: 4px; font-size: 12px; color: #888;">
        当前经度：{{ currentPosition.lng.toFixed(6) }}，纬度：{{ currentPosition.lat.toFixed(6) }}
      </div> -->
    </el-form-item>

    <!-- 目标点 -->
    <el-form-item label="目标点">
      <el-input v-model="form.end" placeholder="地图选点或输入坐标">
        <template #append>
          <el-button @click="$emit('action', { type: 'select-on-map', field: 'end' })">地图选点</el-button>
        </template>
      </el-input>
    </el-form-item>

    <!-- 飞行参数 -->
    <el-form-item label="速度 (m/s)">
      <el-input-number v-model="form.speed" :min="1" :max="20" controls-position="right" />
    </el-form-item>

    <el-form-item label="高度 (m)">
      <el-input-number v-model="form.altitude" :min="10" :max="500" controls-position="right" />
    </el-form-item>

    <!-- 航线导入 -->
    <el-form-item label="航线导入">
      <el-upload class="upload-demo" :show-file-list="false" accept=".json,.csv" :before-upload="handleFileUpload">
        <el-button type="primary">上传航线文件</el-button>
      </el-upload>
      <div v-if="form.waypoints.length" style="margin-top: 6px; font-size: 12px; color: #888;">
        已导入 {{ form.waypoints.length }} 个航点
      </div>
    </el-form-item>

    <!-- 操作按钮 -->
    <div style="text-align: right">
      <el-button @click="$emit('action', { type: 'cancel' })">取消</el-button>
      <el-button type="primary" @click="confirmDispatch">确认调度</el-button>
    </div>
  </el-form>

</template>



<script setup>
import { reactive, watch, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  device: Object
})

const emit = defineEmits(['action'])

const form = reactive({
  taskType: '',
  start: '',
  startMode: 'current',
  end: '',
  speed: 10,
  altitude: 120,
  waypoints: []
})

const currentPosition = ref(null)

// 初始化当前起飞点（设备位置）
const initCurrentPosition = () => {
  const pos = props.device?.position
  if (pos && pos.length >= 2) {
    const [lng, lat] = pos
    form.start = `${lng.toFixed(6)},${lat.toFixed(6)}`
    currentPosition.value = { lng, lat }
  } else {
    form.start = ''
    currentPosition.value = null
  }
}

// 当选择“使用当前位置”时，更新坐标
watch(() => form.startMode, (mode) => {
  if (mode === 'current') {
    initCurrentPosition()
  }
})

// 首次加载也尝试初始化
initCurrentPosition()

// 确认调度
function confirmDispatch() {
  if (!form.taskType) {
    ElMessage.error('请选择任务类型')
    return
  }

  if (form.waypoints.length === 0) {
    if (!form.start || !form.end) {
      ElMessage.error('请填写起点/终点，或上传航线')
      return
    }
  }

  const data = {
    ...form,
    deviceId: props.device?.id
  }
  emit('action', { type: 'confirm-dispatch', data })
}

// 航线文件处理
function handleFileUpload(file) {
  const reader = new FileReader()
  reader.onload = (event) => {
    try {
      const content = event.target.result
      const isJSON = file.name.endsWith('.json')
      form.waypoints = isJSON ? JSON.parse(content) : parseCsv(content)
      ElMessage.success('航线导入成功')
    } catch (e) {
      ElMessage.error('航线文件解析失败')
    }
  }
  reader.readAsText(file)
  return false
}

function parseCsv(content) {
  const lines = content.trim().split('\n')
  return lines.map(line => {
    const [lat, lon, alt] = line.split(',').map(Number)
    return { lat, lon, alt }
  })
}
</script>
