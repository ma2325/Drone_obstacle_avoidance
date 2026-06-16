<script setup>
import {
  HomeFilled,
  Place,
  Cpu,
  MapLocation,
  List,
  Clock,
  Setting,
  ArrowDown
} from '@element-plus/icons-vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

/** 只缓存 RouteShell（它内部用 v-show 切 MapView/Airport/Airspace） */
const cachedViews = computed(() => ['RouteShell'])
const AUTH_STORAGE_KEY = 'uav-auth-user'

const ROLE_LABELS = {
  admin: '管理员',
  dispatcher: '调度员',
  observer: '观察员'
}

function loadAuthUser() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (!parsed.username || !parsed.role) return null
    return parsed
  } catch {
    return null
  }
}

function saveAuthUser(user) {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user))
  } catch {}
}

const currentUser = ref(loadAuthUser())
const loginDialogVisible = ref(false)
const loginForm = ref({
  username: '',
  password: '',
  role: 'dispatcher'
})

const isLoggedIn = computed(() => !!currentUser.value)
const canAccessSystem = computed(() => currentUser.value?.role === 'admin')
const displayUserName = computed(() => currentUser.value?.displayName || currentUser.value?.username || '未登录')
const displayUserRole = computed(() => ROLE_LABELS[currentUser.value?.role] || '访客')

/** 全局兜底事件监听：AirportTask2 等处用 window.dispatchEvent 也能生效 */
const router = useRouter()
const simButtonAnimating = ref(false)
let simButtonTimer = null

function openLoginDialog(preferRole = 'dispatcher') {
  loginForm.value = {
    username: '',
    password: '',
    role: preferRole
  }
  loginDialogVisible.value = true
}

function submitLogin() {
  const username = (loginForm.value.username || '').trim()
  const password = (loginForm.value.password || '').trim()
  const role = loginForm.value.role

  if (!username) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!password) {
    ElMessage.warning('请输入密码')
    return
  }

  const user = {
    username,
    displayName: username,
    role,
    lastLoginAt: new Date().toISOString()
  }
  currentUser.value = user
  saveAuthUser(user)
  loginDialogVisible.value = false
  ElMessage.success(`登录成功，当前身份：${ROLE_LABELS[role] || role}`)
}

function handleLogout() {
  currentUser.value = null
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY)
  } catch {}
  if (String(router.currentRoute.value.path || '').startsWith('/system')) {
    router.push('/home')
  }
  ElMessage.success('已退出登录')
}

function handleUserCommand(command) {
  if (command === 'login') {
    openLoginDialog('dispatcher')
    return
  }
  if (command === 'switch') {
    openLoginDialog(currentUser.value?.role || 'dispatcher')
    return
  }
  if (command === 'logout') {
    handleLogout()
  }
}

function handleMenuSelect(index) {
  if ((index === '/system/user' || index === '/system/role') && !canAccessSystem.value) {
    ElMessage.warning('系统管理仅管理员可访问，请先登录管理员账号')
    openLoginDialog('admin')
  }
}

const triggerVirtualSimulation = () => {
  simButtonAnimating.value = true
  if (simButtonTimer) clearTimeout(simButtonTimer)
  simButtonTimer = setTimeout(() => {
    simButtonAnimating.value = false
  }, 420)

  // 仅用于演示视频的视觉入口，不触发真实仿真逻辑
  window.dispatchEvent(
    new CustomEvent('virtual-simulation-clicked', {
      detail: { time: Date.now() }
    })
  )
}

const handleRouteShellAction = (e) => {
  const evt = e?.detail
  if (!evt || !evt.type) return

  // 统一处理“从 AirportTask2 查看航线” → 进入 /route?view=map
  if (evt.type === 'open-map-from-airport') {
    const d = evt.data || {}
    router.push({
      path: '/route',
      query: {
        view: 'map',
        type: d.mapType || (d.preset3dKey ? '预设航线' : '航点飞行'),
        taskId: d.taskId || '',
        startStation: d.startStation || '',
        preset3d: d.preset3dKey || d.preset || '',
        restore: (typeof d.restore === 'boolean' ? d.restore : !d.preset3dKey) ? '1' : '0',
        lock: (typeof d.lock === 'boolean' ? d.lock : !!d.preset3dKey) ? '1' : '0'
      }
    })
    return
  }

  // 进入空域编辑
  if (evt.type === 'open-map-from-airspace' || evt.type === 'open-airspace') {
    router.push({ path: '/route', query: { view: 'airspace' } })
    return
  }

  // 其它：回到任务编排
  if (evt.type === 'open-airport-task') {
    router.push({ path: '/route', query: { view: 'airport' } })
    return
  }
}

onMounted(() => {
  window.addEventListener('route-shell-action', handleRouteShellAction)
})
onUnmounted(() => {
  window.removeEventListener('route-shell-action', handleRouteShellAction)
  if (simButtonTimer) clearTimeout(simButtonTimer)
})
</script>

<template>
  <div class="common-layout">
    <el-container style="height: 100vh">
      <!-- 顶部导航栏 -->
      <el-header class="header">
  <!-- 左侧部分，包含图标和标题 -->
  <div class="header-left">
    <div class="legend-row">
      <img src="/icons/drone.svg"  class="legend-icon" />
    </div>
    <div class="header-title">高速公路无人机控制系统</div>
  </div>
  
  <!-- 右侧部分，包含用户信息 -->
  <div class="user-section">
    <el-dropdown @command="handleUserCommand">
      <span class="el-dropdown-link">
        {{ displayUserName }}
        <span class="user-role">{{ displayUserRole }}</span>
        <el-icon class="el-icon--right"><arrow-down /></el-icon>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item v-if="!isLoggedIn" command="login">登录</el-dropdown-item>
          <template v-else>
            <el-dropdown-item command="switch">切换账号</el-dropdown-item>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </template>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</el-header>


      <el-container>
        <!-- 左侧菜单栏 -->
        <el-aside width="150px" class="left-sidebar" style="background-color: #1E1E2D; color: white;">
          <div class="sidebar-content">
            <el-menu
              active-text-color="#ffd04b"
              background-color="#1E1E2D"
              class="el-menu-vertical"
              text-color="#fff"
              style="border-right: none"
              :default-active="$route.path"
              :default-openeds="['route','history','task','device','system']" 
              @select="handleMenuSelect"
              :router="true"
            >
              <el-menu-item index="/home">
                <el-icon><HomeFilled /></el-icon>
                <span>首页</span>
              </el-menu-item>

              <el-menu-item index="/screen/uav">
                <el-icon><Place /></el-icon>
                <span>无人机大屏</span>
              </el-menu-item>

              <el-sub-menu index="route">
                <template #title>
                  <el-icon><MapLocation /></el-icon>
                  <span>航线空城</span>
                </template>
                <el-menu-item index="/route/plan">航线任务</el-menu-item>
                <el-menu-item index="/route/airspace">空域管理</el-menu-item>
              </el-sub-menu>

              <el-sub-menu index="history">
                <template #title>
                  <el-icon><Clock /></el-icon>
                  <span>成果数据</span>
                </template>
                <el-menu-item index="/history/airport">历史任务</el-menu-item>
                <el-menu-item index="/history/stats">数据统计</el-menu-item>
                <!-- <el-menu-item index="/history/statistics">成果统计</el-menu-item> -->
              </el-sub-menu>

              <el-sub-menu index="task">
                <template #title>
                  <el-icon><List /></el-icon>
                  <span>任务管理</span>
                </template>
                <el-menu-item index="/task/airport">每日任务</el-menu-item>
                <!-- <el-menu-item index="/task/completion">任务状态</el-menu-item> -->
              </el-sub-menu>

              <el-sub-menu index="device">
                <template #title>
                  <el-icon><Cpu /></el-icon>
                  <span>设备管理</span>
                </template>
                <el-menu-item index="/device/airport">机场设备</el-menu-item>
                <el-menu-item index="/device/drone">无人机</el-menu-item>
              </el-sub-menu>

              <el-sub-menu index="system">
                <template #title>
                  <el-icon><Setting /></el-icon>
                  <span>系统管理</span>
                </template>
                <el-menu-item index="/system/user" :disabled="!canAccessSystem">用户管理</el-menu-item>
                <el-menu-item index="/system/role" :disabled="!canAccessSystem">角色管理</el-menu-item>
                <el-menu-item v-if="!canAccessSystem" index="/system/no-access" disabled>
                  登录管理员后可用
                </el-menu-item>
              </el-sub-menu>
            </el-menu>

            <div class="virtual-entry-wrap">
              <button
                type="button"
                class="virtual-entry-btn"
                :class="{ 'is-clicking': simButtonAnimating }"
                @click="triggerVirtualSimulation"
              >
                <span class="entry-dot"></span>
                虚拟仿真实验
              </button>
            </div>
          </div>
        </el-aside>

        <!-- 主内容区 -->
        <el-main style="padding: 0px; background-color: #f0f2f5;">
          <router-view v-slot="{ Component, route }">
            <!-- 只缓存 RouteShell；用 route.name 作为 key，避免 query 变化导致销毁重建 -->
            <keep-alive :include="cachedViews">
              <component :is="Component" :key="route.name" />
            </keep-alive>
          </router-view>
        </el-main>
      </el-container>

      <el-dialog v-model="loginDialogVisible" title="账号登录" width="420px">
        <el-form :model="loginForm" label-width="86px">
          <el-form-item label="用户名">
            <el-input v-model="loginForm.username" placeholder="请输入用户名" clearable />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="loginForm.password"
              placeholder="请输入密码"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="loginForm.role" style="width: 100%;">
              <el-option label="管理员" value="admin" />
              <el-option label="调度员" value="dispatcher" />
              <el-option label="观察员" value="observer" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="loginDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitLogin">登录</el-button>
        </template>
      </el-dialog>
    </el-container>
  </div>
</template>

<style lang="css">
html, body {
  height: 100%;
  margin: 0;
}

.common-layout {
  height: 100%;
}

.el-container {
  height: 100%;
}

.el-menu-vertical {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.left-sidebar {
  display: flex;
  flex-direction: column;
}

.sidebar-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.virtual-entry-wrap {
  padding: 10px 10px 14px;
  background: linear-gradient(180deg, rgba(30, 30, 45, 0.2) 0%, rgba(30, 30, 45, 0.95) 35%);
}

.virtual-entry-btn {
  width: 100%;
  height: 36px;
  border: 1px solid rgba(255, 217, 46, 0.55);
  border-radius: 8px;
  color: #ffd92e;
  background: linear-gradient(135deg, rgba(255, 217, 46, 0.15), rgba(255, 217, 46, 0.04));
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.2s ease, background 0.2s ease;
  box-shadow: inset 0 0 0 1px rgba(255, 217, 46, 0.08), 0 6px 16px rgba(255, 217, 46, 0.16);
}

.virtual-entry-btn:hover {
  background: linear-gradient(135deg, rgba(255, 217, 46, 0.28), rgba(255, 217, 46, 0.08));
  box-shadow: inset 0 0 0 1px rgba(255, 217, 46, 0.2), 0 8px 18px rgba(255, 217, 46, 0.22);
}

.virtual-entry-btn:active {
  transform: scale(0.97);
}

.virtual-entry-btn.is-clicking {
  animation: sim-click-burst 420ms cubic-bezier(0.22, 0.61, 0.36, 1);
}

.entry-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ffd92e;
  box-shadow: 0 0 8px rgba(255, 217, 46, 0.9);
}

@keyframes sim-click-burst {
  0% {
    transform: scale(1);
    box-shadow: inset 0 0 0 1px rgba(255, 217, 46, 0.08), 0 6px 16px rgba(255, 217, 46, 0.16);
  }
  35% {
    transform: scale(0.94);
    box-shadow: inset 0 0 0 1px rgba(255, 217, 46, 0.3), 0 0 0 6px rgba(255, 217, 46, 0.16);
  }
  100% {
    transform: scale(1);
    box-shadow: inset 0 0 0 1px rgba(255, 217, 46, 0.12), 0 8px 18px rgba(255, 217, 46, 0.2);
  }
}

.el-main {
  height: 100%;
  overflow: auto; /* 添加滚动条 */
}

.el-dropdown-link {
  display: flex;
  align-items: center;
}

/* 子菜单缩进样式 */
.el-menu-item,
.el-sub-menu__title {
  display: flex;
  align-items: center;
  font-family: "Roboto", "Montserrat", sans-serif;
  transition: all 0.3s ease;



}

.el-menu-item .el-icon,
.el-sub-menu__title .el-icon {
  flex-shrink: 0; /* 防止图标被压缩 */
  margin-right: 10px;
}

/* header 样式 */
.header {
  background-color: #1E1E2D;
  color: white;
  display: flex;
  justify-content: space-between; /* 让左右两部分分别靠左和靠右 */
  align-items: center;
  padding: 10px;
}

/* 左侧部分的容器 */
.header-left {
  display: flex;
  align-items: center;
  justify-content: flex-start; /* 左对齐 */
}

/* 图标和文本行样式 */
.legend-row {
  display: flex;
  align-items: center;
  margin-right: 10px; /* 图标和标题之间的间距 */
}

/* 图标样式 */
.legend-icon {
  width: 35px; /* 图标大小 */
  height: 35px; /* 图标大小 */
  margin-left: 10px; /* 图标和文本之间的间距 */
}

/* 标题样式 */
.header-title {
  font-size: 24px;
  font-weight: bold;
  margin-left: 5px; /* 图标和标题之间的间距 */
}

/* 右侧用户菜单部分 */
.user-section {
  margin-left: auto; /* 将用户部分推到右边 */
}

/* 下拉菜单链接样式 */
.el-dropdown-link {
  color: white;
  cursor: pointer;
  gap: 8px;
}

.user-role {
  font-size: 12px;
  color: #cfd3e6;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  line-height: 1.2;
}

/* 下拉菜单图标样式 */
.el-icon--right {
  margin-left: 20px;
}

/* 子菜单标题（一级项） */
.el-sub-menu__title {
  background-color: #1E1E2D !important; 
  color: #fff !important;              
  font-weight: 700;                    
  font-size: 16px;                      
  padding: 10px 12px !important;        
  transition: all 0.3s ease;
}

.el-sub-menu__title:hover {
  background-color: #2a2a3a !important;
}


.el-menu-item:hover {
  background-color: #344055 !important;
  color: #fff !important;
}


.el-menu-item.is-active {
  color: #ffd92e !important;
  font-weight: bold;
}


</style>
