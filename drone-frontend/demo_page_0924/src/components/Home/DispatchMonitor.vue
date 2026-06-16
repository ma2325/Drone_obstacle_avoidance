<template>
  <el-dialog
    title="调度监控"
    :visible.sync="visible"
    width="600px"
    :before-close="handleClose"
    center
  >
    <div class="content">
      <p><strong>设备ID：</strong> {{ device?.id }}</p>
      <p><strong>设备名称：</strong> {{ device?.name }}</p>
      <p><strong>当前状态：</strong> {{ device?.status }}</p>
      <p><strong>电量：</strong> {{ device?.battery }}%</p>

      <el-alert
        v-if="device?.status === '工作中'"
        title="该设备正在执行任务"
        type="warning"
        show-icon
        class="mb-3"
      />
      <el-alert
        v-if="device?.status === '待命'"
        title="设备待命，可执行调度"
        type="success"
        show-icon
        class="mb-3"
      />

      <!-- 这里你可以添加更多调度监控相关内容 -->

      <div class="dialog-footer" style="text-align: right; margin-top: 20px;">
        <el-button @click="handleClose">关闭</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script>
export default {
  name: 'DispatchMonitor',
  props: {
    device: {
      type: Object,
      required: true,
    },
  },
  data() {
    return {
      visible: true,
    };
  },
  methods: {
    handleClose() {
      this.visible = false;
      this.$emit('action', { type: 'close-modal' });
    },
  },
};
</script>

<style scoped>
.content {
  font-size: 14px;
}
.mb-3 {
  margin-bottom: 12px;
}
</style>
