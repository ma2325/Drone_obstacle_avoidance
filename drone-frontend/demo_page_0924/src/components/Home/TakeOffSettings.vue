<template>
  <el-form :model="form" label-width="80px">
    <el-form-item label="任务名称">
      <el-input v-model="form.missionName" placeholder="请输入任务名称" />
    </el-form-item>

    <el-form-item label="起飞位置">
      <el-input v-model="form.position" placeholder="地图选点">
        <template #append>
          <el-button @click="$emit('action', { type: 'select-on-map', field: 'position' })">地图选点</el-button>
        </template>
      </el-input>
    </el-form-item>

    <el-alert type="info" :closable="false" title="无人机状态">
      <p>当前电量：{{ device?.battery || '--' }}%</p>
      <p>状态：{{ device?.status || '--' }}</p>
    </el-alert>

    <div style="text-align: right; margin-top: 10px;">
      <el-button @click="$emit('action', { type: 'cancel' })">取消</el-button>
      <el-button type="primary" @click="confirmTakeOff">确认起飞</el-button>
    </div>
  </el-form>
</template>

<script setup>
import { reactive } from 'vue'

const props = defineProps({ device: Object })
const emit = defineEmits(['action'])

const form = reactive({
  missionName: '',
  position: ''
})

function confirmTakeOff() {
  if (!form.missionName || !form.position) {
    ElMessage.warning('请填写任务名称和位置')
    return
  }
  const data = {
    deviceId: props.device?.id,
    name: form.missionName,
    latitude: 0, // 可由地图点击传入
    longitude: 0,
    ...form
  }
  emit('action', { type: 'confirm-takeoff', data })
}
</script>
