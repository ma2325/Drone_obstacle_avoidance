<template>
  <div style="padding: 20px 10px;">
    <!-- 选项卡切换 -->
    <el-tabs v-model="currentView" @tab-click="handleTabClick" style="margin-bottom: 20px;">
      <el-tab-pane label="日任务计划" name="task" />
      <el-tab-pane label="可用设备列表" name="drone" />
      <el-tab-pane label="日任务分配" name="execution" :disabled="!showExecutionTab" />
    </el-tabs>

    <!-- 日任务计划搜索栏 -->
    <div v-show="currentView === 'task'" class="search-bar">
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
        <label class="label">任务ID</label>
        <el-input v-model="filters.id" placeholder="请输入任务ID" style="width: 200px;" />
        <label class="label">任务类型</label>
        <el-select v-model="filters.taskType" placeholder="请选择任务类型" style="width: 200px;">
          <el-option label="全部" value="" />
          <el-option label="线路扫描" value="线路扫描" />
          <el-option label="点位扫描" value="点位扫描" />
        </el-select>
        <label class="label">航线任务</label>
        <el-select v-model="filters.type" placeholder="请选择航线任务" style="width: 200px;" multiple>
          <el-option label="全部" value="" />
          <el-option v-for="type in allInspectionTypes" :key="type" :label="type" :value="type" />
        </el-select>
        <el-button @click="reset">重置</el-button>
        <el-button type="primary" @click="search">搜索</el-button>
        <el-button type="success" plain @click="openTaskDialog()">
          <el-icon><Plus /></el-icon>
          <span style="margin-left: 6px;">新建</span>
        </el-button>
      </div>
      <div class="right-actions">
        <el-button v-if="isTaskConfirmed" @click="resetTaskSelection">重新选择</el-button>
        <el-button v-if="!isTaskConfirmed && selectedTasks.length > 0" type="primary" @click="confirmTaskSelection">
          确定选择任务
        </el-button>
        <el-button :type="canExecute ? 'danger' : 'info'" :disabled="!canExecute" @click="executeTasks">
          生成任务计划
        </el-button>
      </div>
    </div>

    <!-- 日任务计划表格 -->
    <div v-show="currentView === 'task'" class="table-container">
      <el-table
        ref="taskTable"
        :data="taskTableData"
        stripe
        border
        :fit="true"
        :height="tableHeight"
        style="width: 100%;"
        @selection-change="handleTaskSelectionChange"
      >
        <el-table-column v-if="!isTaskConfirmed" type="selection" width="50" />
        <el-table-column label="" type="index" width="50" />
        <el-table-column prop="id" label="任务ID" width="120" />
        <el-table-column prop="name" label="任务名称" width="160" />
        <el-table-column prop="taskType" label="任务类型" width="100" />
        <el-table-column prop="type" label="航线任务" width="160">
          <template #default="{ row }">
            <div class="type-wrap">
              <span v-for="(t, i) in row.type" :key="i" class="type-item">
                <i class="dot" :style="{ '--dot': typeDotColor(t) }"></i>
                <span class="type-text">{{ t }}</span>
              </span>
              <span v-if="!row.type || !row.type.length">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="航线编号" width="120">
          <template #default="{ row }">{{ row.preset3d || '-' }}</template>
        </el-table-column>
        <el-table-column prop="time_window" label="时间窗" width="120">
          <template #default="{ row }">
            {{ row.time_window ? row.time_window.join('-') : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="flightCount" label="飞行趟数" width="110">
          <template #default="{ row }">{{ row.flightCount || '-' }}</template>
        </el-table-column>

        <!-- 任务执行时间列 -->
        <el-table-column label="任务执行时间" width="220">
          <template #default="{ row }">
            <div class="exec-col">
              <el-select
                v-model="row.executionTime"
                placeholder="选择执行时间"
                style="width: 100%;"
                :disabled="isTaskConfirmed"
                @change="updateTaskExecutionTime(row)"
              >
                <el-option label="立即执行" value="immediate" />
                <el-option label="设定时间" value="custom" />
              </el-select>
              <el-date-picker
                v-if="row.executionTime === 'custom'"
                v-model="row.customExecutionTime"
                type="datetime"
                placeholder="选择时间"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                style="width: 100%;"
                @change="handleCustomTimeChange(row)"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="expectedFinish" label="预计执行完毕时间 (h)" width="190">
          <template #default="{ row }">{{ row.expectedFinish || '-' }}</template>
        </el-table-column>

        <el-table-column label="操作" width="150" fixed="right" align="center">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button type="text" size="small" @click="openTaskDialog(row)">
                <div class="btn blue">
                  <svg class="svg" viewBox="0 0 24 24">
                    <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                  </svg>
                </div>
              </el-button>
              <el-button type="text" size="small" @click="deleteTask(row)">
                <div class="btn red">
                  <svg class="svg" viewBox="0 0 24 24">
                    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                  </svg>
                </div>
              </el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="航线" width="115" fixed="right" align="center">
          <template #default="{ row }">
            <el-button type="primary" link @click.stop="goPlanRoute(row)">查看航线</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页控件：任务 -->
      <div class="pagination-container">
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
    </div>

    <!-- 可用设备列表（搜索 + 表格 + 分页） -->
    <div v-show="currentView === 'drone'">
      <!-- 搜索栏 -->
      <div class="search-bar">
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <label class="label">设备名称</label>
          <el-input
            v-model="droneFilters.search"
            placeholder="输入设备名称或编号搜索"
            style="width: 200px;"
            @keyup.enter="searchDrones"
          />

          <label class="label">设备位置</label>
          <el-select
            v-model="droneFilters.takeoff"
            placeholder="请选择设备存放位置"
            style="width: 200px;"
            clearable
            @change="searchDrones"
          >
            <el-option label="全部" value="" />
            <el-option
              v-for="point in takeoffPoints"
              :key="point"
              :label="point"
              :value="point"
            />
          </el-select>

          <el-button type="primary" @click="searchDrones">搜索</el-button>
          <el-button @click="resetDroneFilters">重置</el-button>

          <span style="margin-left:8px;color:#909399;">
            共 {{ filteredDroneData.length }} 台；可选 {{ filteredDroneData.filter(isDroneSelectable).length }} 台
          </span>
        </div>

        <div class="right-actions">
          <el-button v-if="isDroneConfirmed" @click="resetDroneSelection">重新选择</el-button>
          <el-button
            v-if="!isDroneConfirmed && selectedDrones.length > 0"
            type="primary"
            @click="confirmDroneSelection"
          >
            确定选择无人机（{{ selectedDrones.length }}）
          </el-button>
          <el-button
            :type="canExecute ? 'danger' : 'info'"
            :disabled="!canExecute"
            @click="executeTasks"
          >
            生成任务计划
          </el-button>
        </div>
      </div>

      <!-- 表格 -->
      <div class="table-container" style="margin-top: 8px;">
        <el-table
          ref="droneTable"
          :data="droneTableData"
          stripe
          border
          :fit="true"
          :height="tableHeight"
          style="width: 100%;"
          @selection-change="handleDroneSelectionChange"
          @select-all="handleSelectAllDrones"
        >
          <el-table-column
            v-if="!isDroneConfirmed"
            type="selection"
            width="60"
            :selectable="isDroneSelectable"
          />
          <el-table-column type="index" label="#" width="60" />
          <el-table-column prop="id" label="设备编号" width="180" />
          <el-table-column prop="name" label="设备名称" width="200" />
          <el-table-column prop="takeoff" label="位置信息" width="200" />
          <el-table-column label="当前状态" width="180">
            <template #default="{ row }">
              <span :class="{
                'status-idle': row.status === '空闲中',
                'status-working': row.status === '工作中',
                'status-charging': row.status === '充换电'
              }">
                <span
                  class="status-dot"
                  :style="{ backgroundColor:
                    row.status === '空闲中' ? '#67C23A' :
                    row.status === '工作中' ? '#F56C6C' : '#E6A23C'
                  }"
                ></span>
                {{ row.status || '-' }}
              </span>
            </template>
          </el-table-column>

          <!-- 电量续航：进度条，阈值上色 + 悬浮显示百分比 -->
          <el-table-column label="电量续航" width="140">
            <template #default="{ row }">
              <div v-if="Number.isFinite(row.battery)">
                <el-tooltip :content="`${clampedBattery(row.battery)}%`" placement="top">
                  <el-progress
                    :percentage="clampedBattery(row.battery)"
                    :stroke-width="10"
                    :color="batteryColor(row.battery)"
                    :show-text="false"
                  />
                </el-tooltip>
              </div>
              <span v-else>-</span>
            </template>
          </el-table-column>

          <el-table-column prop="enduranceMileage" label="续航里程" width="160">
            <template #default="{ row }">{{ row.enduranceMileage || '-' }}</template>
          </el-table-column>
          <el-table-column prop="model" label="设备型号" width="180" />
        </el-table>

        <!-- 分页 -->
        <div class="pagination-container">
          <el-pagination
            :total="filteredDroneData.length"
            :page-size="dronePageSize"
            :current-page="droneCurrentPage"
            :page-sizes="[5, 10, 20]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleDronePageChange"
            @size-change="handleDronePageSizeChange"
          />
        </div>
      </div>
    </div>

    <!-- 日任务分配 -->
    <div v-show="currentView === 'execution'">
      <!-- 任务完成情况搜索栏 -->
      <div class="search-bar">
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <label class="label">任务ID</label>
          <el-input v-model="executionFilters.id" placeholder="请输入任务ID" style="width: 200px;" @input="filterExecutionData" />
          <label class="label">任务类型</label>
          <el-select v-model="executionFilters.taskType" placeholder="请选择任务类型" style="width: 200px;" @change="filterExecutionData">
            <el-option label="全部" value="" />
            <el-option label="线路扫描" value="线路扫描" />
            <el-option label="点位扫描" value="点位扫描" />
          </el-select>
          <label class="label">航线任务</label>
          <el-select v-model="executionFilters.type" placeholder="请选择航线任务" style="width: 200px;" multiple @change="filterExecutionData">
            <el-option label="全部" value="" />
            <el-option v-for="type in allInspectionTypes" :key="type" :label="type" :value="type" />
          </el-select>
          <el-button @click="resetExecutionFilters">重置</el-button>
        </div>
        <div class="right-actions">
          <el-button v-if="isExecutionConfirmed" @click="resetExecutionSelection">重新选择</el-button>
          <el-button v-if="!isExecutionConfirmed && selectedExecution.length > 0" type="primary" @click="confirmExecutionSelection">
            确定选择执行任务
          </el-button>
          <el-button type="primary" plain @click="openProgressDialog">
            查看进度
          </el-button>
        </div>
      </div>

      <!-- 任务完成情况表格（执行数据） -->
      <div class="table-container">
        <el-table
          ref="executionTable"
          :data="executionTableData"
          stripe
          border
          :fit="true"
          :height="tableHeight"
          style="width: 100%;"
          @selection-change="handleExecutionSelectionChange"
          @select-all="handleSelectAllExecution"
        >
          <el-table-column v-if="!isExecutionConfirmed" type="selection" width="60" />
          <el-table-column label="任务ID" prop="id" width="110" />
          <el-table-column prop="name" label="任务名称" width="160" />
          <el-table-column label="任务类型" prop="taskType" width="100" />
          <el-table-column label="航线任务" prop="type" width="150">
            <template #default="{ row }">
              <div class="type-wrap">
                <span v-for="(t, i) in row.type" :key="i" class="type-item">
                  <i class="dot" :style="{ '--dot': typeDotColor(t) }"></i>
                  <span class="type-text">{{ t }}</span>
                </span>
                <span v-if="!row.type || !row.type.length">-</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="航线里程" prop="route" width="120" />
          <el-table-column label="任务执行时间" width="160">
            <template #default="{ row }">{{ row.executionTimeDisplay || '-' }}</template>
          </el-table-column>
          <el-table-column label="预计执行完毕时间 (h)" prop="expectedFinish" width="180">
            <template #default="{ row }">{{ row.expectedFinish || '-' }}</template>
          </el-table-column>
          <el-table-column label="实际执行完毕时间 (h)" prop="actualFinish" width="180">
            <template #default="{ row }">{{ row.actualFinish || '-' }}</template>
          </el-table-column>
          <el-table-column label="执勤无人机" prop="drone" width="140">
            <template #default="{ row }">{{ row.drone || '-' }}</template>
          </el-table-column>
          <el-table-column label="优先级" prop="priority" width="100">
            <template #default="{ row }">{{ row.priority || '-' }}</template>
          </el-table-column>
          <el-table-column label="执行状态" prop="status" width="100">
            <template #default="{ row }">{{ row.status || '待执行' }}</template>
          </el-table-column>
          <el-table-column label="异常记录" prop="exceptionRecord" width="180">
            <template #default="{ row }">{{ row.exceptionRecord || '-' }}</template>
          </el-table-column>
          <el-table-column label="识别结果数量" prop="recognitionCount" width="180">
            <template #default="{ row }">{{ row.recognitionCount || '-' }}</template>
          </el-table-column>
          <el-table-column label="精度指标" prop="accuracyMetric" width="150">
            <template #default="{ row }">{{ row.accuracyMetric || '-' }}</template>
          </el-table-column>
          <el-table-column label="时间窗符合率" prop="timeWindowCompliance" width="180">
            <template #default="{ row }">{{ row.timeWindowCompliance || '-' }}</template>
          </el-table-column>
          <el-table-column label="完成率" prop="completionRate" width="150">
            <template #default="{ row }">{{ row.completionRate || '-' }}</template>
          </el-table-column>
          <el-table-column label="飞行日志" prop="flightLog" width="200">
            <template #default="{ row }">{{ row.flightLog || '-' }}</template>
          </el-table-column>
          <el-table-column label="电池使用次数" prop="batteryUsageCount" width="180">
            <template #default="{ row }">{{ row.batteryUsageCount || '-' }}</template>
          </el-table-column>
          <el-table-column label="设备健康度" prop="deviceHealth" width="150">
            <template #default="{ row }">{{ row.deviceHealth || '-' }}</template>
          </el-table-column>

          <!-- 模拟执行 -->
          <el-table-column label="模拟执行" width="120" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="primary" link @click="goSimulate(row)">模拟执行</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-container">
          <el-pagination
            :total="filteredExecutionData.length"
            :page-size="executionPageSize"
            :current-page="executionCurrentPage"
            :page-sizes="[5, 10, 20, 50]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleExecutionPageChange"
            @size-change="handleExecutionPageSizeChange"
          />
        </div>
      </div>
    </div>

    <!-- 日计划完成情况：弹窗 -->
    <el-dialog
      v-model="progressVisible"
      title="日计划完成情况"
      width="60%"
      align-center
      destroy-on-close
    >
      <div class="table-container" style="max-height: 60vh;">
        <!-- 动态进度数据源 -->
        <el-table :data="dayProgressDisplay" stripe border :fit="true" :height="400">
          <el-table-column prop="id"       label="任务ID" width="110" />
          <el-table-column                 label="航线Key" width="120">
            <template #default="{ row }">{{ row.preset3d || '-' }}</template>
          </el-table-column>
          <el-table-column prop="name"     label="任务名称" min-width="120" />
          <el-table-column prop="route"     label="航线里程" min-width="120" />
          <el-table-column                 label="状态" width="100">
            <template #default="{ row }">{{ row.status || '待执行' }}</template>
          </el-table-column>
          <el-table-column                 label="完成度" width="140">
            <template #default="{ row }">
              <el-tooltip :content="`${dayProgressPercent(row)}%`" placement="top">
                <el-progress :show-text="false" :stroke-width="16" :percentage="dayProgressPercent(row)" />
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="updatedAt" label="更新时间" width="160" />
        </el-table>

        <div style="margin-top:12px;font-weight:600;">当日各航线完成统计</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:6px;">
          <el-tag v-for="(v, rk) in dayRouteStat" :key="rk" type="info" effect="plain">
            {{ rk }}：{{ v }} 次
          </el-tag>
        </div>
      </div>

      <template #footer>
        <el-space>
          <!-- 刷新：强制所有进度 100% -->
          <el-button @click="syncDayProgress(true)">刷新</el-button>
          <el-button type="primary" @click="progressVisible=false">关闭</el-button>
        </el-space>
      </template>
    </el-dialog>

    <!-- 新建/修改任务弹窗 -->
    <el-dialog v-model="taskDialogVisible" :title="editMode ? '修改任务' : '新建任务'" width="500px">
      <el-form :model="currentTask" label-width="100px">
        <el-form-item label="任务ID">
          <el-input v-model="currentTask.id" placeholder="请输入任务ID" :disabled="editMode" />
        </el-form-item>
        <el-form-item label="任务类型">
          <el-select v-model="currentTask.taskType" placeholder="请选择任务类型" @change="updateInspectionTypes">
            <el-option label="线路扫描" value="线路扫描" />
            <el-option label="点位扫描" value="点位扫描" />
          </el-select>
        </el-form-item>
        <el-form-item label="航线任务">
          <el-checkbox-group v-model="currentTask.type">
            <el-checkbox v-if="currentTask.taskType === '线路扫描'" v-for="option in areaTypes" :key="option" :label="option">{{ option }}</el-checkbox>
            <el-checkbox v-if="currentTask.taskType === '点位扫描'" v-for="option in pointTypes" :key="option" :label="option">{{ option }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="起飞点">
          <el-select v-model="currentTask.takeoff" placeholder="请选择起飞点">
            <el-option v-for="point in takeoffPoints" :key="point" :label="point" :value="point" />
          </el-select>
        </el-form-item>
        <el-form-item label="航线编号"><el-input v-model="currentTask.route_id" placeholder="请输入航线编号" /></el-form-item>
        <el-form-item label="航线里程"><el-input v-model="currentTask.route" placeholder="请输入航线里程" /></el-form-item>
        <el-form-item label="折返点设置"><el-input v-model="currentTask.turnaround" placeholder="请输入折返点设置" /></el-form-item>
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
        <el-form-item label="飞行趟数"><el-input v-model="currentTask.flightCount" placeholder="请输入飞行趟数" /></el-form-item>
        <el-form-item label="任务执行时间">
          <el-select v-model="currentTask.executionTime" placeholder="选择执行时间" style="width: 100%;">
            <el-option label="立即执行" value="immediate" />
            <el-option label="设定时间" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="自定义时间" v-if="currentTask.executionTime === 'custom'">
          <el-date-picker
            v-model="currentTask.customExecutionTime"
            type="datetime"
            placeholder="选择时间"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DD HH:mm"
            style="width: 100%;"
          />
        </el-form-item>
        <el-form-item label="预计执行时间 (h)"><el-input v-model="currentTask.expectedFinish" placeholder="请输入预计执行时间 (h)" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitTask">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 稳定版 AirportTask2.vue（巡检类型点+文字、电量进度条阈值上色、日计划匀速进度、悬浮显示百分比）
 */
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

// import taskData from '@/test-data/taskData_all.json'
import baseDrones from '@/test-data/droneDataTask.json'
import devices from '@/test-data/devices.json'

/* ==== 周库：轻耦合接入 ==== */
import {
  loadStore as loadWeeklyStore,
  on as weeklyOn,
  getWeekKey,
  listCountsByRoute,
  addTaskToWeek,
  removeTaskFromWeek,
  upsertSubsetItem
} from '@/shared/routeWeekly'

/* ==== 防止 MapView 影子数据 ==== */
const isPresetShadowId   = (id) => typeof id === 'string' && id.startsWith('preset:')
const isPresetShadowTask = (t)  => isPresetShadowId(t?.id || t?.taskId)

/* ===== 路由（仅用于模拟执行跳转） ===== */
const router = useRouter()

/* ===== MapView 事件桥 ===== */
const emit = defineEmits(['action'])
const props = defineProps({
  presetRoutes: { type: Array, default: () => [] },
  allTasks: { type: Array, default: () => [] },
  prefillId: { type: String, default: '' },
  prefillMode: { type: String, default: '' }
})

/* ===== 常量 / 事件名 ===== */
const STORAGE_TASKS = 'inspectionTasks'
const STORAGE_EXEC  = 'executionData'
const STORAGE_PROGRESS = 'dayProgressV1'
const STORAGE_SYNCED_IDS = 'dayProgressSyncedIdsV1'
const EVT_TASKS     = 'tasks-updated'
const EVT_EXEC      = 'execution-updated'
const EVT_REMOVE    = 'tasks-removed'
const STORAGE_DRONES = 'droneList'
const EVT_DRONES = 'drones-updated'

/* ===== 任务类型 / 起飞点 ===== */
const areaTypes = ['抛洒物识别', '团雾检测', '病害识别', '拥堵点检测']
const pointTypes = ['桥梁巡检', '边坡巡检']
const allInspectionTypes = [...areaTypes, ...pointTypes]
const takeoffPoints = ['杜家坎收费站','琉璃河收费站','涿州北收费站','涿州收费站','高碑店收费站','定兴收费站','徐水收费站','保定北收费站','保定收费站','清苑收费站','望都收费站','定州收费站','新乐收费站','藁城北收费站','石家庄机场收费站','石家庄北收费站','石家庄收费站']

/* ===== 页面状态 ===== */
const currentView = ref('task')
const showExecutionTab = ref(false)
const taskTable = ref(null); const droneTable = ref(null); const executionTable = ref(null)

/* ===== 表格高度自适应（不改宽高配置，仅计算高度） ===== */
const windowH = ref(window.innerHeight)
const tableHeight = computed(() => windowH.value - 210)
const onResize = () => { windowH.value = window.innerHeight }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

/* ===== 周库状态 / 当前周 / 阈值 ===== */
const weeklyStoreRef = ref(loadWeeklyStore())
const weekKey = ref(getWeekKey())
const airportThreshold = computed(() => weeklyStoreRef.value?.config?.airportThreshold ?? 2)
const getSubsetObject = (wk) => {
  if (!wk || typeof wk !== 'object') return {}
  if (wk.subset && typeof wk.subset === 'object') return wk.subset
  const out = {}
  Object.keys(wk).forEach(k => { if (/^route_\d+$/.test(k) && Array.isArray(wk[k])) out[k] = wk[k] })
  return out
}

/* ===== 扁平化周库 -> rows（含 routeKey） ===== */
const weeklyRows = computed(() => {
  const wk = weeklyStoreRef.value?.weeks?.[weekKey.value] || {}
  const subset = getSubsetObject(wk)
  const rows = []
  Object.keys(subset).forEach(routeKey => {
    const arr = Array.isArray(subset[routeKey]) ? subset[routeKey] : []
    arr.forEach(t => {
      rows.push({
        ...t,
        routeKey,
        route_id: t.route_id || routeKey,
        preset3d: t.preset3d || t.preset3dKey || routeKey
      })
    })
  })
  return rows
})

/* ===== “低于阈值”的路线集合（兜底来源） ===== */
const lowRoutesSet = computed(() => {
  const counts = listCountsByRoute(weekKey.value)
  const set = new Set()
  Object.entries(counts).forEach(([rk, cnt]) => { if (cnt < airportThreshold.value) set.add(rk) })
  return set
})

/* ===== 任务数据（UI 主数据源） ===== */
const normalizeTask = (item) => ({
  ...item,
  preset3d: item.preset3d || item.preset3dKey || '',
  taskType: item.taskType || (item.type?.some(t => pointTypes.includes(t)) && !item.type?.some(t => areaTypes.includes(t)) ? '点位扫描' : '线路扫描'),
  isDroneSelected: false,
  drone: item.drone || '',
  executionTime: item.executionTime || 'immediate',
  customExecutionTime: item.customExecutionTime || null,
  expectedFinish: item.expectedFinish || '-',
  actualFinish: item.actualFinish || '-'
})
const deriveRouteKey = (t) => {
  if (t?.preset3d && /^route_\d+$/.test(t.preset3d)) return t.preset3d
  if (t?.route_id && /^route_\d+$/.test(t.route_id)) return t.route_id
  const m = String(t?.name || '').match(/route_\d+/)
  return m ? m[0] : ''
}

const allData = ref([]); const selectedTasks = ref([]); const confirmedTasks = ref([]); const isTaskConfirmed = ref(false)
function refreshFromWeeklyOrFallback() {
  const weeklyAll = weeklyRows.value.map(r => normalizeTask({ ...r, route_id: r.routeKey }))
  const base = weeklyAll.filter(r => lowRoutesSet.value.has(r.routeKey))
  let local = []
  try {
    const store = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
    local = Object.values(store || {}).filter(t => t && !isPresetShadowTask(t)).map(normalizeTask)
  } catch {}
  const byId = new Map()
  ;[...base, ...local].forEach(t => byId.set(t.id, { ...(byId.get(t.id) || {}), ...t }))
  const merged = Array.from(byId.values())
  if (allData.value.length === 0) allData.value = merged.length > 0 ? merged : []
}

/* ==== 接收 TaskExecution 推荐清单 ==== */
const AIRPORT_PUSH_PREFIX = 'airport_push_'
function pickRecommendedTasksByWeek(weekKeyStr){
  try {
    const raw = localStorage.getItem(`${AIRPORT_PUSH_PREFIX}${weekKeyStr}`)
    const list = JSON.parse(raw || '[]') || []
    const routeSet = new Set(list.map(x => x.routeKey).filter(Boolean))
    if (routeSet.size === 0) return []
    const base = weeklyRows.value
      .filter(r => routeSet.has(r.routeKey))
      .filter(r => r.status !== '已完成' && r.status !== '完成')
      .map(r => normalizeTask({ ...r, route_id: r.routeKey }))
    const byId = new Map()
    base.forEach(t => byId.set(t.id, t))
    return Array.from(byId.values())
  } catch { return [] }
}
function handleAirportPush(e){
  const wk = e?.detail?.weekKey || weekKey.value
  const rec = pickRecommendedTasksByWeek(wk)
  if (rec.length > 0) {
    allData.value = rec
    selectedTasks.value = []; confirmedTasks.value = []; isTaskConfirmed.value = false
    ElMessage.info(`已载入当周推荐任务 ${rec.length} 条`)
  }
}

/* ===== 无人机数据 ===== */
const droneFilters = ref({ search: '', takeoff: '' })
const allDrones = ref([])
const loadDrones = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_DRONES) || '[]')
    allDrones.value = (Array.isArray(saved) && saved.length) ? saved : baseDrones
  } catch { allDrones.value = baseDrones }
}
onMounted(() => { loadDrones(); window.addEventListener(EVT_DRONES, loadDrones) })
onUnmounted(() => window.removeEventListener(EVT_DRONES, loadDrones))
const selectedDrones = ref([]); const confirmedDrones = ref([]); const isDroneConfirmed = ref(false)
const droneCurrentPage = ref(1); const dronePageSize = ref(10)

/* ===== 执行数据 / 日进度 ===== */
const selectedExecution = ref([]); const confirmedExecution = ref([]); const isExecutionConfirmed = ref(false)
const executionCurrentPage = ref(1); const executionPageSize = ref(10)
const executionData = ref([])
const dayProgress = ref([])
const syncedIds = ref(new Set())
const progressVisible = ref(false)

/* ===== 弹窗 ===== */
const taskDialogVisible = ref(false); const editMode = ref(false)
const currentTask = ref({
  id:'', taskType:'线路扫描', type:[], route:'', takeoff:'',
  route_id:'', turnaround:'', time_window:null, flightCount:'', drone:'',
  executionTime:'immediate', customExecutionTime:null, expectedFinish:'', actualFinish:'-',
  preset3d:''
})

/* ===== 其他状态 ===== */
const canExecute = ref(false)

/* ===== 时间格式化 ===== */
const formatDateTime = (date) => {
  const Y = date.getFullYear()
  const M = String(date.getMonth() + 1).padStart(2, '0')
  const D = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const m = String(date.getMinutes()).padStart(2, '0')
  return `${Y}-${M}-${D} ${h}:${m}`
}

/* ===== 过滤 & 分页（任务） ===== */
const filters = ref({ id: '', taskType: '', type: [] })
const currentPage = ref(1); const pageSize = ref(5)
const filteredData = computed(() => {
  let result = allData.value.filter(i => !isPresetShadowId(i.id))
  if (filters.value.id) result = result.filter(i => String(i.id).includes(filters.value.id))
  if (filters.value.taskType) result = result.filter(i => i.taskType === filters.value.taskType)
  const typeFilter = (filters.value.type || []).filter(Boolean)
  if (typeFilter.length > 0) result = result.filter(i => typeFilter.every(t => i.type.includes(t)))
  return result
})
const pagedData = computed(() => filteredData.value.slice((currentPage.value-1)*pageSize.value, (currentPage.value)*pageSize.value))
const taskTableData = computed(() => isTaskConfirmed.value ? confirmedTasks.value : pagedData.value)

/* ===== 过滤 & 分页（无人机） ===== */
const filteredDroneData = computed(() => {
  let result = [...allDrones.value]
  if (droneFilters.value.search) {
    const kw = droneFilters.value.search.toLowerCase()
    result = result.filter(i => i.name.toLowerCase().includes(kw) || String(i.id).includes(kw))
  }
  if (droneFilters.value.takeoff) result = result.filter(i => i.takeoff === droneFilters.value.takeoff)
  return result.sort((a,b) =>
    (isDroneSelectable(a) && !isDroneSelectable(b)) ? -1 :
    (!isDroneSelectable(a) && isDroneSelectable(b)) ? 1 : 0)
})
const pagedDroneData = computed(() => filteredDroneData.value.slice((droneCurrentPage.value-1)*dronePageSize.value, droneCurrentPage.value*dronePageSize.value))
const droneTableData = computed(() => isDroneConfirmed.value ? confirmedDrones.value : pagedDroneData.value)

/* ===== 过滤 & 分页（执行） ===== */
const executionFilters = ref({ id:'', taskType:'', type:[] })
const filteredExecutionData = computed(() => {
  let result = executionData.value
  if (executionFilters.value.id) result = result.filter(i => String(i.id).includes(executionFilters.value.id))
  if (executionFilters.value.taskType) result = result.filter(i => i.taskType === executionFilters.value.taskType)
  const typeFilter = (executionFilters.value.type || []).filter(Boolean)
  if (typeFilter.length > 0) result = result.filter(i => typeFilter.every(t => i.type.includes(t)))
  return result
})
const pagedExecutionData = computed(() =>
  filteredExecutionData.value.slice((executionCurrentPage.value-1)*executionPageSize.value, (executionCurrentPage.value)*executionPageSize.value)
)
const executionTableData = computed(() => isExecutionConfirmed.value ? confirmedExecution.value : pagedExecutionData.value)

/* ===== 搜索/重置（无人机） ===== */
const searchDrones = () => { droneCurrentPage.value = 1 }
const resetDroneFilters = () => { droneFilters.value = { search:'', takeoff:'' }; droneCurrentPage.value = 1 }

/* ===== 选项卡回显选中状态 ===== */
const handleTabClick = () => {
  nextTick(() => {
    if (currentView.value === 'task' && !isTaskConfirmed.value) selectedTasks.value.forEach(r => taskTable.value?.toggleRowSelection(r, true))
    else if (currentView.value === 'drone' && !isDroneConfirmed.value) selectedDrones.value.forEach(r => droneTable.value?.toggleRowSelection(r, true))
    else if (currentView.value === 'execution' && !isExecutionConfirmed.value) selectedExecution.value.forEach(r => executionTable.value?.toggleRowSelection(r, true))
  })
}

/* ===== 选择回调 ===== */
const handleTaskSelectionChange = (sel) => { if (!isTaskConfirmed.value) selectedTasks.value = sel }
const handleDroneSelectionChange = (sel) => { if (!isDroneConfirmed.value) selectedDrones.value = sel }
const handleExecutionSelectionChange = (sel) => { if (!isExecutionConfirmed.value) selectedExecution.value = sel }
const handleSelectAllDrones = (selection) => {
  if (isDroneConfirmed.value) return
  const allSelectable = filteredDroneData.value.filter(isDroneSelectable)
  if (selection.length > 0) {
    selectedDrones.value = allSelectable
    filteredDroneData.value.forEach(row => droneTable.value?.toggleRowSelection(row, isDroneSelectable(row)))
  } else {
    selectedDrones.value = []; droneTable.value?.clearSelection()
  }
}
const handleSelectAllExecution = (selection) => {
  if (isExecutionConfirmed.value) return
  if (selection.length > 0) {
    selectedExecution.value = filteredExecutionData.value
    filteredExecutionData.value.forEach(row => executionTable.value?.toggleRowSelection(row, true))
  } else {
    selectedExecution.value = []; executionTable.value?.clearSelection()
  }
}

/* ===== 无人机是否可勾选 ===== */
const isDroneSelectable = (row) => row.status === '空闲中' && row.battery >= 80

/* ===== 确认选择/分配 ===== */
const confirmTaskSelection = () => {
  if (selectedTasks.value.length === 0) return ElMessage.warning('请至少选择一个任务')
  confirmedTasks.value = [...selectedTasks.value]; isTaskConfirmed.value = true
  ElMessage.success('当日任务清单保存成功')
  canExecute.value = isTaskConfirmed.value && isDroneConfirmed.value
  persistTasks()
}
const confirmDroneSelection = () => {
  if (selectedDrones.value.length === 0) return ElMessage.warning('请至少选择一架无人机')
  confirmedDrones.value = [...selectedDrones.value]; isDroneConfirmed.value = true
  ElMessage.success('当日执勤无人机保存成功')

  const tasksToAssign = isTaskConfirmed.value ? confirmedTasks.value : selectedTasks.value
  assignDronesToTasks(tasksToAssign, confirmedDrones.value)

  const store = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
  tasksToAssign.forEach(t => { store[t.id] = { ...(store[t.id] || {}), ...t, id:t.id, drone:t.drone, takeoff:t.takeoff } })
  localStorage.setItem(STORAGE_TASKS, JSON.stringify(store))
  busEmit(EVT_TASKS, store)

  allData.value = allData.value.map(item => {
    const hit = tasksToAssign.find(t => t.id === item.id)
    return hit ? { ...item, drone: hit.drone } : item
  })

  canExecute.value = isTaskConfirmed.value && isDroneConfirmed.value
  persistTasks()
}

/* ===== 分配无人机 ===== */
const assignDronesToTasks = (tasks, drones) => {
  const used = new Set()
  tasks.forEach(task => {
    let picked = drones.find(d => d.takeoff === task.takeoff && isDroneSelectable(d) && !used.has(d.name))
    if (!picked) picked = drones.find(d => isDroneSelectable(d) && !used.has(d.name))
    task.drone = picked ? picked.name : '-'
    if (picked) used.add(picked.name)
  })
}

/* ===== 重置选择 ===== */
const resetTaskSelection = () => {
  isTaskConfirmed.value = false; confirmedTasks.value = []; selectedTasks.value = []; taskTable.value?.clearSelection()
  canExecute.value = isTaskConfirmed.value && isDroneConfirmed.value
  persistTasks()
}
const resetDroneSelection = () => {
  isDroneConfirmed.value = false; confirmedDrones.value = []; selectedDrones.value = []; droneTable.value?.clearSelection()
  const tasksToClear = isTaskConfirmed.value ? confirmedTasks.value : selectedTasks.value
  tasksToClear.forEach(t => t.drone = '')
  canExecute.value = isTaskConfirmed.value && isDroneConfirmed.value
  persistTasks()
}
const resetExecutionSelection = () => {
  isExecutionConfirmed.value = false; confirmedExecution.value = []; selectedExecution.value = []; executionTable.value?.clearSelection()
}

/* ===== 执行时间编辑（同步执行表 + 广播） ===== */
const updateTaskExecutionTime = (row) => {
  if (row.executionTime !== 'custom') row.customExecutionTime = null
  allData.value = [...allData.value]; persistTasks()
  const idx = executionData.value.findIndex(e => e.id === row.id)
  if (idx !== -1) {
    executionData.value[idx].executionTimeDisplay = row.executionTime === 'immediate' ? formatDateTime(new Date()) : (row.customExecutionTime || '-')
    persistExecution()
  }
}
const handleCustomTimeChange = (row) => {
  if (row.executionTime === 'custom' && !row.customExecutionTime) {
    row.executionTime = 'immediate'; ElMessage.warning('请选择有效的时间')
  }
  allData.value = [...allData.value]; persistTasks()
  const idx = executionData.value.findIndex(e => e.id === row.id)
  if (idx !== -1) {
    executionData.value[idx].executionTimeDisplay = row.executionTime === 'immediate' ? formatDateTime(new Date()) : (row.customExecutionTime || '-')
    persistExecution()
  }
}

/* ===== 生成任务计划（去重构建 executionData） ===== */
const executeTasks = () => {
  if (!(isTaskConfirmed.value && isDroneConfirmed.value && confirmedTasks.value.length > 0 && confirmedDrones.value.length > 0)) {
    return ElMessage.warning('请先选择任务和无人机')
  }

  const now = formatDateTime(new Date())
  const resolveDroneId = (name) => (allDrones.value.find(x => x.name === name)?.id || '')

  const byId = new Map()
  confirmedTasks.value.forEach(task => {
    const drone_id = task.drone_id || resolveDroneId(task.drone)
    const row = {
      ...task,
      drone_id,
      status: '待执行',
      executionTimeDisplay: task.executionTime === 'immediate' ? now : (task.customExecutionTime || '-'),
      priority: '-',
      exceptionRecord: '-',
      recognitionCount: '-',
      accuracyMetric: '-',
      timeWindowCompliance: '-',
      completionRate: '-',
      flightLog: '-',
      batteryUsageCount: '-',
      deviceHealth: '-'
    }
    byId.set(row.id, row)
  })
  executionData.value = Array.from(byId.values())

  persistExecution()
  showExecutionTab.value = true
  currentView.value = 'execution'
  ElMessage.success('任务已分配并开始执行')
}

/* ===== 进度弹窗：打开 -> 同步(重置startAt) -> 显示 ===== */
function openProgressDialog(){
  syncDayProgress(false, true)   // resetStartAt = true，让进度从 0% 开始动画
  progressVisible.value = true
}

/* ===== 巡检类型点+文字的颜色表 ===== */
const TYPE_DOT_COLORS = {
  '桥梁巡检':   '#EFDCCE',
  '边坡巡检':   '#888C91',
  '抛洒物识别': '#CDBDC0',
  '团雾检测':   '#AEA5B8',
  '拥堵点检测': '#6378AF',
  '病害识别':   '#8B91B5'
}
function typeDotColor(name){
  if (TYPE_DOT_COLORS[name]) return TYPE_DOT_COLORS[name]
  if (/桥|边坡/.test(name || '')) return '#BFB0D9'
  if (/雾|拥堵|抛洒|病害|识别|检测/.test(name || '')) return '#A9C6DF'
  return '#C0CBD9'
}

/* ===== 电量进度条：阈值上色 + 取整 + 限幅 ===== */
function clampedBattery(b){
  const v = Number(b)
  return Number.isFinite(v) ? Math.max(0, Math.min(100, Math.round(v))) : 0
}
function batteryColor(b){
  const p = clampedBattery(b)
  if (p >= 80) return '#67C23A'   // 绿
  if (p >= 40) return '#E6A23C'   // 橙
  return '#F56C6C'                // 红
}

/* ===== 匀速进度条（5 km/s） ===== */
const SPEED_KM_PER_SEC = 5
function parseRouteKm(route) {
  if (route == null) return NaN
  const s = String(route).trim()
  if (!s) return NaN
  const m = s.match(/([\d.]+)\s*(km|公里|m|米)?/i)
  if (!m) return NaN
  const val = parseFloat(m[1])
  const unit = (m[2] || 'km').toLowerCase()
  if (Number.isNaN(val)) return NaN
  if (unit === 'm' || unit === '米') return val / 1000
  return val
}

/* ===== 动态时钟：弹窗打开时每秒刷新一次 ===== */
const nowTick = ref(Date.now())
let tickTimer = null
watch(progressVisible, (v) => {
  if (v) {
    if (tickTimer) clearInterval(tickTimer)
    tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
  } else {
    if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
  }
})
onUnmounted(() => { if (tickTimer) clearInterval(tickTimer) })

/* ===== 动态百分比计算 ===== */
function calcPercentBySpeed(row) {
  if (row._forceComplete) return 100
  if (row.status === '已完成' || row.status === '完成') return 100
  const startStr = row.executionTimeDisplay || row.startAt
  const start = startStr ? new Date(startStr.replace(/-/g, '/')) : null
  if (!start || isNaN(start.getTime())) return 0

  const elapsedSec = Math.max(0, (nowTick.value - start.getTime()) / 1000)
  const totalKm = parseRouteKm(row.route)
  if (!Number.isFinite(totalKm) || totalKm <= 0) return 0

  const traveledKm = Math.min(totalKm, elapsedSec * SPEED_KM_PER_SEC)
  const pct = Math.round((traveledKm / totalKm) * 100)
  return Math.max(0, Math.min(100, pct))
}
function dayProgressPercent(row) { return calcPercentBySpeed(row) }

/* ===== 动态表数据（进度随 nowTick 变化） ===== */
const dayProgressDisplay = computed(() =>
  (dayProgress.value || []).map(p => ({
    ...p,
    percent: calcPercentBySpeed(p)
  }))
)

/* ===== 统计：完成到 100% 的路线次数 ===== */
const dayRouteStat = computed(() => {
  const stat = {}
  ;(dayProgress.value || []).forEach(p => {
    const rk = p.preset3d || ''
    if (!rk) return
    const pct = calcPercentBySpeed(p)
    if (pct >= 100) stat[rk] = (stat[rk] || 0) + 1
  })
  return stat
})

/* ===== 同步“日计划完成情况”（支持刷新=100%，支持打开时重置起点） ===== */
function syncDayProgress(forceComplete = false, resetStartAt = false){
  const now = formatDateTime(new Date())
  const dedup = new Map(dayProgress.value.map(x => [x.id, x]))
  executionData.value.forEach(e => {
    dedup.set(e.id, {
      id: e.id,
      name: e.name,
      preset3d: e.preset3d || e.route_id || '',
      route: e.route || '-',
      status: e.status || '待执行',
      startAt: resetStartAt ? now : (e.executionTimeDisplay || now),
      _forceComplete: forceComplete ? true : (e._forceComplete || false),
      updatedAt: now,
      completionRate: typeof e.completionRate === 'number' ? e.completionRate : undefined
    })
  })
  dayProgress.value = Array.from(dedup.values())
  localStorage.setItem(STORAGE_PROGRESS, JSON.stringify(dayProgress.value))

  // ✅ 首次“完成”的任务 -> 回写周库
  const newlyCompleted = executionData.value.filter(e => {
    const completed = forceComplete
      ? true
      : (typeof e.completionRate === 'number' ? e.completionRate >= 100 : e.status === '已完成')
    return completed && !syncedIds.value.has(e.id)
  })
  if (newlyCompleted.length) {
    newlyCompleted.forEach(e => {
      const rk = e.preset3d || e.route_id || ''
      if (!rk) return
      const execDate = String(e.executionTimeDisplay || now).slice(0,10)
      upsertSubsetItem(
        weekKey.value,
        rk,
        { ...e, id: e.id, preset3d: rk, route_id: rk, status: '已完成', exec_at: execDate }
      )
      syncedIds.value.add(e.id)
    })
    localStorage.setItem(STORAGE_SYNCED_IDS, JSON.stringify(Array.from(syncedIds.value)))
  }
  ElMessage.success(forceComplete ? '已刷新：完成度 100%' : '已同步到「日计划完成情况」')
}

/* ===== 打开任务弹窗（新建/编辑） ===== */
const openTaskDialog = (row) => {
  editMode.value = !!row
  currentTask.value = row ? { ...row } : {
    id:'', taskType:'线路扫描', type:[], route:'', takeoff:'',
    route_id:'', turnaround:'', time_window:null, flightCount:'', drone:'',
    executionTime:'immediate', customExecutionTime:null, expectedFinish:'', actualFinish:'-',
    preset3d:''
  }
  updateInspectionTypes(); taskDialogVisible.value = true
}

/* ===== 从 props 预填 ===== */
const prefillFromProps = () => {
  const id = props.prefillId; if (!id) return
  const store = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
  const t = store[id]; if (!t) return
  if (isPresetShadowTask(t)) return
  const existIdx = allData.value.findIndex(item => item.id === id)
  if (existIdx !== -1) {
    const old = allData.value[existIdx]
    allData.value.splice(existIdx, 1, { ...old, ...t })
    persistTasks()
    return
  }
  if (props.prefillMode === 'create') {
    allData.value.unshift(normalizeTask(t))
    persistTasks()
  }
  if (!allData.value.some(item => item.id === id)) {
    allData.value.unshift(normalizeTask(t))
    persistTasks()
  }
}

/* ===== 首次挂载：恢复执行数据 + 合并已存任务 + 周库/推荐订阅 ===== */
let offTasks=null, offExec=null, offWeekly=null
onMounted(() => {
  try { executionData.value = JSON.parse(localStorage.getItem(STORAGE_EXEC) || '[]') } catch { executionData.value = [] }
  try {
    const arr = JSON.parse(localStorage.getItem(STORAGE_PROGRESS) || '[]')
    dayProgress.value = Array.isArray(arr) ? arr : []
    const setArr = JSON.parse(localStorage.getItem(STORAGE_SYNCED_IDS) || '[]')
    syncedIds.value = new Set(Array.isArray(setArr) ? setArr : [])
  } catch {}

  if (executionData.value.length > 0) showExecutionTab.value = true

  refreshFromWeeklyOrFallback()
  offWeekly = weeklyOn('weekly-updated', (s) => { weeklyStoreRef.value = s; refreshFromWeeklyOrFallback() })

  // 推荐清单：事件订阅 + 首次回显
  window.addEventListener('airport-push-update', handleAirportPush)
  const rec = pickRecommendedTasksByWeek(weekKey.value)
  if (rec.length > 0) { allData.value = rec }

  try {
    const store = JSON.parse(localStorage.getItem(STORAGE_TASKS) || '{}')
    const locals = Object.values(store || {}).filter(t => t && !isPresetShadowTask(t)).map(normalizeTask)
    const byId = new Map(allData.value.map(i => [i.id, i]))
    locals.forEach(t => byId.set(t.id, { ...(byId.get(t.id) || {}), ...t } ))
    allData.value = Array.from(byId.values())
  } catch {}

  prefillFromProps()

  offTasks = busOn(EVT_TASKS, (detail) => {
    const isWrapped = detail && typeof detail === 'object' && 'payload' in detail
    const source    = isWrapped ? detail.source : null
    const dict      = isWrapped ? (detail.payload || {}) : (detail || {})

    if (source && source !== 'airport') return
    const list = Object.values(dict).filter(t => t && !isPresetShadowTask(t)).map(normalizeTask)
    if (list.length === 0) return
    const byId = new Map(allData.value.map(i => [i.id, i]))
    list.forEach(t => byId.set(t.id, { ...(byId.get(t.id) || {}), ...t } ))
    allData.value = Array.from(byId.values())
  })

  offExec = busOn(EVT_EXEC, (arr) => {
    const list = Array.isArray(arr) ? arr : (arr && Array.isArray(arr.payload) ? arr.payload : [])
    const dedup = new Map()
    list.forEach(e => dedup.set(e.id, e))
    executionData.value = Array.from(dedup.values())
    if (executionData.value.length > 0) showExecutionTab.value = true
  })
})
onUnmounted(() => {
  offTasks && offTasks(); offExec && offExec(); offWeekly && offWeekly()
  window.removeEventListener('airport-push-update', handleAirportPush)
})

/* ===== 查看航线（从 AirportTask2 跳转 MapView） ===== */
let _goPlanBusy = false
const goPlanRoute = (row = {}) => {
  if (_goPlanBusy) return
  _goPlanBusy = true
  setTimeout(() => { _goPlanBusy = false }, 250)

  const presetKey = row?.preset3d || row?.preset3dKey || ''
  const isPreset  = !!presetKey
  const payload = {
    mapType: isPreset ? '预设航线' : '航点飞行',
    taskId: row?.id || '',
    startStation: row?.takeoff || row?.startStation || '',
    preset3dKey: presetKey,
    restore: !isPreset,
    lock: isPreset
  }
  emit('action', { type: 'open-map-from-airport', data: payload })
  window.dispatchEvent(new CustomEvent('route-shell-action', { detail: { type: 'open-map-from-airport', data: payload }}))
}

/* ===== 模拟执行：跳到首页设备卡片 ===== */
const goSimulate = (row) => {
  const device = devices.find(d => d.id === row.drone_id)
  if (!device) return ElMessage.warning(`未找到对应的设备，drone_id=${row.drone_id}`)
  router.push({ path: '/', query: { focus: device.id } })
}

/* ===== 提交任务（新增/编辑） ===== */
const submitTask = () => {
  if (!currentTask.value.id?.trim()) {
    if (editMode.value) return ElMessage.error('任务ID缺失')
    currentTask.value.id = `T-${Date.now()}`
  }

  if (editMode.value) {
    const idx = allData.value.findIndex(item => item.id === currentTask.value.id)
    if (idx !== -1) allData.value[idx] = { ...currentTask.value }
    ElMessage.success('任务修改成功')
  } else {
    allData.value.unshift({ ...currentTask.value })
    ElMessage.success('任务创建成功')
  }
  taskDialogVisible.value = false
  persistTasks()

  const routeKey = deriveRouteKey(currentTask.value)
  if (routeKey) {
    const t = { ...currentTask.value, route_id: routeKey, preset3d: routeKey }
    addTaskToWeek(t, weekKey.value)
  }
}

/* ===== 更新航线任务类型（切换大类时清空小类） ===== */
const updateInspectionTypes = () => { currentTask.value.type = [] }

/* ===== 搜索与分页（统一句柄） ===== */
const search = () => { currentPage.value = 1 }
const reset = () => { filters.value = { id:'', taskType:'', type:[] }; currentPage.value = 1 }
const handlePageChange = val => { currentPage.value = val }
const handlePageSizeChange = val => { pageSize.value = val; currentPage.value = 1 }
const handleDronePageChange = val => { droneCurrentPage.value = val }
const handleDronePageSizeChange = val => { dronePageSize.value = val; droneCurrentPage.value = 1 }
const handleExecutionPageChange = val => { executionCurrentPage.value = val }
const handleExecutionPageSizeChange = val => { executionPageSize.value = val; executionCurrentPage.value = 1 }

/* ===== 删除任务（同步清理执行表 + 广播 + 周库） ===== */
const deleteTask = (row) => {
  const id = row.id
  allData.value = allData.value.filter(item => item.id !== id)
  selectedTasks.value = selectedTasks.value.filter(i => i.id !== id)
  confirmedTasks.value = confirmedTasks.value.filter(i => i.id !== id)

  const beforeLen = executionData.value.length
  executionData.value = executionData.value.filter(e => e.id !== id)
  if (executionData.value.length !== beforeLen) persistExecution()
  persistTasks()
  busEmit(EVT_REMOVE, [id])
  ElMessage.success('任务已删除')

  const routeKey = deriveRouteKey(row) || row.route_id
  if (routeKey) removeTaskFromWeek(id, routeKey, weekKey.value)
}

/* ===== 执行过滤 ===== */
const filterExecutionData = () => { executionCurrentPage.value = 1 }
const resetExecutionFilters = () => { executionFilters.value = { id:'', taskType:'', type:[] }; executionCurrentPage.value = 1 }

/* ===== allData 变化后同步表格选择状态 ===== */
watch(allData, () => {
  nextTick(() => {
    taskTable.value?.clearSelection?.()
    selectedTasks.value.forEach(r => taskTable.value?.toggleRowSelection?.(r, true))
  })
}, { deep: true })

/* ===== 简易事件总线（本地） ===== */
function busEmit(name, detail){ window.dispatchEvent(new CustomEvent(name, { detail })) }
function busOn(name, cb){ const h = e => cb(e.detail); window.addEventListener(name, h); return () => window.removeEventListener(name, h) }

/* ===== 持久化 helpers（并广播） ===== */
function persistTasks(){
  const dict = {}
  allData.value.filter(t => !isPresetShadowId(t.id)).forEach(t => { dict[t.id] = t })
  localStorage.setItem(STORAGE_TASKS, JSON.stringify(dict))
  busEmit(EVT_TASKS, { source: 'airport', payload: dict })
}
function persistExecution(){
  const byId = new Map()
  executionData.value.forEach(e => byId.set(e.id, e))
  executionData.value = Array.from(byId.values())
  localStorage.setItem(STORAGE_EXEC, JSON.stringify(executionData.value))
  if (executionData.value.length > 0) showExecutionTab.value = true
  busEmit(EVT_EXEC, { source: 'execution', payload: executionData.value })
}

/* ===== props 预填监听 ===== */
watch(() => props.prefillId, () => { prefillFromProps() }, { immediate: true })
</script>

<style scoped>
.label { font-weight: 600; width: 80px; text-align: right; color: #303133; }
.right-actions { display: flex; gap: 10px; margin-left: auto; margin-right: 50px; }
.type-line { display: flex; align-items: center; margin-bottom: 4px; }
.exec-col { display: flex; flex-direction: column; gap: 8px; }

.search-bar {
  padding: 10px; background: #fff; border-bottom: 1px solid #EBEEF5;
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap; position: relative; z-index: 11;
}
.table-container {
  width: 100%; max-height: calc(100vh - 190px); overflow-y: auto; border: 1px solid #EBEEF5; border-radius: 4px; background:#fff;
}
.pagination-container {
  position: sticky; bottom: 0; padding: 10px; background: #fff; border-top: 1px solid #EBEEF5;
  display: flex; justify-content: flex-end; z-index: 10;
}

.op-btns { display: flex; gap: 0px; justify-content: center; }
.btn { width: 40px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 4px; }
.btn.blue { background-color: #409EFF; } .btn.red { background-color: #F56C6C; }
.svg { width: 16px; height: 16px; fill: #fff; }

:deep(.el-table .el-table__row){ height: auto; }
:deep(.el-table .el-table__header-wrapper){ position: sticky; top: 0; z-index: 10; background: #F5F7FA; }
:deep(.el-table .el-table__header-wrapper th){ height: 30px; line-height: 30px; padding: 8px; font-size: 14px; }
:deep(.el-table .cell){ line-height: 24px; padding: 8px; }

/* 状态颜色文本（仅用于“当前状态”一列） */
.status-idle { color: #67C23A; opacity: 1; }
.status-working { color: #F56C6C; opacity: 0.5; }
.status-charging { color: #E6A23C; opacity: 0.7; }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }

/* 进度条圆角（可选美化） */
:deep(.el-progress-bar__outer){ border-radius: 6px; }
:deep(.el-progress-bar__inner){ border-radius: 6px; }

/* Tabs 美化（不改表格宽高） */
:deep(.el-tabs__header){ background:#fff; padding:12px 24px; box-shadow:0 2px 4px rgba(0,0,0,0.05); }
:deep(.el-tabs__item){
  font-weight:500; font-size:18px; padding:0 32px; margin:0 15px; line-height:48px; color:#6b7280;
  display:flex; justify-content:center; align-items:center; min-width:290px; text-align:center; transition:all .2s;
}
:deep(.el-tabs__item:hover){ color:#303133; background:#f1f5f9; }
:deep(.el-tabs__item.is-active){
  color:#409EFF; background:#ffffff; box-shadow:0 8px 16px rgba(0,0,0,0.2),0 4px 8px rgba(0,0,0,0.1); border-bottom:3px solid #409EFF;
  min-width:290px; padding:0 32px; line-height:48px;
}
:deep(.el-tabs__active-bar){ display:none; }
:deep(.el-date-editor.el-input){ width:100%; }

/* —— 巡检类型：彩色圆点 + 文字 —— */
.type-wrap{ display:flex; flex-wrap:wrap; gap:8px 12px; }
.type-item{ display:inline-flex; align-items:center; gap:8px; }
.dot{
  width:10px; height:10px; border-radius:50%;
  background: var(--dot);
  box-shadow: 0 0 0 1px rgba(0,0,0,.06) inset, 0 1px 0 rgba(255,255,255,.6);
}
.type-text{ color:#304455; font-weight: 500; }

/* —— 让滚动条不显眼（仅在悬停时淡淡出现） —— */
.table-container{
  /* 仍可滚动 */
  overflow-y: auto;

  /* Firefox：默认不显示，悬停时再变细并上色 */
  scrollbar-width: none;          /* 默认隐藏 */
  scrollbar-gutter: stable;       /* 防止出现/消失导致的抖动 */
}
.table-container:hover{
  scrollbar-width: thin;          /* 悬停变细 */
  scrollbar-color: rgba(0,0,0,.28) transparent;
}

/* WebKit(Chromium/Edge/Chrome/Safari)：用全局选择器配合 scoped */
:global(.table-container::-webkit-scrollbar){
  width: 6px; height: 6px;
}
:global(.table-container::-webkit-scrollbar-track){
  background: transparent;
}
:global(.table-container::-webkit-scrollbar-thumb){
  background-color: transparent;      /* 默认透明，看不见 */
  border-radius: 6px;
}
:global(.table-container:hover::-webkit-scrollbar-thumb){
  background-color: rgba(0,0,0,.22);  /* 悬停时淡淡出现 */
}
:global(.table-container::-webkit-scrollbar-thumb:active){
  background-color: rgba(0,0,0,.35);  /* 拖动时稍深 */
}

</style>
