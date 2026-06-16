/**
 * src/shared/routeWeekly.js (hardened, weekday-expression enabled)
 * 统一“周库 + 航线Key(preset3d/route_xxx)分组”的存储与事件。
 */

const STORAGE_KEY = 'ROUTE_WEEKLY_STORE'
export const WEEKLY_EVENT = 'weekly-updated'
export const THRESHOLD_EVENT = 'airport-threshold'

/* -------------------------------- 工具 -------------------------------- */

const clone = (v) => JSON.parse(JSON.stringify(v ?? null))

/** 默认 Store */
function getDefaultStore() {
  return {
    config: { airportThreshold: 2 },
    catalog: [],
    weeks: {}
  }
}

/** 安全 JSON 解析：若解析结果不是“对象”，也回退成 fallback */
function safeParse(json, fallback) {
  try {
    const v = JSON.parse(json)
    if (v && typeof v === 'object' && !Array.isArray(v)) return v
    return clone(fallback)
  } catch {
    return clone(fallback)
  }
}

function writeStore(db) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(db))
  } catch {}
}

/** 读取并自修复（防止 localStorage = "null" / "undefined" / ""） */
function readStore() {
  const raw = localStorage.getItem(STORAGE_KEY)
  let db = safeParse(raw, getDefaultStore())

  // 兜底：再判一次，确保是对象
  if (!db || typeof db !== 'object' || Array.isArray(db)) {
    db = getDefaultStore()
  }
  if (!db.weeks || typeof db.weeks !== 'object' || Array.isArray(db.weeks)) {
    db.weeks = {}
  }
  if (!db.config || typeof db.config !== 'object' || Array.isArray(db.config)) {
    db.config = { airportThreshold: 2 }
  }
  if (!Array.isArray(db.catalog)) db.catalog = []

  // 动态补齐 catalog（收集所有已出现的 routeKey）
  const ids = new Set(db.catalog.map(c => c.route_id))
  Object.values(db.weeks).forEach((wk) => {
    if (wk && typeof wk === 'object') {
      Object.keys(wk.subset || {}).forEach(rid => ids.add(rid))
      Object.keys(wk.counts || {}).forEach(rid => ids.add(rid))
    }
  })
  db.catalog = Array.from(ids).sort().map(rid => {
    const hit = (db.catalog || []).find(c => c.route_id === rid)
    return hit || { route_id: rid, name: rid }
  })

  // 把修复后的内容写回，避免下次再坏
  writeStore(db)
  return db
}

/** 统一发全量快照 */
function broadcastSnapshot() {
  const snap = readStore()
  try {
    window.dispatchEvent(new CustomEvent(WEEKLY_EVENT, { detail: snap } ))
  } catch {}
}

/** 事件订阅（与之前保持一致） */
export function on(eventName, cb) {
  const h = (e) => cb(e?.detail)
  window.addEventListener(eventName, h)
  return () => window.removeEventListener(eventName, h)
}
export function addWeeklyListener(cb) { return on(WEEKLY_EVENT, cb) }
export function emitUpdated() { broadcastSnapshot() }

/** ISO 周 key: YYYY-Www（周一为周首） */
export function getWeekKey(date = new Date()) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const year = d.getUTCFullFullYear?.() ?? d.getUTCFullYear() // 兼容极旧环境
  const yearStart = new Date(Date.UTC(year, 0, 1))
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
  return `${year}-W${String(weekNo).padStart(2, '0')}`
}

/** 归一化 routeKey（兼容多种写法 → 统一为 route_数字） */
export function normalizeRouteId(x) {
  if (!x) return ''
  const raw = (typeof x === 'string')
    ? x
    : (x.preset3d || x.preset3dKey || x.route_id || x.routeId || '')
  if (typeof raw !== 'string') return ''

  // 标准：route_数字
  let m = raw.match(/^route_(\d+)$/i)
  if (m) return `route_${+m[1]}`

  // 变体：route3d_数字 / routex_数字
  m = raw.match(/^route(?:3d|x)?_(\d+)$/i)
  if (m) return `route_${+m[1]}`

  // 形如 R-001 / R001
  m = raw.match(/^R[-_]?0*(\d+)$/i)
  if (m) return `route_${+m[1]}`

  // 形如 X-7
  m = raw.match(/^X[-_]?0*(\d+)$/i)
  if (m) return `route_${+m[1]}`

  // 兜底：抓末尾数字
  m = raw.match(/(\d+)$/)
  if (m) return `route_${+m[1]}`

  return ''
}

/* ------------------------ 周→日期 工具 & exec_at 规范化 ------------------------ */

// 解析 'YYYY-Www' 得到该周「周一 00:00:00 UTC」
function weekStartOfKey(weekKey) {
  const m = String(weekKey || '').match(/^(\d{4})-W(\d{2})$/)
  if (!m) return null
  const year = +m[1], week = +m[2]
  // ISO：第一个周四所在周为第 1 周
  const jan4 = new Date(Date.UTC(year, 0, 4))
  const jan4Dow = jan4.getUTCDay() || 7 // 周一=1..周日=7
  const week1Mon = new Date(jan4); week1Mon.setUTCDate(jan4.getUTCDate() - (jan4Dow - 1))
  const d = new Date(week1Mon); d.setUTCDate(week1Mon.getUTCDate() + (week - 1) * 7)
  return d
}
function ymdUTC(d){
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth()+1).padStart(2,'0')
  const day = String(d.getUTCDate()).padStart(2,'0')
  return `${y}-${m}-${day}`
}
// 给定周 + 周几(1..7) + 偏移，返回 YYYY-MM-DD 字符串
function ymdOfWeekday(weekKey, weekday = 1, offset = 0){
  const base = weekStartOfKey(weekKey); if (!base) return ''
  const d = new Date(base); d.setUTCDate(base.getUTCDate() + (Number(weekday)-1) + (Number(offset)||0))
  return ymdUTC(d)
}
// 从 YYYY-MM-DD 求 ISO 周几（周一=1..周日=7）
function isoWeekdayFromYmd(ymd){
  const m = String(ymd||'').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return null
  const d = new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`)
  const w = d.getUTCDay()
  return w === 0 ? 7 : w
}

/**
 * 把“周几/表达式/日期”统一换算到指定周
 * 支持：
 *  - '1'..'7'、'周一'..'周日'、'mon'..'sun'
 *  - 带偏移：'3+1'、'@fri-2'、'mon+2'（@ 可有可无）
 *  - 直接日期：'YYYY-MM-DD'（rollToTargetWeek=true 时，平移到目标周的同周几）
 */
function normalizeExecAtForWeek(raw, weekKey, { rollToTargetWeek = true } = {}){
  if (raw == null || raw === '') return ''
  const s = String(raw).trim()

  // 1) 直接是日期
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    if (!rollToTargetWeek) return s
    const wd = isoWeekdayFromYmd(s)
    if (!wd) return s
    return ymdOfWeekday(weekKey, wd, 0)
  }

  // 2) 纯数字 1..7（可带前缀@ 和 偏移）
  let m = s.match(/^@?([1-7])([+-]\d+)?$/i)
  if (m) {
    const wd = +m[1]; const off = m[2] ? +m[2] : 0
    return ymdOfWeekday(weekKey, wd, off)
  }

  // 3) 中文/英文周几（可带偏移）
  const dict = {
    '周一':1,'周二':2,'周三':3,'周四':4,'周五':5,'周六':6,'周日':7,'周天':7,
    'mon':1,'monday':1,'tue':2,'tues':2,'tuesday':2,'wed':3,'weds':3,'wednesday':3,
    'thu':4,'thur':4,'thurs':4,'thursday':4,'fri':5,'friday':5,
    'sat':6,'saturday':6,'sun':7,'sunday':7
  }
  m = s.match(/^@?\s*([a-zA-Z\u5468\u4e00-\u9fa5]+)\s*([+-]\d+)?$/)
  if (m){
    const key = m[1].toLowerCase()
    const wd = dict[key]
    const off = m[2] ? +m[2] : 0
    if (wd) return ymdOfWeekday(weekKey, wd, off)
  }

  // 其它情况：按原样返回（兼容旧数据）
  return s
}

/* ------------------------------- 结构保障 ------------------------------- */
function ensureWeek(db, wkKey) {
  if (!db.weeks[wkKey]) db.weeks[wkKey] = { counts: {}, subset: {}, rules: {} }
  if (!db.weeks[wkKey].counts) db.weeks[wkKey].counts = {}
  if (!db.weeks[wkKey].subset) db.weeks[wkKey].subset = {}
  if (!db.weeks[wkKey].rules || typeof db.weeks[wkKey].rules !== 'object') db.weeks[wkKey].rules = {}
  return db.weeks[wkKey]
}
function ensureRoute(wk, routeId) {
  if (!wk.counts[routeId]) wk.counts[routeId] = { count: 0, updatedAt: Date.now() }
  if (!wk.subset[routeId]) wk.subset[routeId] = []
}

/* -------------------------- 计数（按 route） --------------------------- */
export function getCount(weekKey = getWeekKey(), routeId) {
  if (!routeId) return 0
  const db = readStore()
  return db.weeks?.[weekKey]?.counts?.[routeId]?.count || 0
}
export function setCount(weekKey = getWeekKey(), routeId, count) {
  if (!routeId) return
  const db = readStore()
  const wk = ensureWeek(db, weekKey)
  ensureRoute(wk, routeId)
  wk.counts[routeId].count = Math.max(0, Number(count) || 0)
  wk.counts[routeId].updatedAt = Date.now()
  writeStore(db); broadcastSnapshot()
}
export function incCount(weekKey = getWeekKey(), routeId, delta = 1) {
  if (!routeId) return
  const db = readStore()
  const wk = ensureWeek(db, weekKey)
  ensureRoute(wk, routeId)
  const cur = wk.counts[routeId].count || 0
  wk.counts[routeId].count = Math.max(0, cur + (Number(delta) || 0))
  wk.counts[routeId].updatedAt = Date.now()
  writeStore(db); broadcastSnapshot()
}
/** 给 TaskExecution 用：返回 { [routeKey]: count } */
export function listCountsByRoute(weekKey = getWeekKey()) {
  const db = readStore()
  const wk = db.weeks?.[weekKey]
  if (!wk) return {}
  const out = {}
  Object.keys(wk.counts || {}).forEach(rid => out[rid] = wk.counts[rid]?.count || 0)
  Object.keys(wk.subset || {}).forEach(rid => {
    if (!(rid in out)) out[rid] = (wk.subset[rid] || []).length
  })
  return out
}
export function recalcCountsFromSubset(weekKey = getWeekKey()) {
  const db = readStore()
  const wk = db.weeks?.[weekKey]
  if (!wk) return
  const now = Date.now()
  Object.keys(wk.subset || {}).forEach(rid => {
    const n = (wk.subset[rid] || []).length
    wk.counts[rid] = { count: n, updatedAt: now }
  })
  writeStore(db); broadcastSnapshot()
}

/* ------------------ 子集（AirportTask2 列表 — 周内） ------------------ */
function sanitizeSubsetItem(t, routeId) {
  // 自动兜底 taskType：只有点位类→点位扫描，否则线路扫描
  const pointTypes = ['桥梁巡检','边坡巡检']
  const isPointOnly = Array.isArray(t.type) && t.type.length > 0 && t.type.every(x => pointTypes.includes(x))

  return {
    id: String(t.id || `${routeId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`),
    name: String(t.name || ''),
    preset3d: routeId,
    preset3dKey: routeId,

    taskType: t.taskType || (isPointOnly ? '点位扫描' : '线路扫描'),
    type: Array.isArray(t.type) ? t.type : (t.type ? [t.type] : []),

    route_id: t.route_id ?? t.routeCode ?? routeId,
    route: t.route ?? '',
    takeoff: t.takeoff ?? '',
    turnaround: t.turnaround ?? '',
    time_window: t.time_window ?? t.timeWindow ?? [],
    flightCount: t.flightCount ?? t.flights ?? '',
    expectedFinish: t.expectedFinish ?? t.estimatedHours ?? '',
    actualFinish: t.actualFinish ?? '',
    drone: t.drone ?? '',
    drone_id: t.drone_id ?? '',

    status: t.status ?? '',
    executionTime: t.executionTime ?? '',
    exec_at: t.exec_at ?? t.execAt ?? '',        // ✅ 用于“分日完成”统计
    customExecutionTime: t.customExecutionTime ?? '',
    executionTimeDisplay: t.executionTimeDisplay ?? '',

    createdAt: t.createdAt ?? t.startTime ?? '',

    priority: t.priority ?? '',
    exceptionRecord: t.exceptionRecord ?? '',
    recognitionCount: t.recognitionCount ?? '',
    accuracyMetric: t.accuracyMetric ?? '',
    timeWindowCompliance: t.timeWindowCompliance ?? '',
    completionRate: t.completionRate ?? '',
    flightLog: t.flightLog ?? '',
    batteryUsageCount: t.batteryUsageCount ?? '',
    deviceHealth: t.deviceHealth ?? ''
  }
}

export function listSubsetByRoute(weekKey = getWeekKey(), routeId, sortDesc = false) {
  if (!routeId) return []
  const db = readStore()
  const arr = clone(db.weeks?.[weekKey]?.subset?.[routeId] || [])
  if (sortDesc) arr.sort((a,b) => String(b.createdAt||'').localeCompare(String(a.createdAt||'')))
  return arr
}
export function listAirportSubset(weekKey = getWeekKey(), sortDesc = false) {
  const db = readStore()
  const wk = db.weeks?.[weekKey]
  if (!wk) return []
  const arr = Object.values(wk.subset || {}).flat()
  const out = clone(arr)
  if (sortDesc) out.sort((a,b) => String(b.createdAt||'').localeCompare(String(a.createdAt||'')))
  return out
}

export function upsertSubsetItem(weekKey = getWeekKey(), routeId, rawItem) {
  if (!routeId || !rawItem) return null
  const db = readStore()
  const wk = ensureWeek(db, weekKey)
  ensureRoute(wk, routeId)
  const list = wk.subset[routeId]
  const item = sanitizeSubsetItem(rawItem, routeId)
  const idx = list.findIndex(x => x.id === item.id)
  if (idx === -1) {
    list.push(item)
    const cur = wk.counts[routeId]?.count || 0
    wk.counts[routeId] = { count: cur + 1, updatedAt: Date.now() }
  } else {
    list.splice(idx, 1, item)
    wk.counts[routeId].updatedAt = Date.now()
  }
  writeStore(db); broadcastSnapshot()
  return item
}

export function replaceSubsetForRoute(weekKey = getWeekKey(), routeId, rawItems = []) {
  if (!routeId) return []
  const db = readStore()
  const wk = ensureWeek(db, weekKey)
  ensureRoute(wk, routeId)
  const items = rawItems.map(r => sanitizeSubsetItem(r, routeId))
  wk.subset[routeId] = items
  wk.counts[routeId] = { count: items.length, updatedAt: Date.now() }
  writeStore(db); broadcastSnapshot()
  return items
}

export function deleteSubsetItem(weekKey = getWeekKey(), routeId, id) {
  if (!routeId || !id) return false
  const db = readStore()
  const wk = db.weeks?.[weekKey]
  if (!wk || !wk.subset?.[routeId]) return false
  const list = wk.subset[routeId]
  const idx = list.findIndex(x => x.id === id)
  if (idx === -1) return false
  list.splice(idx, 1)
  const cur = wk.counts?.[routeId]?.count || 0
  wk.counts[routeId] = { count: Math.max(0, cur - 1), updatedAt: Date.now() }
  writeStore(db); broadcastSnapshot()
  return true
}

export function listRoutesForWeek(weekKey = getWeekKey()) {
  const db = readStore()
  const wk = db.weeks?.[weekKey]
  if (!wk) return []
  const a = Object.keys(wk.counts || {})
  const b = Object.keys(wk.subset || {})
  return Array.from(new Set([...a, ...b])).sort()
}

/* --------------------------- 规则与导入 --------------------------- */
/** 从快照/后端返回写入某周规则 */
export function setWeekRules(weekKey = getWeekKey(), rules = {}) {
  const db = readStore()
  const wk = ensureWeek(db, weekKey)
  wk.rules = (rules && typeof rules === 'object' && !Array.isArray(rules)) ? rules : {}
  writeStore(db); broadcastSnapshot()
}

/** 从 items[] 导入子集 */
export function importAirportJson(items = [], { weekKey = getWeekKey(), mode = 'replace' } = {}) {
  const bucket = new Map()
  items.forEach(raw => {
    const rid = normalizeRouteId(raw)
    if (!rid) return
    const item = sanitizeSubsetItem(raw, rid)
    if (!bucket.has(rid)) bucket.set(rid, [])
    bucket.get(rid).push(item)
  })
  bucket.forEach((arr, rid) => {
    if (mode === 'replace') replaceSubsetForRoute(weekKey, rid, arr)
    else arr.forEach(it => upsertSubsetItem(weekKey, rid, it))
  })
  // 调试：看总数与保留条数
  try {
    const total = Array.isArray(items) ? items.length : 0
    let kept = 0; bucket.forEach(a => kept += a.length)
    console.log('[importAirportJson]', 'total=', total, 'kept=', kept, 'routes=', Array.from(bucket.keys()))
  } catch {}
  broadcastSnapshot()
}

/** 直接导入“周库快照”（支持 exec_at = 周几/表达式/日期） */
export function importWeeklySnapshot(snapshot = {}, { weekKey = getWeekKey(), mode = 'merge' } = {}) {
  if (!snapshot || typeof snapshot !== 'object' || !snapshot.weeks) return
  // 优先取当前周，其次取快照里第一周
  const wkKey = snapshot.weeks[weekKey] ? weekKey : Object.keys(snapshot.weeks)[0]
  const wkSnap = snapshot.weeks[wkKey]
  if (!wkSnap) return

  const rules = wkSnap.rules || {}
  const subset = wkSnap.subset || {}

  // 扁平化子集：补齐 preset3d = routeKey，并将 exec_at 规范到 wkKey
  const items = []
  Object.keys(subset).forEach(routeKey => {
    const arr = Array.isArray(subset[routeKey]) ? subset[routeKey] : []
    arr.forEach(t => {
      const preset = t.preset3d ?? routeKey
      const srcExec = t.exec_at ?? t.execAt ?? t.executionTime ?? ''
      const execAt = normalizeExecAtForWeek(srcExec, wkKey, { rollToTargetWeek: true })
      items.push({ ...t, preset3d: preset, exec_at: execAt })
    })
  })

  // 先写规则，再导入子集
  setWeekRules(wkKey, rules)
  importAirportJson(items, { weekKey: wkKey, mode })

  try {
    console.log('[importWeeklySnapshot]', 'week=', wkKey, 'rules=', Object.keys(rules).length, 'items=', items.length)
  } catch {}
}

export function getRouteMetrics(weekKey = getWeekKey()) {
  const metrics = {}
  listRoutesForWeek(weekKey).forEach(rid => {
    const arr = listSubsetByRoute(weekKey, rid)
    const m = { count: arr.length, expectedHrs: 0, actualHrs: 0, flights: 0 }
    arr.forEach(t => {
      m.expectedHrs += Number(t.expectedFinish) || 0
      m.actualHrs   += Number(t.actualFinish)   || 0
      m.flights     += Number(t.flightCount)    || 0
    })
    metrics[rid] = m
  })
  return metrics
}

// 全部周数据显示
export function importWeeklySnapshotAll(snapshot = {}, { mode = 'merge' } = {}) {
  if (!snapshot || typeof snapshot !== 'object' || !snapshot.weeks) return
  Object.keys(snapshot.weeks).forEach(wk =>
    importWeeklySnapshot(snapshot, { weekKey: wk, mode })
  )
}

/* ------------------------------ 兼容 API ------------------------------ */
export function addTaskToWeek(task, weekKey = getWeekKey()) {
  const rid = normalizeRouteId(task) || normalizeRouteId(task?.route_id)
  if (!rid) return null
  return upsertSubsetItem(weekKey, rid, { ...task, route_id: rid })
}
export function removeTaskFromWeek(taskId, routeId, weekKey = getWeekKey()) {
  const rid = normalizeRouteId(routeId) || normalizeRouteId({ route_id: routeId })
  if (!rid) return false
  return deleteSubsetItem(weekKey, rid, taskId)
}
export function setAirportThreshold(value) {
  const db = readStore()
  const v = Number(value)
  db.config.airportThreshold = Number.isFinite(v) && v >= 0 ? v : 0
  writeStore(db)
  try { window.dispatchEvent(new CustomEvent(THRESHOLD_EVENT, { detail: db.config.airportThreshold })) } catch {}
  broadcastSnapshot()
}
export function loadStore() { return readStore() }

/* -------------------------------- 清理 -------------------------------- */
export function clearAll() { writeStore(getDefaultStore()); broadcastSnapshot() }
export function clearWeek(weekKey = getWeekKey()) {
  const db = readStore()
  if (db.weeks?.[weekKey]) delete db.weeks[weekKey]
  writeStore(db); broadcastSnapshot()
}

/** 首次/整页刷新时灌入一份种子数据。只在应用启动时调用一次 */
export function bootstrapWeeklySeed(seed, { weekKey = getWeekKey(), resetOnReload = true } = {}) {
  // resetOnReload=true 表示每次整页刷新都回到初设；如果希望刷新后也保留派发结果，改成 false
  if (resetOnReload) {
    clearAll();                  // 清空存储（只在整页刷新时执行一次）
  }
  importWeeklySnapshot(seed, { weekKey, mode: 'merge' })  // 写入 seed 并广播
  emitUpdated()                 // 再广播一次，确保各页面能立刻收到
}

// 默认导出里暴露清单
export default {
  // 周
  getWeekKey,
  listRoutesForWeek,
  listCountsByRoute,
  listWeeks: () => Object.keys(readStore().weeks || {}).sort(),

  // 子集
  listSubsetByRoute,
  listAirportSubset,
  upsertSubsetItem,
  replaceSubsetForRoute,
  deleteSubsetItem,

  // 导入/聚合
  importAirportJson,
  importWeeklySnapshot,
  getRouteMetrics,

  // 计数
  getCount, setCount, incCount, recalcCountsFromSubset,

  // 事件/工具
  on, addWeeklyListener, emitUpdated, normalizeRouteId, loadStore, setAirportThreshold, setWeekRules,

  // 兼容
  addTaskToWeek, removeTaskFromWeek,

  // 清理
  clearAll, clearWeek,

  bootstrapWeeklySeed,
}

