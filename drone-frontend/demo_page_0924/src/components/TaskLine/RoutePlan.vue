<!-- src/components/TaskLine/RoutePlan.vue -->
<template>
  <div style="padding: 20px 10px;">
    <!-- 搜索栏（卡片/列表共用同一数据源） -->
    <div style="margin-bottom: 12px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
      <label class="f-label">航线名称</label>
      <el-input v-model="filters.name" placeholder="请输入航线名称" style="width: 200px;" />

      <label class="f-label">航线类型</label>
      <el-select v-model="filters.type" placeholder="请选择航线类型" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option label="航点飞行" value="航点飞行" />
        <el-option label="建图航拍" value="建图航拍" />
        <el-option label="预设航线" value="预设航线" />
      </el-select>

      <label class="f-label">设备型号</label>
      <el-select v-model="filters.drone_name" placeholder="请选择设备型号" style="width: 200px;">
        <el-option label="全部" value="" />
        <el-option label="Matrice 3TD" value="Matrice 3TD" />
        <el-option label="Mavic 3" value="Mavic 3" />
      </el-select>

      <el-button @click="reset">重置</el-button>
      <el-button type="primary" @click="search">搜索</el-button>

      <!-- 视图切换：卡片 / 列表 -->
      <div style="margin-left: auto; display: flex; align-items: center; gap: 8px;">
        <span style="color:#606266;">视图：</span>
        <el-radio-group v-model="viewMode" size="small">
          <el-radio-button label="card">卡片</el-radio-button>
          <el-radio-button label="table">列表</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 创建与导入 -->
    <div style="margin-bottom: 16px; display: flex; gap: 10px;">
      <el-button type="success" @click="openTaskDialog">新建任务</el-button>
      <el-upload :show-file-list="false" accept=".json" :before-upload="handleBeforeUpload">
        <el-button type="primary">导入航线</el-button>
      </el-upload>
    </div>

    <!-- === 卡片模式（与列表共用 combinedPaged） === -->
    <div v-if="viewMode === 'card'" class="task-card-container">
      <div
        v-for="item in combinedPaged"
        :key="item.id"
        class="task-card horizontal-layout"
        @click="goToMap(item)"
      >
        <img :src="getThumbnail(item)" class="task-thumb-left" alt="航线图" />
        <div class="task-info-right">
          <div class="task-header">
            <div class="task-title">{{ item.name }}</div>
          </div>

          <div class="task-line">航线类型：{{ displayType(item.type) }}</div>
          <div class="task-line">起始站点：{{ item.startStation || '-' }}</div>
          <div class="task-line">创建人：{{ item.creator }}</div>
          <div class="task-line">创建时间：{{ item.startTime }}</div>
          <div class="task-line">
            同步云端：
            <span :style="{ color: item.cloud === '已同步' ? 'green' : 'red', fontWeight: 600 }">
              {{ item.cloud }}
            </span>
          </div>
          <div class="task-actions-right">
            <el-button size="small" type="primary" @click.stop="editTask(item)">修改</el-button>
            <el-button size="small" type="danger" @click.stop="deleteTask(item)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页（卡片模式） -->
    <div v-if="viewMode === 'card'" style="margin-top: 16px; display: flex; justify-content: flex-end;">
      <el-pagination
        :total="combinedFiltered.length"
        :page-size="pageSize"
        :current-page="currentPage"
        :page-sizes="[5, 10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handlePageSizeChange"
      />
    </div>

    <!-- === 列表模式（与卡片共用 combinedPaged） === -->
    <div v-else>
      <el-card shadow="never" class="table-card">
        <div class="table-title">航线列表</div>
        <el-table :data="combinedPaged" border size="small" @row-dblclick="goToMap">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="id" label="任务ID" width="180" />
          <el-table-column prop="name" label="任务名称" min-width="180" />
          <el-table-column label="任务类型" width="120">
            <template #default="{ row }">{{ displayType(row.type) }}</template>
          </el-table-column>
          <el-table-column prop="startStation" label="起始站点" width="160" />
          <el-table-column prop="creator" label="创建人" width="100" />
          <el-table-column prop="startTime" label="创建时间" width="140" />
          <el-table-column label="同步云端" width="120">
            <template #default="{ row }">
              <span :style="{ color: row.cloud === '已同步' ? 'green' : 'red', fontWeight: 600 }">{{ row.cloud }}</span>
            </template>
          </el-table-column>

          <!-- 与 AirportTask2 对齐的字段名 -->
          <el-table-column prop="route_id" label="航线编号" width="120" />
          <el-table-column prop="time_window" label="时间窗" width="140">
            <template #default="{ row }">{{ Array.isArray(row.time_window) ? row.time_window.join('-') : (row.time_window || '-') }}</template>
          </el-table-column>
          <el-table-column prop="flightCount" label="飞行趟数" width="100">
            <template #default="{ row }">{{ row.flightCount ?? '-' }}</template>
          </el-table-column>
          <el-table-column prop="executionTimeDisplay" label="任务执行时间" width="160">
            <template #default="{ row }">{{ row.executionTimeDisplay || '-' }}</template>
          </el-table-column>
          <el-table-column prop="expectedFinish" label="预计执行完成时间(h)" width="180">
            <template #default="{ row }">{{ row.expectedFinish ?? '-' }}</template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small "type="primary" @click.stop="editTask(row)">修改</el-button>
              <el-button size="small" type="danger" @click.stop="deleteTask(row)">删除</el-button>
            </template>
          </el-table-column>
          <el-table-column label="航线" width="120" fixed="right">
            <template #default="{ row }">
              <el-link type="primary" @click="goToMap(row)">查看航线</el-link>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页（列表模式） -->
        <div style="margin-top: 12px; display: flex; justify-content: flex-end;">
          <el-pagination
            :total="combinedFiltered.length"
            :page-size="pageSize"
            :current-page="currentPage"
            :page-sizes="[5, 10, 20, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </el-card>
    </div>

    <!-- 新建任务弹窗 -->
    <el-dialog v-model="taskDialogVisible" title="创建新航线" width="500px" class="custom-dialog">
      <div class="dialog-content">
        <!-- 航线类型 -->
        <div class="section">
          <h3 class="section-title">航线类型</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.routeType" class="radio-group square-button">
              <el-radio-button :value="'航点飞行'">
                <div class="icon-radio">
                  <!-- 图标：航点飞行 -->
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M665.6 204.8v122.88c0 10.24 15.36 15.36 20.48 10.24L901.12 102.4c10.24-10.24 0-20.48-10.24-20.48l-322.56 20.48c-10.24 0-15.36 15.36-5.12 20.48L665.6 204.8z" />
                    <path d="M931.84 588.8c-5.12-20.48-20.48-35.84-40.96-40.96L256 465.92c-5.12 0-10.24-10.24 0-10.24l312.32-158.72c15.36-5.12 20.48-20.48 20.48-35.84 0-10.24-5.12-20.48-15.36-30.72-10.24-10.24-25.6-10.24-40.96-5.12L117.76 435.2c-20.48 10.24-30.72 30.72-25.6 51.2 5.12 20.48 20.48 35.84 40.96 40.96l640 81.92c5.12 0 10.24 10.24 0 10.24l-353.28 184.32c-10.24-5.12-25.6-10.24-40.96-10.24-35.84 0-71.68 35.84-71.68 76.8s35.84 76.8 76.8 76.8S460.8 916.48 460.8 875.52l445.44-235.52c20.48-10.24 30.72-30.72 25.6-51.2z" />
                  </svg>
                  <span>航点飞行</span>
                </div>
              </el-radio-button>

              <el-radio-button :value="'建图航拍'">
                <div class="icon-radio">
                  <!-- 图标：建图航拍 -->
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M238.047 879.766l-87.517-144.62 18.032-10.932 87.517 144.619z m87.259 5.182L148.976 544.98l18.86-9.793L345.463 877.64z m97.415 0L149.908 357.25l18.861-9.794 274.626 531.428z m99.383 0L149.908 147.239l20.986-5.181 371.315 735.79z m89.694-5.182L237.633 155.012l18.861-9.793L630.659 869.92z m113.996 0L326.705 155.271l18.55-10.363L744.241 869.61z m123.582 0L444.794 155.271l18.55-10.363 404.79 724.702z m5.855-193.482l-304.42-530.858 18.394-10.363 304.42 530.858z m0-203.845l-193.275-326.96 18.24-10.779 193.326 326.91z m-1.088-190.114l-88.917-136.432 17.721-11.607 88.969 136.432z" />
                    <path d="M874.973 884.896H148.716V139.519h726.257v745.377zM200.429 833.08H823.26V191.23H203.175z" />
                    <path d="M833.209 842.925V992h149.075V842.925zM940.054 949.77H875.44v-64.615h64.667zM833.21 32v149.075h149.075V32z m106.845 106.845H875.44V74.23h64.667zM41.716 842.925V992H190.79V842.925zM148.56 949.77H83.946v-64.615h64.615zM41.716 32v149.075H190.79V32zM148.56 138.845H83.946V74.23h64.615z" />
                  </svg>
                  <span>建图航拍</span>
                </div>
              </el-radio-button>

              <el-radio-button :value="'预设航线'">
                <div class="icon-radio">
                  <!-- 图标：预设航线 -->
                  <svg viewBox="0 0 1024 1024" width="28" height="28" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
                    <path d="M466.274462 1024l-47.458462-44.032q12.288-13.312 31.074462-34.146462l49.467076 42.338462q-21.504 22.173538-33.083076 35.84zM564.893538 905.885538L512 866.304a1783.099077 1783.099077 0 0 0 59.076923-81.250462l53.563077 36.194462c-17.053538 27.648-37.888 55.965538-59.746462 84.676923z m117.76-174.08l-56.635076-31.744c16.384-28.396308 30.759385-57.934769 43.008-88.379076l60.061538 24.221538a838.498462 838.498462 0 0 1-46.434462 95.901538z m77.154462-199.68l-63.488-12.957538c6.340923-30.444308 9.688615-61.44 9.885538-92.514462l64.512-3.387076v3.387076a519.876923 519.876923 0 0 1-11.933538 105.472h1.024z m-67.584-200.704a294.203077 294.203077 0 0 0-38.596923-83.259076l53.956923-36.194462c20.873846 31.507692 36.745846 66.048 47.104 102.4l-62.464 17.053538zM590.848 180.578462a190.109538 190.109538 0 0 0-34.146462-22.882462l28.002462-58.368c16.541538 8.428308 32.216615 18.510769 46.749538 30.050462l-40.605538 51.2zM39.266462 1024L0 972.406154c3.741538-2.756923 360.763077-276.795077 450.56-531.101539a218.781538 218.781538 0 0 0-5.12-176.836923c-49.152-94.168615-170.653538-130.008615-170.653538-130.363077l18.077538-62.109538c5.789538 1.693538 147.101538 43.008 209.565538 162.107077A281.6 281.6 0 0 1 512 462.493538C415.389538 735.232 54.626462 1012.381538 39.266462 1024z" />
                    <path d="M831.803077 1024l-45.016615-46.749538 22.528 23.552-22.528-23.552c1.693538-1.732923 172.347077-170.692923 172.347076-475.490462 0-296.96-346.781538-440.32-350.523076-441.698462L633.186462 0C648.546462 6.498462 1024 162.461538 1024 501.76S839.68 1016.516923 831.803077 1024z" />
                  </svg>
                  <span>预设航线</span>
                </div>
              </el-radio-button>
            </el-radio-group>

            <!-- 选择 预设航线 下拉 -->
            <div v-if="newTask.routeType === '预设航线'" class="section">
              <h3 class="section-title">选择预设航线</h3>
              <el-select v-model="newTask.presetKey" placeholder="请选择预设航线" style="width: 100%;">
                <el-option
                  v-for="opt in presetOptions"
                  :key="opt.key"
                  :label="opt.name"
                  :value="opt.key">
                  <div style="display:flex;align-items:center;gap:8px;">
                    <img :src="opt.thumb" style="width:32px;height:24px;object-fit:cover;border-radius:2px;" />
                    <span>{{ opt.name }}</span>
                  </div>
                </el-option>
              </el-select>
            </div>

            <!-- 航点飞行 打点（进入 MapView 草稿模式） -->
            <div v-if="newTask.routeType === '航点飞行'" class="section">
              <h3 class="section-title">航线规划</h3>
              <div style="display:flex; gap:10px; align-items:center;">
                <el-button @click="openWaypointDraft">编辑航线（打点）</el-button>
                <span v-if="newTask.waypointsDraft" style="color:#67C23A;">已设置 {{ newTask.waypointsDraft?.length || 0 }} 个航点</span>
              </div>
            </div>

          </div>
        </div>

        <!-- 选择飞行器 -->
        <div class="section">
          <h3 class="section-title">选择飞行器</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.droneSeries" class="radio-group">
              <el-radio-button :value="'经纬M30系列'">经纬M30系列</el-radio-button>
              <el-radio-button :value="'Mavic 3 行业系列'">Mavic 3 行业系列</el-radio-button>
              <el-radio-button :value="'Matrice 3D系列'">Matrice 3D系列</el-radio-button>
            </el-radio-group>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">选择型号</h3>
          <div class="option-group">
            <el-radio-group v-model="newTask.droneModel" class="radio-group">
              <el-radio-button :value="'Matrice 30'">Matrice 30</el-radio-button>
              <el-radio-button :value="'Matrice 30T'">Matrice 30T</el-radio-button>
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

    <!-- 媒体抽屉 -->
    <el-drawer v-model="mediaDrawerVisible" title="任务媒体" direction="rtl" size="30%">
      <div v-if="selectedTask && selectedTask.media && selectedTask.media.length > 0">
        <div v-for="(media, index) in selectedTask.media" :key="index" class="media-item">
          <img v-if="media.type === 'image'" :src="media.url" alt="媒体图片" style="width: 100%; height: auto;" />
          <video v-else-if="media.type === 'video'" :src="media.url" controls style="width: 100%; height: auto;"></video>
          <p>{{ media.name }} ({{ media.type }})</p>
        </div>
      </div>
      <div v-else><p>暂无媒体文件</p></div>
    </el-drawer>

    <!-- 编辑任务弹窗（和地图一致；无“折返点”） -->
    <el-dialog v-model="editVisible" title="修改任务" width="560px">
      <el-form :model="editForm" label-width="96px" size="small">
        <el-form-item label="任务ID">
          <el-input v-model="editForm.id" disabled />
        </el-form-item>
        <el-form-item label="任务名称">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-radio-group v-model="editForm.taskType" @change="onTaskTypeChange">
            <el-radio-button v-for="opt in TASK_TYPE_OPTIONS" :key="opt" :label="opt">
              {{ opt }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="航线任务">
          <el-checkbox-group v-model="editForm.taskTags">
            <el-checkbox v-for="tag in availableTaskTags" :key="tag" :label="tag" />
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="起飞点">
          <el-input v-model="editForm.startStation" />
        </el-form-item>
        <el-form-item label="航线编号">
          <el-input v-model="editForm.route_id" />
        </el-form-item>
        <el-form-item label="航线里程">
          <el-input v-model="editForm.mileage" placeholder="如：单程5km" />
        </el-form-item>
        <el-form-item label="时间窗">
          <el-time-picker
            v-model="editForm.timeRange"
            is-range
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="HH:mm"
            value-format="HH:mm"
          />
        </el-form-item>
        <el-form-item label="飞行趟数">
          <el-input-number v-model="editForm.flightCount" :min="1" />
        </el-form-item>
        <el-form-item label="任务执行时间">
          <div style="display:flex;gap:8px;align-items:center;width:100%;">
            <el-select v-model="editForm.executionMode" style="width:140px;">
              <el-option label="立即执行" value="immediate" />
              <el-option label="预约执行" value="schedule" />
            </el-select>
            <el-date-picker
              v-if="editForm.executionMode==='schedule'"
              v-model="editForm.customExecutionTime"
              type="datetime"
              placeholder="选择执行时间"
              style="flex:1;"
              value-format="YYYY-MM-DD HH:mm:ss"
              format="YYYY-MM-DD HH:mm"
            />
          </div>
        </el-form-item>
        <el-form-item label="预计时长(h)">
          <el-input-number v-model="editForm.expectedFinish" :min="0" :step="0.5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="goToMapFromEdit">在地图中编辑</el-button>
          <el-button @click="editVisible=false">取消</el-button>
          <el-button type="primary" @click="saveEdit">确定</el-button>
        </div>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
// 从本地 JSON 文件初始化数据
import taskData from '@/test-data/taskData.json'

/** ===== 任务类型 & 航线任务联动规则（仅编辑弹窗使用） ===== */
const TASK_TYPE_OPTIONS = ['线路扫描', '点位扫描']
const TASK_TAGS_BY_TYPE = {
  '线路扫描': ['抛洒物识别', '团雾识别', '病害识别', '拥堵点检测'],
  '点位扫描': ['桥梁巡检', '边坡巡检']
}

const availableTaskTags = computed(() => TASK_TAGS_BY_TYPE[editForm.value.taskType] || [])


/** ===== 事件 & 存储键（与 MapView/旧面板统一） ===== */
const STORAGE_TASKS = 'inspectionTasks'
const STORAGE_EXEC  = 'executionData'
const EVT_TASKS  = 'tasks-updated'
const EVT_EXEC   = 'execution-updated'
const EVT_REMOVE = 'tasks-removed'
const EVT_DRAFT_SAVED = 'map-draft-saved'
const EVT_ROUTEPLAN = 'routeplan-updated'

/** ===== 轻量事件总线 ===== */
function busOn(name, cb) {
  const h = (e) => cb(e.detail)
  window.addEventListener(name, h)
  return () => window.removeEventListener(name, h)
}
function busEmit(name, detail) {
  window.dispatchEvent(new CustomEvent(name, { detail }))
}

const DEFAULT_CREATOR = 'user'
const DEFAULT_START   = '2025-09-01'
const DEFAULT_CLOUD   = '已同步'
const AUTH_STORAGE_KEY = 'uav-auth-user'

const CREATOR_POOL = [
  '王皓',
  '李薇',
  '陈航',
  '周宁',
  '赵磊',
  '刘洋',
  '孙萌',
  '马骁'
]

function pad2(n) {
  return String(n).padStart(2, '0')
}

function formatDateTime(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

function hashSeed(text = '') {
  let h = 0
  for (let i = 0; i < text.length; i += 1) {
    h = (h * 31 + text.charCodeAt(i)) >>> 0
  }
  return h
}

function buildMetaFallback(item = {}, index = 0) {
  const seed = hashSeed(`${item.id || ''}|${item.name || ''}|${item.takeoff || item.startStation || ''}`) + index * 97
  const creator = CREATOR_POOL[seed % CREATOR_POOL.length]
  const base = new Date('2026-04-13T08:20:00')
  const minuteOffset = (seed % 1800)
  const date = new Date(base.getTime() - minuteOffset * 60000)
  return {
    creator,
    startTime: formatDateTime(date)
  }
}

function normalizeTaskMeta(item = {}, index = 0) {
  const meta = buildMetaFallback(item, index)
  const creatorRaw = String(item.creator || '').trim()
  const startRaw = String(item.startTime || '').trim()
  const creatorPlaceholder = !creatorRaw || ['user', 'admin', 'adminpc'].includes(creatorRaw.toLowerCase())
  const startPlaceholder = !startRaw || startRaw === DEFAULT_START

  return {
    ...item,
    creator: creatorPlaceholder ? meta.creator : creatorRaw,
    startTime: startPlaceholder ? meta.startTime : startRaw
  }
}

function getCurrentOperator() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    const user = raw ? JSON.parse(raw) : null
    const name = String(user?.displayName || user?.username || '').trim()
    return name || '调度员'
  } catch {
    return '调度员'
  }
}

function nowTimeText() {
  return formatDateTime(new Date())
}

/** ===== props / emit ===== */
const props = defineProps({
  presetRoutes: { type: Array, default: () => [] },
  allTasks: { type: Array, default: () => [] },
  prefillId:  { type: String, default: '' },
  prefillMode:{ type: String, default: '' }
})
const emit = defineEmits(['action'])

/** ===== 视图模式 / 过滤 / 分页 ===== */
const viewMode = ref('card') // 'card' | 'table'
const filters = ref({ name: '', type: '', drone_name: '' })
const currentPage = ref(1)
const pageSize = ref(10)

/** ===== 规范化：类型显示 ===== */
const normalizeRouteType = (item) => {
  const hasPresetKey = !!(item?.preset3d || item?.preset3dKey)
  if (hasPresetKey) return '预设航线'
  if (typeof item?.type === 'string') return item.type
  if (typeof item?.routeType === 'string') return item.routeType
  return '航点飞行'
}
const displayType = (t) => Array.isArray(t) ? t.join('、') : (t || '-')

/** ===== 快照：给 MapView 单次读取 ===== */
function makeMapSnapshotFromItem(item = {}) {
  const presetKey = item.preset3d || item.preset3dKey || ''
  const id = presetKey ? `preset:${presetKey}` : (item.id || item.taskId || '')
  return {
    id,
    name: item.name || '',
    type: normalizeRouteType(item),
    taskType: '线路扫描',
    creator: item.creator || DEFAULT_CREATOR,
    startTime: item.startTime || DEFAULT_START,
    thumbnailUrl: item.thumbnailUrl || '/media/thumbnails/default.png',
    takeoff: item.startStation || item.takeoff || '',
    route_id: item.route_id ?? item.routeCode ?? '',
    time_window: item.time_window ?? item.timeWindow ?? [],
    flightCount: item.flightCount ?? item.flights ?? 1,
    expectedFinish: item.expectedFinish ?? item.estimatedHours ?? '',
    route: item.route ?? '',
    preset3d: presetKey,
    preset3dKey: presetKey,
  }
}
function stashMapSnapshot(snap) {
  if (!snap?.id) return
  try { sessionStorage.setItem(`map:snapshot:${snap.id}`, JSON.stringify(snap)) } catch {}
}

/** ===== 预设航线与普通任务（初始化） ===== */
const presetRoutesRef = ref(
  (taskData || [])
    .filter(r => r?.preset3d || r?.preset3dKey)
    .map((r, idx) => {
      const normType = Array.isArray(r.type)
        ? r.type.map(x => (x ?? '').toString().trim()).filter(Boolean)
        : (r.type || r.routeType || '预设航线')
      return normalizeTaskMeta({
        ...r,
        id: r.id || (r.preset3d || r.preset3dKey),
        preset3d: r.preset3d || r.preset3dKey,
        thumbnailUrl: r.thumbnailUrl || '/media/thumbnails/default.png',
        cloud: r.cloud || DEFAULT_CLOUD,
        creator: r.creator || DEFAULT_CREATOR,
        startTime: r.startTime || DEFAULT_START,
        startStation: r.startStation || r.takeoff || '',
        endStation: r.endStation || r.landing || r.destination || '',
        type: Array.isArray(normType) && normType.length === 0 ? '预设航线' : normType
      }, idx)
    })
)
const ALLOWED_PRESET_KEYS = new Set(
  (presetRoutesRef.value || []).map(r => r.preset3d || r.preset3dKey).filter(Boolean)
)
const allData = ref(
  (taskData || [])
    .filter(r => !(r?.preset3d || r?.preset3dKey))
    .map((r, idx) => normalizeTaskMeta({
      ...r,
      id: r.id || `task-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      thumbnailUrl: r.thumbnailUrl || '/media/thumbnails/default.png',
      type: Array.isArray(r.type) ? r.type : (r.type || r.routeType || '航点飞行'),
      route_id:       r.route_id       ?? r.routeCode      ?? '',
      time_window:    r.time_window    ?? r.timeWindow     ?? '',
      flightCount:    r.flightCount    ?? r.flights        ?? '',
      expectedFinish: r.expectedFinish ?? r.estimatedHours ?? '',
      cloud: r.cloud || DEFAULT_CLOUD,
      creator: r.creator || DEFAULT_CREATOR,
      startTime: r.startTime || DEFAULT_START,
      startStation: r.startStation || r.takeoff || '',
      endStation: r.endStation || r.landing || r.destination || ''
    }, idx))
)
// 合并历史新增
try {
  const saved = JSON.parse(localStorage.getItem('savedTasks') || '[]')
  if (Array.isArray(saved) && saved.length) {
    const map = new Map(allData.value.map(i => [i.id, i]))
    saved.forEach(item => { if (!map.has(item.id)) allData.value.push(item) })
    allData.value = allData.value.map((item, idx) => normalizeTaskMeta(item, idx))
  }
} catch {}

/** ===== 组合/筛选/分页 ===== */
const combinedData = computed(() => {
  const byId = new Map()
  ;[...presetRoutesRef.value, ...allData.value].forEach(x => {
    if (!x) return
    const id = x.id || (x.preset3d || x.preset3dKey)
    if (!id) return
    if (!byId.has(id)) byId.set(id, x)
  })
  return Array.from(byId.values())
})
const combinedFiltered = computed(() => {
  let result = combinedData.value
  if (filters.value.name) {
    result = result.filter(item => (item.name || '').toLowerCase().includes(filters.value.name.toLowerCase()))
  }
  if (filters.value.type) {
    result = result.filter(item => normalizeRouteType(item) === filters.value.type)
  }
  if (filters.value.drone_name) {
    result = result.filter(item => (item.drone_name || '') === filters.value.drone_name)
  }
  return result
})
const combinedPaged = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return combinedFiltered.value.slice(start, start + pageSize.value)
})

/** ===== 新建任务弹窗 ===== */
const taskDialogVisible = ref(false)
const newTask = ref({
  name: '',
  routeType: '航点飞行',
  droneSeries: '经纬M30系列',
  droneModel: 'Matrice 30',
  presetKey: '',
  presetName: '',
  waypointsDraft: null,
  thumbnailDraft: ''
})
// 预设下拉
const presetOptions = ref([])
function getHiddenPresetSet() {
  try {
    const arr = JSON.parse(sessionStorage.getItem('hiddenPresets') || '[]')
    return new Set(Array.isArray(arr) ? arr : [])
  } catch { return new Set() }
}
function loadPresetOptions() {
  const core = (presetRoutesRef.value || []).map(r => ({
    key: r.preset3d || r.preset3dKey || r.id,
    name: r.name,
    thumb: r.thumbnailUrl || '/media/thumbnails/default.png'
  }))
  let extra = []
  try { extra = JSON.parse(localStorage.getItem('savedPresets') || '[]') } catch {}
  const map = new Map()
  ;[...core, ...extra].forEach(p => {
    if (!p?.key) return
    map.set(p.key, { key: p.key, name: p.name || p.key, thumb: p.thumb || '/media/thumbnails/default.png' })
  })
  const hidden = getHiddenPresetSet()
  hidden.forEach(k => map.delete(k))
  presetOptions.value = Array.from(map.values())
}
const openTaskDialog = () => {
  newTask.value = {
    name: '',
    routeType: '航点飞行',
    droneSeries: '经纬M30系列',
    droneModel: 'Matrice 30',
    presetKey: '',
    presetName: '',
    waypointsDraft: null,
    thumbnailDraft: ''
  }
  loadPresetOptions()
  taskDialogVisible.value = true
}

/** ===== 新建提交 ===== */
const submitTask = () => {
  if (!newTask.value.name.trim()) {
    ElMessage.error('航线名称不能为空')
    return
  }

  // 预设航线：直接跳地图，锁编辑（不生成卡片）
  if (newTask.value.routeType === '预设航线') {
    const presetKey = newTask.value.presetKey
    if (!presetKey) return ElMessage.error('请选择预设航线')
    const presetItem = presetRoutesRef.value.find(r => (r.preset3d || r.preset3dKey) === presetKey)
    if (!presetItem) return ElMessage.error('预设航线不存在或已被隐藏')

    taskDialogVisible.value = false
    const snap = makeMapSnapshotFromItem(presetItem)
    snap.id = `preset:${presetKey}`
    stashMapSnapshot(snap)
    emit('action', {
      type: 'open-map',
      data: {
        mapType: '预设航线',
        taskId: `preset:${presetKey}`,
        startStation: presetItem.startStation || '',
        preset3dKey: presetKey,
        restore: false,
        lock: true,
        sink: 'routeplan'
      }
    })
    return
  }

  // 普通任务：先创建列表项，再进入地图
  const nowStr = nowTimeText()
  const id = `task-${Date.now()}`
  const task = {
    id,
    name: newTask.value.name,
    routeType: newTask.value.routeType,
    type: newTask.value.routeType,
    droneSeries: newTask.value.droneSeries,
    droneModel: newTask.value.droneModel,
    startTime: nowStr,
    endTime: nowStr,
    status: '完成',
    creator: getCurrentOperator(),
    media: [],
    thumbnailUrl: '/media/thumbnails/default.png',
    location: '未设置',
    cloud: DEFAULT_CLOUD,
    drone: '',
    executionTimeDisplay: '',
    preset3d: '',
    startStation: '',
    endStation: '',
    route_id: '',
    time_window: '',
    flightCount: '',
    expectedFinish: '',
    routeCode: '',
    timeWindow: '',
    flights: '',
    estimatedHours: ''
  }
  allData.value = [task, ...allData.value]
  try {
    const saved = JSON.parse(localStorage.getItem('savedTasks') || '[]')
    saved.unshift(task)
    localStorage.setItem('savedTasks', JSON.stringify(saved))
  } catch {}
  try {
    const dict = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
    const taskForPanels = { ...task, type: Array.isArray(task.type) ? task.type : (task.type ? [task.type] : []) }
    dict[id] = taskForPanels
    localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
    busEmit(EVT_TASKS, { [id]: taskForPanels })
  } catch {}
  taskDialogVisible.value = false
  currentPage.value = 1
  ElMessage.success('任务创建成功')
  goToMap(task)
}

/** ===== 编辑弹窗（与地图一致，无折返点） ===== */
const editVisible = ref(false)
const editForm = ref({
  id: '',
  name: '',
  type: '航点飞行',
  taskType: '线路扫描',
  taskTags: [],
  startStation: '',
  route_id: '',
  mileage: '',
  timeRange: [],              // ['HH:mm','HH:mm'] for UI
  time_window: '',            // save back
  flightCount: 1,
  executionMode: 'immediate', // 'immediate' | 'schedule'
  customExecutionTime: '',    // 'YYYY-MM-DD HH:mm:ss'
  executionTimeDisplay: '',   // computed for display
  expectedFinish: 0,
  preset3d: '',
  preset3dKey: ''
})
const isPresetEditing = computed(() => !!(editForm.value.preset3d || editForm.value.preset3dKey))
function onTaskTypeChange() {
  // 根据类型清理不允许的已选标签
  const allowed = new Set(availableTaskTags.value)
  editForm.value.taskTags = (editForm.value.taskTags || []).filter(t => allowed.has(t))
}

// （保持已有）时间窗与执行时间工具函数 ...
function normalizeTimeWindowInput(v, timeRange) {
  if (Array.isArray(timeRange) && timeRange.length === 2) return timeRange
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.trim()) {
    const s = v.trim()
    if (s.startsWith('[') && s.endsWith(']')) {
      try { const arr = JSON.parse(s); if (Array.isArray(arr)) return arr } catch {}
    }
    if (s.includes('-')) {
      const [a,b] = s.split('-').map(x=>x.trim()).filter(Boolean)
      if (a && b) return [a,b]
    }
    return s
  }
  return ''
}
function computeExecutionDisplay(mode, dt) {
  if (mode === 'schedule' && dt) return dt.slice(0,16) // 'YYYY-MM-DD HH:mm'
  return '立即执行'
}
function openEditDialog(row) {
  const timeArr = Array.isArray(row.time_window)
    ? row.time_window
    : (typeof row.time_window === 'string' && row.time_window.includes('-'))
      ? row.time_window.split('-').map(s=>s.trim())
      : []
  const mode = row.executionMode || ((row.executionTimeDisplay && row.executionTimeDisplay !== '立即执行') ? 'schedule' : 'immediate')
  const initTaskType = row.taskType || '线路扫描'
  const allowedTags = TASK_TAGS_BY_TYPE[initTaskType] || []
  editForm.value = {
    id: row.id || row.taskId || '',
    name: row.name || '',
    type: Array.isArray(row.type) ? (row.type[0] || '航点飞行') : (row.type || '航点飞行'),
    taskType: initTaskType,
    taskTags: Array.isArray(row.taskTags)
      ? row.taskTags.filter(t => allowedTags.includes(t))
      : [],
    startStation: row.startStation || row.takeoff || '',
    route_id: row.route_id ?? row.routeCode ?? '',
    mileage: row.mileage || '',
    timeRange: timeArr.length === 2 ? timeArr : [],
    time_window: row.time_window ?? '',
    flightCount: row.flightCount ?? row.flights ?? 1,
    executionMode: mode,
    customExecutionTime: row.customExecutionTime || '',
    executionTimeDisplay: row.executionTimeDisplay || (mode === 'immediate' ? '立即执行' : ''),
    expectedFinish: row.expectedFinish ?? row.estimatedHours ?? 0,
    preset3d: row.preset3d || row.preset3dKey || '',
    preset3dKey: row.preset3d || row.preset3dKey || ''
  }
  editVisible.value = true
}
function saveEdit() {
  const payload = { ...editForm.value }
  payload.time_window = normalizeTimeWindowInput(payload.time_window, payload.timeRange)
  payload.executionTimeDisplay = computeExecutionDisplay(payload.executionMode, payload.customExecutionTime)

  if (payload.preset3d || payload.preset3dKey) {
    updatePresetCardOnly(payload)
  } else {
    updateExistingTaskOnly(payload)
  }
  try { localStorage.setItem('savedTasks', JSON.stringify(allData.value)) } catch {}

  const snap = makeMapSnapshotFromItem(payload)
  busEmit(EVT_ROUTEPLAN, { [snap.id]: snap })

  try {
    const dict = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
    const forPanels = { ...payload, type: Array.isArray(payload.type) ? payload.type : (payload.type ? [payload.type] : []) }
    dict[payload.id] = forPanels
    localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
    busEmit(EVT_TASKS, { [payload.id]: forPanels })
  } catch {}

  editVisible.value = false
  ElMessage.success('已保存')
}
function goToMapFromEdit() {
  const payload = { ...editForm.value }
  const isPreset = !!(payload.preset3d || payload.preset3dKey)
  const idForMap = isPreset ? `preset:${payload.preset3d || payload.preset3dKey}` : payload.id
  const snap = makeMapSnapshotFromItem(payload)
  snap.id = idForMap
  stashMapSnapshot(snap)
  editVisible.value = false
  emit('action', {
    type: 'open-map',
    data: {
      mapType: isPreset ? '预设航线' : normalizeRouteType(payload),
      taskId: idForMap,
      startStation: payload.startStation || '',
      preset3dKey: payload.preset3d || payload.preset3dKey || '',
      restore: !isPreset,
      lock: isPreset,
      sink: 'routeplan'
    }
  })
}

/** ===== 其它交互 ===== */
const mediaDrawerVisible = ref(false)
const selectedTask = ref(null)
const openMediaDrawer = (item) => { selectedTask.value = item; mediaDrawerVisible.value = true }
const getThumbnail = (item) => item.thumbnailUrl || '/media/thumbnails/default.png'
const search = () => { currentPage.value = 1; ElMessage.success('搜索已应用') }
const reset = () => { filters.value = { name: '', type: '', drone_name: '' }; currentPage.value = 1; ElMessage.info('搜索条件已重置') }
const handlePageChange = (v) => { currentPage.value = v }
const handlePageSizeChange = (v) => { pageSize.value = v; currentPage.value = 1 }

/** “修改”行为：打开本地编辑弹窗 */
const editTask = (row) => { openEditDialog(row) }

/** 删除任务：普通任务直接删；预设仅会话内隐藏 */
const deleteTask = (row) => {
  const isTruePreset =
    !!(row?.preset3d || row?.preset3dKey || (typeof row?.id === 'string' && row.id.startsWith('preset:')))
  if (!isTruePreset) {
    allData.value = allData.value.filter(i => i.id !== row.id)
    try {
      const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
      delete savedRoutes[row.id]
      localStorage.setItem('savedRoutes', JSON.stringify(savedRoutes))
      const savedTasks = JSON.parse(localStorage.getItem('savedTasks') || '[]')
      localStorage.setItem('savedTasks', JSON.stringify(savedTasks.filter(i => i.id !== row.id)))
    } catch {}
    try {
      const dict = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
      if (dict[row.id]) {
        delete dict[row.id]
        localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
        busEmit(EVT_REMOVE, [row.id])
        busEmit(EVT_TASKS, dict)
      }
    } catch {}
    ElMessage.success('任务已删除')
    return
  }
  const presetKey = row?.preset3d || row?.preset3dKey
  if (!presetKey) return ElMessage.warning('未找到预设标识')
  if (!confirm(`确定要删除预设航线「${row.name || presetKey}」吗？`)) return
  const idx = presetRoutesRef.value.findIndex(r => (r.preset3d || r.preset3dKey) === presetKey)
  if (idx !== -1) presetRoutesRef.value.splice(idx, 1)
  loadPresetOptions()
  try {
    const dict = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
    const shadowId = `preset:${presetKey}`
    if (dict[shadowId]) {
      delete dict[shadowId]
      localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
      busEmit(EVT_REMOVE, [shadowId])
      busEmit(EVT_TASKS, dict)
    }
    const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
    if (savedRoutes[shadowId]) {
      delete savedRoutes[shadowId]
      localStorage.setItem('savedRoutes', JSON.stringify(savedRoutes))
    }
  } catch {}
  ElMessage.success('预设航线已删除')
}

/** 导入 JSON 航线文件 */
const handleBeforeUpload = (file) => {
  const reader = new FileReader()
  reader.onload = (event) => {
    try {
      const text = event.target.result
      const json = JSON.parse(text)
      const savedRoutes = JSON.parse(localStorage.getItem('savedRoutes') || '{}')
      const nowStr = nowTimeText()
      const pushOne = (task) => {
        const id = `task-${Date.now()}-${Math.random().toString(36).slice(2)}`
        const t = normalizeTaskMeta({
          ...task,
          id,
          thumbnailUrl: task.thumbnailUrl || '/media/thumbnails/default.png',
          startTime: task.startTime || nowStr,
          creator: task.creator || getCurrentOperator(),
          location: task.location || '未设置',
          cloud: task.cloud || DEFAULT_CLOUD,
          media: task.media || [],
          type: task.type || task.routeType || '航点飞行',
          preset3d: task.preset3d || task.preset3dKey || '',
          route_id:       task.route_id       ?? task.routeCode      ?? '',
          time_window:    task.time_window    ?? task.timeWindow     ?? '',
          flightCount:    task.flightCount    ?? task.flights        ?? '',
          expectedFinish: task.expectedFinish ?? task.estimatedHours ?? '',
          startStation:   task.startStation || task.takeoff || '',
          endStation:     task.endStation || task.landing || task.destination || ''
        }, allData.value.length)
        allData.value = [t, ...allData.value]
        if (t.routeData) savedRoutes[t.id] = t.routeData

        const presetKey = task.preset3d || task.preset3dKey || task.presetKey
        if (presetKey) {
          savedPresets.push({ key: presetKey, name: task.name || `预设航线-${presetKey}`, thumb: task.thumbnailUrl || '/media/thumbnails/default.png' })
        }
        try {
          const dict = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
          const forPanels = { ...t, type: Array.isArray(t.type) ? t.type : (t.type ? [t.type] : []) }
          dict[id] = forPanels
          localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
          busEmit(EVT_TASKS, { [id]: forPanels })
        } catch {}
      }
      let savedPresets = []
      if (Array.isArray(json)) json.forEach(pushOne)
      else if (typeof json === 'object') pushOne(json)
      else return ElMessage.error('文件格式不正确，请上传有效的航线JSON文件')

      localStorage.setItem('savedRoutes', JSON.stringify(savedRoutes))
      if (savedPresets.length) {
        const base = new Map((JSON.parse(localStorage.getItem('savedPresets') || '[]')||[]).map(p=>[p.key,p]))
        savedPresets.forEach(p => base.set(p.key, p))
        localStorage.setItem('savedPresets', JSON.stringify(Array.from(base.values())))
      }
      loadPresetOptions()
      try { localStorage.setItem('savedTasks', JSON.stringify(allData.value)) } catch {}
      currentPage.value = 1
      ElMessage.success('导入成功')
    } catch (err) {
      ElMessage.error('解析文件失败，请检查文件内容')
      console.error('导入航线失败:', err)
    }
  }
  reader.readAsText(file)
  return false
}

/** 只更新：预设卡片 */
function updatePresetCardOnly(raw) {
  const presetKey = raw?.preset3d || raw?.preset3dKey
  if (!presetKey) return
  if (!ALLOWED_PRESET_KEYS.has(presetKey)) return
  const idx = presetRoutesRef.value.findIndex(r => (r.preset3d || r.preset3dKey) === presetKey)
  if (idx === -1) return
  const merged = {
    ...presetRoutesRef.value[idx],
    ...raw,
    preset3d: presetKey,
    preset3dKey: presetKey,
    taskType: raw.taskType ?? presetRoutesRef.value[idx].taskType,
    taskTags: Array.isArray(raw.taskTags) ? raw.taskTags : (presetRoutesRef.value[idx].taskTags || []),
    mileage: raw.mileage ?? presetRoutesRef.value[idx].mileage,
    executionMode: raw.executionMode ?? presetRoutesRef.value[idx].executionMode,
    customExecutionTime: raw.customExecutionTime ?? presetRoutesRef.value[idx].customExecutionTime,
    thumbnailUrl: raw.thumbnailUrl || presetRoutesRef.value[idx].thumbnailUrl || '/media/thumbnails/default.png',
    drone: raw.drone ?? presetRoutesRef.value[idx].drone,
    executionTimeDisplay: raw.executionTimeDisplay ?? presetRoutesRef.value[idx].executionTimeDisplay,
    startTime: raw.startTime || presetRoutesRef.value[idx].startTime || DEFAULT_START,
    creator: raw.creator || presetRoutesRef.value[idx].creator || DEFAULT_CREATOR,
    cloud: raw.cloud || presetRoutesRef.value[idx].cloud || DEFAULT_CLOUD,
    startStation: raw.startStation || raw.takeoff || presetRoutesRef.value[idx].startStation || '',
    endStation: raw.endStation || raw.landing || raw.destination || presetRoutesRef.value[idx].endStation || '',
    route_id:       raw.route_id       ?? presetRoutesRef.value[idx].route_id,
    time_window:    raw.time_window    ?? presetRoutesRef.value[idx].time_window,
    flightCount:    raw.flightCount    ?? presetRoutesRef.value[idx].flightCount,
    expectedFinish: raw.expectedFinish ?? presetRoutesRef.value[idx].expectedFinish,
  }
  presetRoutesRef.value.splice(idx, 1, merged)
}
/** 只更新：普通任务 */
function updateExistingTaskOnly(raw) {
  const id = raw?.id || raw?.taskId
  if (!id) return
  const idx = allData.value.findIndex(i => i.id === id)
  if (idx === -1) return
  const prev = allData.value[idx]
  const merged = {
    ...prev,
    ...raw,
    id,
    name: raw.name || prev.name,
    taskType: raw.taskType ?? prev.taskType,
    taskTags: Array.isArray(raw.taskTags) ? raw.taskTags : (prev.taskTags || []),
    mileage: raw.mileage ?? prev.mileage,
    executionMode: raw.executionMode ?? prev.executionMode,
    customExecutionTime: raw.customExecutionTime ?? prev.customExecutionTime,
    thumbnailUrl: raw.thumbnailUrl || prev.thumbnailUrl || '/media/thumbnails/default.png',
    type: Array.isArray(raw.type) ? raw.type : (raw.type || raw.routeType || prev.type),
    drone: raw.drone ?? prev.drone,
    executionTimeDisplay: raw.executionTimeDisplay ?? prev.executionTimeDisplay,
    cloud: raw.cloud || prev.cloud || DEFAULT_CLOUD,
    creator: raw.creator || prev.creator || DEFAULT_CREATOR,
    startTime: raw.startTime || prev.startTime || DEFAULT_START,
    startStation: raw.startStation || raw.takeoff || prev.startStation || '',
    endStation: raw.endStation || raw.landing || raw.destination || prev.endStation || '',
    route_id:       raw.route_id       ?? prev.route_id,
    time_window:    raw.time_window    ?? prev.time_window,
    flightCount:    raw.flightCount    ?? prev.flightCount,
    expectedFinish: raw.expectedFinish ?? prev.expectedFinish,
  }
  allData.value.splice(idx, 1, merged)
}
function upsertTaskToTop(raw) {
  if (!raw) return
  const presetKey = raw?.preset3d || raw?.preset3dKey
  if (presetKey) updatePresetCardOnly(raw)
  else updateExistingTaskOnly(raw)
}

/** ===== 事件订阅 ===== */
let offTasks, offExec, offRemove, offRouteplan, offDraft
onMounted(() => {
  offTasks  = busOn(EVT_TASKS,  handleTasksUpdated)
  offExec   = busOn(EVT_EXEC,   handleExecutionUpdated)
  offRemove = busOn(EVT_REMOVE, handleTasksRemoved)
  offRouteplan = busOn(EVT_ROUTEPLAN, handleTasksUpdated)
  offDraft = busOn(EVT_DRAFT_SAVED, (payload) => {
    if (!payload) return
    newTask.value.waypointsDraft = payload.waypoints || []
    newTask.value.thumbnailDraft = payload.thumbnailUrl || ''
  })
  try {
    const execArr = JSON.parse(localStorage.getItem(STORAGE_EXEC) || '[]')
    if (Array.isArray(execArr) && execArr.length) handleExecutionUpdated(execArr)
  } catch {}
})
onUnmounted(() => {
  offTasks && offTasks()
  offExec && offExec()
  offRemove && offRemove()
  offRouteplan && offRouteplan()
  offDraft && offDraft()
})

/** ===== 处理外部回填 ===== */
const prefillFromProps = () => {
  const id = props.prefillId
  if (!id) return
  const tasks = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
  const t = tasks[id]
  if (!t) return
  upsertTaskToTop(t)
}
watch(() => [props.prefillId, props.prefillMode], () => { prefillFromProps() }, { immediate: true })

/** ===== 列表/卡片行为 ===== */
const goToMap = (item) => {
  try {
    const presetKey = item?.preset3d || item?.preset3dKey || ''
    const isPreset  = !!presetKey
    const mapType   = isPreset ? '预设航线' : normalizeRouteType(item)
    const taskIdForMap = isPreset ? `preset:${presetKey}` : (item?.taskId || item?.id || '')
    if (isPreset) {
      const snap = makeMapSnapshotFromItem(item)
      snap.id = taskIdForMap
      stashMapSnapshot(snap)
    }
    emit('action', {
      type: 'open-map',
      data: {
        mapType,
        taskId: taskIdForMap,
        startStation: item?.startStation || item?.takeoff || '',
        preset3dKey: presetKey,
        restore: !isPreset,
        lock: isPreset,
        sink: 'routeplan'
      }
    })
  } catch (e) {
    console.error('[RoutePlan] goToMap error:', e, item)
    emit('action', {
      type: 'open-map',
      data: { mapType: '航点飞行', taskId: String(item?.id || item?.taskId || ''), startStation: '', preset3dKey: '', restore: true, lock: false }
    })
  }
}

/** ===== tasks/execution/remove 事件回调 ===== */
const handleTasksUpdated = (payload) => {
  if (!payload) return
  const list = Array.isArray(payload) ? payload : Object.values(payload || {})
  list.forEach(upsertTaskToTop)
}
const handleExecutionUpdated = (execArr) => {
  if (!Array.isArray(execArr)) return
  execArr.forEach(e => {
    upsertTaskToTop({
      id: e.id,
      name: e.name,
      type: e.type,
      preset3d: e.preset3d,
      drone: e.drone,
      executionTimeDisplay: e.executionTimeDisplay,
      startTime: e.startTime || e.createdAt || '',
      creator: e.creator || DEFAULT_CREATOR
    })
  })
}
const handleTasksRemoved = (ids) => {
  if (!Array.isArray(ids) || ids.length === 0) return
  const set = new Set(ids)
  const before = allData.value.length
  allData.value = allData.value.filter(i => !set.has(i.id))
  if (allData.value.length !== before) {
    try {
      const saved = JSON.parse(localStorage.getItem('savedTasks') || '[]')
      const newSaved = saved.filter(i => !set.has(i.id))
      localStorage.setItem('savedTasks', JSON.stringify(newSaved))
    } catch {}
  }
  // 预设卡片不做删除
}
</script>

<style scoped>
.f-label { font-weight: 600; width: 80px; text-align: right; color: #303133; }

/* 任务卡片容器：响应式网格 */
.task-card-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 16px;
}

/* 任务卡片 */
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
  cursor: pointer;
  transition: transform 0.2s ease;
}
.task-card:hover { transform: translateY(-2px); }

/* 缩略图 */
.task-thumb-left {
  height: 200px;
  width: auto;
  max-width: 200px;
  object-fit: contain;
  border-right: 1px solid #e0e0e0;
  flex-shrink: 0;
}

/* 文字区 */
.task-info-right { flex: 1; padding: 10px 16px; font-size: 13px; display: flex; flex-direction: column; justify-content: space-between; }
.task-header { display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 14px; margin-bottom: 4px; }
.task-title { font-weight: 700; }
.task-line { margin: 2px 0; }
.task-actions-right { margin-top: 8px; display: flex; gap: 12px; }

/* 弹窗样式（深色风格） */
:deep(.el-dialog) { background-color: #1f1f1f !important; color: #ffffff !important; border-radius: 8px !important; }
:deep(.el-dialog__header) { padding: 16px 20px; border-bottom: 1px solid #444; margin-right: 0; background-color: #1f1f1f; }
:deep(.el-dialog__title) { font-size: 16px; font-weight: 600; color: #ffffff !important; }
.dialog-content { padding: 20px; background-color: #1f1f1f; }
.section { margin-bottom: 24px; }
.section-title { font-size: 14px; color: #f0f0f0; margin-bottom: 12px; font-weight: 600; }
.option-group { margin-left: 8px; }
.radio-group { display: flex; flex-wrap: wrap; gap: 12px; }

/* 方块大按钮尺寸 */
.square-button :deep(.el-radio-button__inner) {
  width: 130px; height: 90px; display: flex; align-items: center; justify-content: center;
  border-radius: 5px; font-size: 14px; font-weight: 600; text-align: center;
}

/* 图标+文字的纵向布局 */
.icon-radio { display: flex; flex-direction: column; align-items: center; gap: 6px; }

/* 交互颜色 */
:deep(.el-dialog) .el-radio-button__inner {
  border-radius: 5px !important; background-color: #9eb0ff2f; color: #ffffff; border-color: #444444ba; transition: all 0.2s;
}
:deep(.el-dialog) .el-radio-button__inner:hover { border-color: #409EFF; color: #409EFF; }
:deep(.el-dialog) .el-radio-button.is-active .el-radio-button__inner { background-color: #409EFF; border-color: #409EFF; color: #ffffff; }
.dialog-footer { background-color: #1f1f1f; border-top: 1px solid #444444ba; display: flex; justify-content: flex-end; padding: 12px 20px; }
.cancel-btn, .confirm-btn { padding: 8px 20px; border-radius: 4px; }
.cancel-btn { margin-right: 12px; }

/* 表格包装 */
.table-card { margin-top: 12px; }
.table-title { font-weight: 700; margin-bottom: 8px; color: #303133; }

/* 分页 */
:deep(.el-pagination) { color: #303133; }
:deep(.el-pagination .el-input__inner) { background-color: #fff; color: #303133; }
</style>
