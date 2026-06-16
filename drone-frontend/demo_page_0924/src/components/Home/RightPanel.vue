<template>
  <div class="right-panel" :class="{ 'is-collapsed': isCollapsed }">
    <!-- 折叠按钮 -->
    <div class="collapse-btn" @click="togglePanel">
      <div class="collapse-icon" :class="{ 'collapsed': isCollapsed }"></div>
    </div>

    <div class="panel-content-wrapper">
      <!-- 顶部选项卡 -->
      <div class="panel-tabs">
        <div class="tab-item" :class="{ 'active': activeTab === 'device' }" @click="activeTab = 'device'">
          无人机 <span class="count">{{ devices.length }}</span>
        </div>
        <div class="tab-item" :class="{ 'active': activeTab === 'dockers' }" @click="activeTab = 'dockers'">
          机场 <span class="count">{{ dockers.length }}</span>
        </div>
      </div>

      <!-- 搜索框 -->
      <div class="search-box">
        <input v-model="searchText" :placeholder="activeTab === 'device' ? '搜索无人机' : '搜索机场'" class="search-input">
      </div>

      <!-- 无人机列表 -->
      <div v-if="activeTab === 'device'" class="device-list-wrapper">
        <div class="device-list-scroll">
          <div v-for="item in filteredDevices" :key="item.id" class="device-item" :class="{
            online: item.connection === '在线',
            selected: selectedDeviceId === item.id
          }" @click="showDeviceDetail(item)">
            <div class="device-header">
              <div class="device-name">{{ item.name }}</div>
              <div class="connection-status">
                {{ item.connection || '离线' }}
              </div>
            </div>

            <div v-if="item.model" class="device-model">
              {{ item.model }}
              <div class="connection-status priority" :class="getPriorityClass(item.priority)">
                {{ item.priority || '低' }}
              </div>
            </div>



            <div class="device-details">
              <div class="detail-row">
                <span class="detail-label">状态：</span>
                <span class="detail-value">{{ item.status }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">任务：</span>
                <span class="detail-value">{{ item.task || '暂无任务' }}</span>
              </div>
              <div class="detail-row progress-row">
                <span class="detail-label">剩余时间：</span>
                <span class="detail-value">
                  {{ item.remainingTime }}/{{ item.estimatedCompletionTime }}
                </span>
                <div class="progress-circle">
                  <svg viewBox="0 0 36 36">
                    <path class="circle-bg" d="M18 2.0845
           a 15.9155 15.9155 0 0 1 0 31.831
           a 15.9155 15.9155 0 0 1 0 -31.831" />
                    <path class="circle" :stroke-dasharray="getProgress(item) + ', 100'" d="M18 2.0845
           a 15.9155 15.9155 0 0 1 0 31.831
           a 15.9155 15.9155 0 0 1 0 -31.831" />
                    <!-- <text x="18" y="20.35" class="percentage">{{ getProgress(item) }}%</text> -->
                  </svg>
                </div>


              </div>

            </div>

            <div v-if="item.spec" class="device-spec">
              {{ item.spec }}
            </div>
          </div>
        </div>
      </div>

      <!-- 机场列表 -->
      <div v-if="activeTab === 'dockers'" class="device-list-wrapper">
        <div class="device-list-scroll">
          <div v-for="item in filteredDockers" :key="item.id" class="device-item" :class="{
            online: item.status === '空闲',
            selected: selectedDockerId === item.id
          }" @click="showDockerDetail(item)">
            <!-- 标题栏 -->
            <div class="device-header">
              <div class="device-name">{{ item.name }}</div>
              <div class="connection-status">{{ item.status || '未知' }}</div>
            </div>

            <!-- 型号 -->
            <div v-if="item.model" class="device-model">
              {{ item.model }}
            </div>

            <!-- 任务与关联无人机 -->
            <div class="device-details">
              <!-- 任务 -->
              <div class="detail-row">
                <span class="detail-label">任务：</span>
                <span class="detail-value">{{ item.task || '暂无任务' }}</span>
              </div>

              <!-- 关联无人机 -->
              <div class="detail-row" v-if="item.associatedDevices && item.associatedDevices.length">
                <span class="detail-label">关联无人机：</span>
                <span class="detail-value">
                  <span v-for="uavId in item.associatedDevices" :key="uavId" class="linked-device"
                    @click.stop="openUavDetailById(uavId)">
                    {{ getUavNameById(uavId) }}
                  </span>
                </span>
              </div>

            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import dockers from '@/test-data/dockers.json';

const props = defineProps({
  devices: {
    type: Array,
    default: () => []
  }
});

const emit = defineEmits(['action']);

// 选中的设备ID
const selectedDeviceId = ref(null);
const selectedDockerId = ref(null);

// 获取无人机名称
const getUavNameById = (id) => {
  const uav = props.devices?.find?.(d => d.id === id);
  return uav ? uav.name : `无人机${id}`;
};

// 打开无人机详情
const openUavDetailById = (id) => {
  const device = props.devices?.find?.(d => d.id === id);
  if (device) {
    showDeviceDetail(device);
  }
};

// 无人机详情
const showDeviceDetail = (device) => {
  // 更新选中的设备ID
  selectedDeviceId.value = device.id;
  // 清除选中的机场ID
  selectedDockerId.value = null;

  emit('action', { type: 'show-detail', data: device });
};

// 机场详情
const showDockerDetail = (docker) => {
  // 更新选中的机场ID
  selectedDockerId.value = docker.id;
  // 清除选中的设备ID
  selectedDeviceId.value = null;

  emit('action', { type: 'show-docker-detail', data: docker });
};

// 状态控制
const isCollapsed = ref(false);
const togglePanel = () => {
  isCollapsed.value = !isCollapsed.value;
  if (isCollapsed.value) {
    emit('action', { type: 'close-detail' });
  }
};

const activeTab = ref('device');

watch(activeTab, () => {
  selectedDeviceId.value = null;
  selectedDockerId.value = null;
});

const searchText = ref('');

const dockersData = ref(dockers);

const filteredDevices = computed(() => {
  return props.devices.filter(d =>
    d.name?.includes(searchText.value) ||
    d.model?.includes(searchText.value)
  );
});

const filteredDockers = computed(() => {
  return dockersData.value.filter(p =>
    p.name?.includes(searchText.value) ||
    p.status?.includes(searchText.value)
  );
});

const getPriorityClass = (priority) => {
  if (priority === '高') return 'high';
  if (priority === '中') return 'medium';
  return 'low'; // 默认返回低优先级
};

//剩余时间计算
const getProgress = (item) => {
  const remain = parseInt(item.remainingTime);              // 20
  const total = parseInt(item.estimatedCompletionTime);     // 40
  if (!remain || !total) return 0;
  return Math.round(((total - remain) / total) * 100);      // 已完成进度百分比
};



</script>

<style scoped>
.right-panel {
  position: relative;
  width: 280px;
  height: 100%;
  background: rgba(30, 30, 45, 0.6);
  border-left: 1px solid #2A2A3A;
  transition: transform 0.3s ease;
  transform: translateX(0);
  overflow: visible;
  display: flex;
  flex-direction: column;
  color: #E0E0E0;
  font-size: 14px;
}

.right-panel.is-collapsed {
  transform: translateX(calc(100% - 16px));
}

.panel-content-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-tabs {
  display: flex;
  padding: 12px 16px 0;
  border-bottom: 1px solid #2A2A3A;
}

.tab-item {
  padding: 8px 16px;
  cursor: pointer;
  position: relative;
  color: #A0A0C0;
}

.tab-item.active {
  color: #FFFFFF;
  font-weight: 500;
}

.tab-item.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: #4A9FF5;
}

.count {
  background: #3A3F5C;
  color: #FFFFFF;
  border-radius: 10px;
  padding: 0 6px;
  font-size: 0.85em;
  margin-left: 4px;
}

.search-box {
  padding: 12px 16px;
}

.search-input {
  width: 80%;
  background: #2A2A3A;
  border: 1px solid #3A3F5C;
  border-radius: 4px;
  padding: 8px 12px;
  color: #FFFFFF;
  outline: none;
}

.search-input::placeholder {
  color: #6C7493;
}

.device-list-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 5px;
}

.device-list-scroll {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  margin-right: -4px;
   /* 隐藏滚动条但仍然能滚动 */
  scrollbar-width: none;      /* Firefox */
  -ms-overflow-style: none;   /* IE 和 Edge */
}

.device-item {
  padding: 12px;
  margin-bottom: 8px;
  background: #2A2A3A;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3); /* 基础阴影 */
}

/* 鼠标悬停时的立体效果 */
.device-item:hover {
  transform: translateY(-4px); /* 稍微抬起 */
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4); /* 阴影加深 */
}


/* 选中的设备卡片样式 */
.device-item.selected {
  background: #1A1A24;
}

.device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.device-name {
  font-weight: 600;
  color: #FFFFFF;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
}

.connection-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(244, 67, 54, 0.2);
  color: #F44336;
}

.device-item.online .connection-status {
  background: rgba(76, 175, 80, 0.2);
  color: #4CAF50;
}

.device-model {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #A0A0C0;
  font-size: 13px;
}

.connection-status.priority {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.connection-status.priority.high {
  background: rgba(244, 67, 54, 0.2);
  color: #F44336;
}

.connection-status.priority.medium {
  background: rgba(255, 193, 7, 0.2);
  color: #FFC107;
}

.connection-status.priority.low {
  background: rgba(76, 175, 80, 0.2);
  color: #4CAF50;
}



.connection-status.priority {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(244, 67, 54, 0.2);
  color: #F44336;
}

.device-details {
  font-size: 13px;
}

.detail-row {
  display: flex;
  margin-bottom: 4px;
}

.detail-label {
  color: #9090B0;
  margin-right: 8px;
  min-width: 40px;
}

.detail-value {
  color: #FFFFFF;
}

.device-spec {
  color: #A0A0C0;
  font-size: 12px;
  margin-top: 4px;
}

.progress-row {
  align-items: center;
}

.progress-circle {
  width: 24px;
  height: 24px;
  margin-left: 8px;
}

.progress-circle svg {
  width: 100%;
  height: 100%;
}

.circle-bg {
  fill: none;
  stroke: #444a60;
  stroke-width: 5;
}

.circle {
  fill: none;
  stroke-width: 2.8;
  stroke-linecap: round;
  stroke: #4A9FF5;
  transition: stroke-dasharray 0.3s ease;
}

.percentage {
  font-size: 0.35em;
  text-anchor: middle;
  fill: #fff;
}
</style>
