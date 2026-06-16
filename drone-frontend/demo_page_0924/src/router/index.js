// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

// —— 顶层菜单视图 —— //
import DeviceView from '../components/menu/DeviceView.vue'
import TaskView from '../components/menu/TaskView.vue'
import SystemView from '../components/menu/SystemView.vue'
import HomeView from '../components/menu/HomeView.vue'
import HistoryView from '../components/menu/HistoryView.vue'

// —— 其它子页 —— //
import DeviceDetail from '../components/Home/DeviceDetail.vue'
import AirportTask from '../components/History/AirportTask.vue'
import TaskExecution from '../components/TaskLine/TaskExecution.vue'
import AirportTaskStats from '../components/History/AirportTaskStats.vue'

// —— 设备子页 —— //
// import DeviceView from '../components/menu/DeviceView.vue'
import DeviceAirport from '../components/Device/DeviceAirport.vue'
import DeviceDrone   from '../components/Device/DeviceDrone.vue'

// —— 系統子页 —— //
import SystemUser from '../components/System/SystemUser.vue'
import SystemRole from '../components/System/SystemRole.vue'

// —— 航线相关（RouteShell 作为壳，内部切换 RoutePlan / MapView / AirportTask2 / Airspace） —— //
import RouteShell from '../components/TaskLine/RouteShell.vue'
import AirportTask2 from '../components/TaskLine/AirportTask2.vue'
import TaskHistory from '../components/TaskLine/TaskHistory.vue'

// —— 无人机连接测试 —— //
import DroneTest from '../components/DroneTest.vue'
import UavBigScreen from '../views/UavBigScreen.vue'


const routes = [
  // 默认首页
  { path: '/', redirect: '/home' },

  // 🚁 无人机连接测试页面（独立路由）
  {
    path: '/drone-test',
    name: 'DroneTest',
    component: DroneTest
  },

  // 无人机可视化大屏
  {
    path: '/screen/uav',
    name: 'UavBigScreen',
    component: UavBigScreen
  },

  // 首页 + 设备详情
  {
    path: '/home',
    name: 'Home',
    component: HomeView,
    children: [
      {
        path: 'device/:id',
        name: 'DeviceDetail',
        component: DeviceDetail,
        props: route => ({ deviceId: route.params.id, ...route.query })
      }
    ]
  },

  // 设备
  {
    path: '/device',
    name: 'Device',
    component: DeviceView,          // 设备区的“壳”，内部必须有 <router-view />
    redirect: '/device/airport',    // 默认进“机场设备”
    children: [
      { path: 'airport', name: 'DeviceAirport', component: DeviceAirport },
      { path: 'drone',   name: 'DeviceDrone',   component: DeviceDrone }
    ]
  },

  /**
   * 航线：统一进入 RouteShell，由它内部根据 query.view 渲染：
   *   view=plan      -> RoutePlan
   *   view=map       -> MapView
   *   view=airspace  -> Airspace
   *   view=airport   -> AirportTask2
   */
  { path: '/route', name: 'RouteShell', component: RouteShell },

  // 深链别名：航线任务
  {
    path: '/route/plan',
    redirect: to => ({ path: '/route', query: { ...to.query, view: 'plan' } })
  },

  // ✅ 深链别名：空域管理（侧边栏点击 /route/airspace 即可）
  {
    path: '/route/airspace',
    redirect: to => ({ path: '/route', query: { ...to.query, view: 'airspace' } })
  },

  //（可选）深链别名：直接进入 AirportTask2
  {
    path: '/route/airport',
    redirect: to => ({ path: '/route', query: { ...to.query, view: 'airport' } })
  },

  // 深链别名：直接进入 MapView，并透传参数
  {
    path: '/route/map/:type?/:taskId?/:startStation?',
    redirect: to => {
      const { type, taskId, startStation } = to.params
      return {
        path: '/route',
        query: {
          ...to.query,
          view: 'map',
          type: type || '',
          taskId: taskId || '',
          startStation: startStation || ''
        }
      }
    }
  },

  // 任务（如仍保留）
  {
    path: '/task',
    name: 'Task',
    component: TaskView,
    children: [
      { path: 'airport', name: 'AirportTask2', component: AirportTask2 },
      { path: 'completion', name: 'TaskCompletion', component: TaskExecution, props: true },
      { path: 'datahistory', name: 'TaskHistory', component: TaskHistory, props: true }
    ]
  },

  // 历史
  {
    path: '/history',
    name: 'History',
    component: HistoryView,
    children: [
      { path: 'airport', name: 'AirportTask', component: AirportTask },
      { path: 'stats', name: 'AirportTaskStats', component: AirportTaskStats }
    ]
  },

  // 系统
  {
    path: '/system',
    name: 'System',
    component: SystemView,            // 系统管理的“壳”，内部必须有 <router-view />
    redirect: '/system/user',         // 默认进“用户管理”
    children: [
      { path: 'user', name: 'SystemUser', component: SystemUser },
      { path: 'role', name: 'SystemRole', component: SystemRole }
    ]
  },


  /**
   * 旧地址兼容：/map/:type(/:taskId?/:startStation?) -> 统一走到 /route?view=map
   * 例：/map/预设航线/xxx?preset3d=route_1&restore=1
   */
  {
    path: '/map/:type?/:taskId?/:startStation?',
    redirect: to => {
      const { type, taskId, startStation } = to.params
      return {
        path: '/route',
        query: {
          ...to.query,
          view: 'map',
          type: type || '',
          taskId: taskId || '',
          startStation: startStation || ''
        }
      }
    }
  },

  // 兜底
  { path: '/:pathMatch(.*)*', redirect: '/home' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ left: 0, top: 0 })
})

const AUTH_STORAGE_KEY = 'uav-auth-user'

router.beforeEach((to) => {
  if (!String(to.path || '').startsWith('/system')) return true

  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY)
    const user = raw ? JSON.parse(raw) : null
    if (user?.role === 'admin') return true
  } catch {}

  return '/home'
})

export default router
