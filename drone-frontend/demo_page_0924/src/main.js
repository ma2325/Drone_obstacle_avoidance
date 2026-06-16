// src/main.js
// ⚠️ 在使用 Cesium 之前设置 BASE_URL
window.CESIUM_BASE_URL = '/cesium'

// Cesium UI 样式（放最前，避免被覆盖）
import 'cesium/Build/Cesium/Widgets/widgets.css'

import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import router from './router'

//3D小窗
import '@google/model-viewer'

// ====== 周任务 seed：只在应用启动时灌入一次 ======
import weeklySeed from '@/test-data/taskData_week.json'
import { bootstrapWeeklySeed, getWeekKey } from '@/shared/routeWeekly'

//刷新时是否回到初始数据（true=刷新重置；false=刷新也保留派发/编辑后的结果）
const RESET_WEEKLY_ON_RELOAD = true

// === 刷新时按需清理本地数据（不影响其他站点数据）===
;(function resetAppLocalDataOnRefresh() {
  try {
    // 只在需要“刷新回到初设”时清掉 Weekly 相关键
    if (RESET_WEEKLY_ON_RELOAD) {
      localStorage.removeItem('ROUTE_WEEKLY_STORE')
      // 清理周推送缓存前缀
      const del = []
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i)
        if (k && k.startsWith('airport_push_')) del.push(k)
      }
      del.forEach(k => localStorage.removeItem(k))
    }

    // 其余模块清理
    const KEYS = [
      'inspectionTasks',
      'executionData',
      'dayProgressV1',
      'dayProgressSyncedIdsV1',
      'droneList',
    ]
    KEYS.forEach(k => localStorage.removeItem(k))
  } catch { /* 忽略本地存储异常 */ }
})()

// === 在挂载应用前，把 seed 灌到本地（只跑一次）===
bootstrapWeeklySeed(weeklySeed, {
  weekKey: getWeekKey(),
  resetOnReload: RESET_WEEKLY_ON_RELOAD
})

// === 创建并挂载应用 ===
const app = createApp(App)
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.mount('#app')
