```vue
<template>
  <div style="padding: 20px 10px;">
    <!-- 搜索栏 -->
    <div style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">航线名称</label>
      <el-input v-model="filters.name" placeholder="请输入航线名称" style="width: 200px;" />

      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">航线类型</label>
      <el-select v-model="filters.type" placeholder="请选择航线类型" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option label="航点飞行" value="航点飞行" />
        <el-option label="建图航拍" value="建图航拍" />
        <el-option label="带状航线" value="带状航线" />
        <el-option label="预设航线" value="预设航线" />
      </el-select>

      <label style="font-weight: 600; width: 80px; text-align: right; color: #303133;">设备型号</label>
      <el-select v-model="filters.drone_name" placeholder="请选择设备型号" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option label="Matrice 3TD" value="Matrice 3TD" />
        <el-option label="Mavic 3" value="Mavic 3" />
      </el-select>

      <el-button @click="reset">重置</el-button>
      <el-button type="primary" @click="search">搜索</el-button>
    </div>

    <!-- 创建航线按钮和导入航线按钮放一起 -->
    <div style="margin-bottom: 20px; display: flex; gap: 10px;">
      <el-button type="primary" @click="openTaskDialog">新建任务</el-button>
      <el-upload
        :show-file-list="false"
        accept=".json"
        :before-upload="handleBeforeUpload"
      >
        <el-button type="primary" @click="triggerImport">导入航线</el-button>
      </el-upload>
    </div>

    <!-- 卡片式任务列表 -->
    <div class="task-card-container">
      <!-- 预设航线卡片 -->
      <div class="task-card horizontal-layout" @click="goToMap(presetRoute)">
        <img :src="presetRoute.thumbnailUrl" class="task-thumb-left" alt="航线图" />
        <div class="task-info-right">
          <div class="task-header">
            <div class="task-title">{{ presetRoute.name }}</div>
          </div>
          <div class="task-line">飞机名称：{{ presetRoute.drone_name }}</div>
          <div class="task-line">航线类型：{{ presetRoute.type }}</div>
          <div class="task-line">航线地点：{{ presetRoute.location }}</div>
          <div class="task-line">创建人：{{ presetRoute.creator }}</div>
          <div class="task-line">创建时间：{{ presetRoute.startTime }}</div>
          <div class="task-line">
            同步云端：
            <span :style="{ color: presetRoute.cloud === '已同步' ? 'green' : 'red', fontWeight: 600 }">
              {{ presetRoute.cloud }}
            </span>
          </div>
          <div class="task-actions-right">
            <el-button size="small" @click.stop="openMediaDrawer(presetRoute)">媒体</el-button>
            <el-button size="small" @click.stop="deleteTask(presetRoute)">删除</el-button>
          </div>
        </div>
      </div>
      <!-- 其他动态任务卡片 -->
      <div v-for="(item, index) in pagedData" :key="index" class="task-card horizontal-layout" @click="goToMap(item)">
        <img :src="getThumbnail(item)" class="task-thumb-left" alt="航线图" />
        <div class="task-info-right">
          <div class="task-header">
            <div class="task-title">{{ item.name }}</div>
          </div>
          <div class="task-line">飞机名称：{{ item.drone_name }}</div>
          <div class="task-line">航线类型：{{ item.type }}</div>
          <div class="task-line">航线地点：{{ item.location }}</div>
          <div class="task-line">创建人：{{ item.creator }}</div>
          <div class="task-line">创建时间：{{ item.startTime }}</div>
          <div class="task-line">
            同步云端：
            <span :style="{ color: item.cloud === '已同步' ? 'green' : 'red', fontWeight: 600 }">
              {{ item.cloud }}
            </span>
          </div>
          <div class="task-actions-right">
            <el-button size="small" @click.stop="openMediaDrawer(item)">媒体</el-button>
            <el-button size="small" @click.stop="deleteTask(item)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

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

    <!-- 创建航线弹窗 -->
    <el-dialog v-model="taskDialogVisible" title="创建新航线" width="500px" class="custom-dialog">
      <div class="dialog-content">
        <div class="section">
          <h3 class="section-title">航线类型</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.routeType" class="radio-group square-button">
              <el-radio-button :value="'航点飞行'">
                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M665.6 204.8v122.88c0 10.24 15.36 15.36 20.48 10.24L901.12 102.4c10.24-10.24 0-20.48-10.24-20.48l-322.56 20.48c-10.24 0-15.36 15.36-5.12 20.48L665.6 204.8z" />
                    <path d="M931.84 588.8c-5.12-20.48-20.48-35.84-40.96-40.96L256 465.92c-5.12 0-10.24-10.24 0-10.24l312.32-158.72c15.36-5.12 20.48-20.48 20.48-35.84 0-10.24-5.12-20.48-15.36-30.72-10.24-10.24-25.6-10.24-40.96-5.12L117.76 435.2c-20.48 10.24-30.72 30.72-25.6 51.2 5.12 20.48 20.48 35.84 40.96 40.96l640 81.92c5.12 0 10.24 10.24 0 10.24l-353.28 184.32c-10.24-5.12-25.6-10.24-40.96-10.24-35.84 0-71.68 35.84-71.68 76.8s35.84 76.8 76.8 76.8S460.8 916.48 460.8 875.52l445.44-235.52c20.48-10.24 30.72-30.72 25.6-51.2z" />
                  </svg>
                  <span>航点飞行</span>
                </div>
              </el-radio-button>
              <el-radio-button :value="'建图航拍'">
                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M238.047 879.766l-87.517-144.62 18.032-10.932 87.517 144.619z m87.259 5.182L148.976 544.98l18.86-9.793L345.463 877.64z m97.415 0L149.908 357.25l18.861-9.794 274.626 531.428z m99.383 0L149.908 147.239l20.986-5.181 371.315 735.79z m89.694-5.182L237.633 155.012l18.861-9.793L630.659 869.92z m113.996 0L326.705 155.271l18.55-10.363L744.241 869.61z m123.582 0L444.794 155.271l18.55-10.363 404.79 724.702z m5.855-193.482l-304.42-530.858 18.394-10.363 304.42 530.858z m0-203.845l-193.275-326.96 18.24-10.779 193.326 326.91z m-1.088-190.114l-88.917-136.432 17.721-11.607 88.969 136.432z" />
                    <path d="M874.973 884.896H148.716V139.519h726.257v745.377zM200.429 833.08H823.26V191.23H203.175z" />
                    <path d="M833.209 842.925V992h149.075V842.925zM940.054 949.77H875.44v-64.615h64.667zM833.21 32v149.075h149.075V32z m106.845 106.845H875.44V74.23h64.667zM41.716 842.925V992H190.79V842.925zM148.56 949.77H83.946v-64.615h64.615zM41.716 32v149.075H190.79V32zM148.56 138.845H83.946V74.23h64.615z" />
                  </svg>
                  <span>建图航拍</span>
                </div>
              </el-radio-button>
              <el-radio-button :value="'带状航线'">
                <div style="display: flex; flex-direction: column; align-items: center; gap: 6px;">
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M466.274462 1024l-47.458462-44.032q12.288-13.312 31.074462-34.146462l49.467076 42.338462q-21.504 22.173538-33.083076 35.84zM564.893538 905.885538L512 866.304a1783.099077 1783.099077 0 0 0 59.076923-81.250462l53.563077 36.194462c-17.053538 27.648-37.888 55.965538-59.746462 84.676923z m117.76-174.08l-56.635076-31.744c16.384-28.396308 30.759385-57.934769 43.008-88.379076l60.061538 24.221538a838.498462 838.498462 0 0 1-46.434462 95.901538z m77.154462-199.68l-63.488-12.957538c6.340923-30.444308 9.688615-61.44 9.885538-92.514462l64.512-3.387076v3.387076a519.876923 519.876923 0 0 1-11.933538 105.472h1.024z m-67.584-200.704a294.203077 294.203077 0 0 0-38.596923-83.259076l53.956923-36.194462c20.873846 31.507692 36.745846 66.048 47.104 102.4l-62.464 17.053538zM590.848 180.578462a190.109538 190.109538 0 0 0-34.146462-22.882462l28.002462-58.368c16.541538 8.428308 32.216615 18.510769 46.749538 30.050462l-40.605538 51.2zM39.266462 1024L0 972.406154c3.741538-2.756923 360.763077-276.795077 450.56-531.101539a218.781538 218.781538 0 0 0-5.12-176.836923c-49.152-94.168615-170.653538-130.008615-170.653538-130.363077l18.077538-62.109538c5.789538 1.693538 147.101538 43.008 209.565538 162.107077A281.6 281.6 0 0 1 512 462.493538C415.389538 735.232 54.626462 1012.381538 39.266462 1024z" />
                    <path d="M831.803077 1024l-45.016615-46.749538 22.528 23.552-22.528-23.552c1.693538-1.732923 172.347077-170.692923 172.347076-475.490462 0-296.96-346.781538-440.32-350.523076-441.698462L633.186462 0C648.546462 6.498462 1024 162.461538 1024 501.76S839.68 1016.516923 831.803077 1024z" />
                  </svg>
                  <span>带状航线</span>
                </div>
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">选择飞行器</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.droneSeries" class="radio-group">
              <el-radio-button :value="'经纬M30系列'" >经纬M30系列</el-radio-button>
              <el-radio-button :value="'Mavic 3 行业系列'" >Mavic 3 行业系列</el-radio-button>
              <el-radio-button :value="'Matrice 3D系列'" >Matrice 3D系列</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">选择型号</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.droneModel" class="radio-group">
              <el-radio-button :value="'Matrice 30'" >Matrice 30</el-radio-button>
              <el-radio-button :value="'Matrice 30T'" >Matrice 30T</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">航线名称</h3>
          <el-input v-model="newTask.name" placeholder="请输入航线名称" />
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="taskDialogVisible = false" class="cancel-btn">取消</el-button>
          <el-button type="primary" @click="submitTask" class="confirm-btn">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import taskData from '@/assets/taskData_line.json';
import { useRouter } from 'vue-router';

// 预设航线数据
const presetRoute = ref({
  id: 'preset-waypoint-flight1',
  name: '预设航线1',
  drone_name: 'Matrice 3TD',
  type: '预设航线',
  location: '北京市',
  creator: '系统预设',
  startTime: '2025-08-29 10:00:00',
  cloud: '已同步',
  thumbnailUrl: '/media/thumbnails/waypoint_flight1.jpg',
  routeData: '/media/thumbnails/waypoint_flight1.json', // 预设航线路径文件的相对路径
});

const router = useRouter();

const goToMap = (item) => {
  console.log('跳转到地图页面，任务ID:', item.id, '航线类型:', item.type);
  router.push({
    name: 'MapView',
    params: {
      type: item.type,
      taskId: item.id,
      routeData: item.type === '预设航线' ? item.routeData : undefined, // 传递预设航线路径
    },
  });
};

const allData = ref(taskData);
const filters = ref({ name: '', date: null, type: '', drone_name: '' });
const currentPage = ref(1);
const pageSize = ref(10);

const filteredData = computed(() => {
  let result = allData.value;
  if (filters.value.name) {
    result = result.filter(item => item.name.includes(filters.value.name));
  }
  if (filters.value.type) {
    result = result.filter(item => item.type === filters.value.type);
  }
  if (filters.value.drone_name) {
    result = result.filter(item => item.drone_name === item.drone_name);
  }
  return result;
});

const pagedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredData.value.slice(start, start + pageSize.value);
});

const search = () => {
  currentPage.value = 1;
};

const reset = () => {
  filters.value = { name: '', date: null, type: '', drone_name: '' };
  currentPage.value = 1;
};

const handlePageChange = val => {
  currentPage.value = val;
};

const handlePageSizeChange = val => {
  pageSize.value = val;
  currentPage.value = 1;
};

const taskDialogVisible = ref(false);
const newTask = ref({
  name: '',
  routeType: '航点飞行',
  droneSeries: '经纬M30系列',
  droneModel: 'Matrice 30',
  type: '航点飞行',
  id: '',
});

watch(() => newTask.value.routeType, val => {
  newTask.value.type = val;
});

watch(() => newTask.value.droneSeries, series => {
  switch (series) {
    case '经纬M30系列':
      newTask.value.droneModel = 'Matrice 30';
      break;
    case 'Mavic 3 行业系列':
      newTask.value.droneModel = 'Mavic 3';
      break;
    case 'Matrice 3D系列':
      newTask.value.droneModel = 'Matrice 3TD';
      break;
    default:
      newTask.value.droneModel = '';
  }
});

const openTaskDialog = () => {
  taskDialogVisible.value = true;
};

const submitTask = () => {
  const now = new Date();
  const format = d => d.toISOString().slice(0, 19).replace('T', ' ');
  const timeStr = format(now);
  const task = {
    ...newTask.value,
    id: `task-${Date.now()}`,
    planStartTime: timeStr,
    planEndTime: timeStr,
    startTime: timeStr,
    endTime: timeStr,
    status: '完成',
    creator: 'adminPC',
    media: '待上传(1/2)',
  };
  allData.value.unshift(task);
  taskDialogVisible.value = false;
  ElMessage.success('任务创建成功');
};

const deleteTask = row => {
  allData.value = allData.value.filter(item => item !== row);
  const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}');
  delete savedRoutes[row.id];
  localStorage.setItem('savedRoutes', JSON.stringify(savedRoutes));
  ElMessage.success('任务已删除');
};

const openMediaDrawer = item => {
  console.log('打开媒体抽屉:', item);
};

const getThumbnail = item => {
  return item.thumbnailUrl || '/media/thumbnails/default.png';
};

const triggerImport = () => {
  console.log('触发导入航线');
};

const handleBeforeUpload = file => {
  const reader = new FileReader();
  reader.onload = event => {
    try {
      const text = event.target.result;
      const json = JSON.parse(text);
      const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}');
      if (Array.isArray(json)) {
        json.forEach(task => {
          task.id = `task-${Date.now()}-${Math.random().toString(36).slice(2)}`;
          allData.value.unshift(task);
          if (task.routeData) {
            savedRoutes[task.id] = task.routeData;
          }
        });
      } else if (typeof json === 'object') {
        json.id = `task-${Date.now()}`;
        allData.value.unshift(json);
        if (json.routeData) {
          savedRoutes[json.id] = json.routeData;
        }
      } else {
        ElMessage.error('文件格式不正确，请上传有效的航线JSON文件');
        return;
      }
      localStorage.setItem('savedRoutes', JSON.stringify(savedRoutes));
      ElMessage.success('导入成功');
    } catch (err) {
      ElMessage.error('解析文件失败，请检查文件内容');
    }
  };
  reader.readAsText(file);
  return false;
};
</script>

<style scoped>
.task-card-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

.task-card {
  display: flex;
  flex-direction: row;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
}

.task-thumb-left {
  height: 200px;
  width: auto;
  max-width: 200px;
  object-fit: contain;
  border-right: 1px solid #e0e0e0;
  flex-shrink: 0;
}

.task-info-right {
  flex: 1;
  padding: 10px 16px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 14px;
  margin-bottom: 4px;
}

.task-line {
  margin: 2px 0;
}

.task-actions-right {
  margin-top: 8px;
  display: flex;
  gap: 12px;
}

:deep(.el-dialog) {
  background-color: #1f1f1f !important;
  color: #ffffff !important;
  border-radius: 8px !important;
}

:deep(.el-dialog__header) {
  padding: 16px 20px;
  border-bottom: 1px solid #444;
  margin-right: 0;
  background-color: #1f1f1f;
}

:deep(.el-dialog__title) {
  font-size: 16px;
  font-weight: 600;
  color: #ffffff !important;
}

.dialog-content {
  padding: 20px;
  background-color: #1f1f1f;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 14px;
  color: #f0f0f0;
  margin-bottom: 12px;
  font-weight: 600;
}

.option-group {
  margin-left: 8px;
}

.radio-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.square-button :deep(.el-radio-button__inner) {
  width: 130px;
  height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  font-size: 14px;
  font-weight: 600;
  text-align: center;
}

:deep(.square-button svg) {
  fill: currentColor;
  color: inherit;
}

:deep(.el-dialog) .el-input__inner,
:deep(.el-dialog) .el-select .el-input__inner,
:deep(.el-dialog) .el-input-number .el-input__inner {
  background-color: #363948 !important;
  color: #ffffff !important;
  border-color: #444444ba !important;
}

.dialog-footer {
  background-color: #1f1f1f;
  border-top: 1px solid #444444ba;
  display: flex;
  justify-content: flex-end;
  padding: 12px 20px;
}

.cancel-btn,
.confirm-btn {
  padding: 8px 20px;
  border-radius: 4px;
}

.cancel-btn {
  margin-right: 12px;
}

:deep(.el-overlay) {
  background-color: rgba(0, 0, 0, 0.5) !important;
}

:deep(.el-dialog) .el-radio-button__inner {
  border-radius: 5px !important;
  background-color: #9eb0ff2f;
  color: #ffffff;
  border-color: #444444ba;
  transition: all 0.2s;
}

:deep(.el-dialog) .el-radio-button__inner:hover {
  border-color: #409EFF;
  color: #409EFF;
}

:deep(.el-dialog) .el-radio-button.is-active .el-radio-button__inner {
  background-color: #409EFF;
  border-color: #409EFF;
  color: #ffffff;
}

.radio-group :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background-color: rgba(64, 158, 255, 0.6) !important;
  border-color: rgba(64, 158, 255, 0.6) !important;
  color: #ffffff !important;
}
</style>
```