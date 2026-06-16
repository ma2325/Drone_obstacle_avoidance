<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import * as Cesium from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import hebeiMap from '@/test-data/map/hebei.json'
import routesData from '@/test-data/routes.json'
import { useDroneTelemetry } from '@/shared/useDroneTelemetry'
import {
  cityAlertMock,
  findCityAlert,
  heatLevelText,
  swarmDronesMock,
  communicationLinksMock,
  collisionMatrixLabels,
  collisionRiskMatrixMock
} from '@/mock/mock'
import '@/assets/uav-bigscreen.css'

window.CESIUM_BASE_URL = '/node_modules/cesium/Build/Cesium/'

const {
  isConnected,
  droneData,
  flightHistory,
  attitudeHistory,
  totalSpeed,
  onlineText
} = useDroneTelemetry({ maxPoints: 40 })

const nowText = ref('')
const rightTopSlide = ref(0)
const rightBottomSlide = ref(0)
const kpiMotionTick = ref(0)
const modeTick = ref(0)
const stableGpsCount = ref(12)
let clockTimer = null
let slideTimer = null
let kpiMotionTimer = null
let modeTimer = null

const elFlightTrend = ref(null)
const elAttitudeTrend = ref(null)
const elRealMap = ref(null)
const elRingOnline = ref(null)
const elRingTask = ref(null)
const elRingAlert = ref(null)
const elRiskRadar = ref(null)
const elRiskBar = ref(null)
const elLinkComputeA = ref(null)
const elLinkComputeB = ref(null)

const charts = []
const selectedCity = ref(cityAlertMock[0].name)
const selectedCityData = computed(() => findCityAlert(selectedCity.value))
let realMapViewer = null
let routeMoveTimer = null

const selectedRouteId = ref('ALL')
const isRouteOverlayCollapsed = ref(true)
const routeTick = ref(0)
const routeEntityMap = new Map()
const droneEntityMap = new Map()
const routeProgressMap = new Map()

const HOME_LOCK_CENTER = [115.579662, 38.870149]
const HOME_LOCK_ZOOM = 8.6
const HOME_LOCK_SCALE = { min: 8.2, max: 9.4 }

function decodePolygon(coordinate, encodeOffsets) {
  const result = []
  let prevX = encodeOffsets[0]
  let prevY = encodeOffsets[1]

  for (let i = 0; i < coordinate.length; i += 2) {
    let x = coordinate.charCodeAt(i) - 64
    let y = coordinate.charCodeAt(i + 1) - 64
    x = (x >> 1) ^ (-(x & 1))
    y = (y >> 1) ^ (-(y & 1))
    x += prevX
    y += prevY
    prevX = x
    prevY = y
    result.push([x / 1024, y / 1024])
  }

  return result
}

function decodeGeoJson(mapData) {
  if (!mapData || !mapData.UTF8Encoding) return mapData

  const result = JSON.parse(JSON.stringify(mapData))
  result.features.forEach((feature) => {
    const geom = feature.geometry
    const { coordinates, encodeOffsets } = geom
    if (!coordinates || !encodeOffsets) return

    if (geom.type === 'Polygon') {
      geom.coordinates = coordinates.map((polygon, idx) => decodePolygon(polygon, encodeOffsets[idx]))
    } else if (geom.type === 'MultiPolygon') {
      geom.coordinates = coordinates.map((polygonGroup, idx) => {
        return polygonGroup.map((polygon, subIdx) => decodePolygon(polygon, encodeOffsets[idx][subIdx]))
      })
    }
  })

  result.UTF8Encoding = false
  return result
}

const displayTelemetry = computed(() => {
  const useLive = isConnected.value && droneData.value?.connected
  const t = kpiMotionTick.value

  if (useLive) {
    return {
      linkStatus: onlineText.value,
      mode: droneData.value?.mode || 'UNKNOWN',
      armed: droneData.value?.armed ? '已解锁' : '未解锁',
      gps: stableGpsCount.value,
      speed: Number(totalSpeed.value || 0),
      relAlt: Number(droneData.value?.position?.relative_alt || 0),
      heading: Number(droneData.value?.position?.heading || 0),
      battery: Number(droneData.value?.battery?.remaining || 0)
    }
  }

  return {
    linkStatus: '在线',
    mode: ['AUTO', 'GUIDED', 'LOITER'][modeTick.value % 3],
    armed: '已解锁',
    gps: stableGpsCount.value,
    speed: 7.2 + Math.sin(t / 2.6) * 2.3,
    relAlt: 108 + Math.cos(t / 3.1) * 13,
    heading: (t * 17) % 360,
    battery: Math.max(26, 96 - (t % 140) * 0.42)
  }
})

const metricRows = computed(() => {
  const s = displayTelemetry.value
  return [
    { name: '链路状态', value: s.linkStatus },
    { name: '飞行模式', value: s.mode },
    { name: '解锁状态', value: s.armed },
    { name: '卫星数量', value: `${s.gps} 颗` },
    { name: '相对高度', value: `${s.relAlt.toFixed(1)} m` },
    { name: '航向角', value: `${s.heading.toFixed(0)}°` },
    { name: '电池余量', value: `${s.battery.toFixed(0)}%` }
  ]
})

const kpis = computed(() => {
  const s = displayTelemetry.value

  return [
    { label: '当前速度', value: s.speed.toFixed(1), unit: 'm/s' },
    { label: '相对高度', value: s.relAlt.toFixed(1), unit: 'm' },
    { label: '航向角', value: s.heading.toFixed(0), unit: '°' },
    { label: '电池电量', value: s.battery.toFixed(0), unit: '%' }
  ]
})

const depthStats = computed(() => {
  const base = isConnected.value ? 1 : 0
  return [
    { label: '图传码率', value: `${(18 + base * 2.2).toFixed(1)} Mbps` },
    { label: '视频帧率', value: `${(24 + base * 4).toFixed(0)} FPS` },
    { label: '端到端延迟', value: `${(82 - base * 10).toFixed(0)} ms` },
    { label: '丢帧率', value: `${(2.4 - base * 0.7).toFixed(1)} %` }
  ]
})

const selectedCityTitle = computed(() => {
  const city = selectedCityData.value
  return `${city.shortName}（热度${city.heat}，${heatLevelText(city.heat)}）`
})

const routeColorPalette = ['#29f6ff', '#ff9a54', '#af7dff', '#3dff9e', '#ffe15a']

const sceneRoutes = computed(() => {
  return routesData.slice(0, 5).map((route, idx) => ({
    ...route,
    label: `路线${idx + 1}`,
    colorHex: routeColorPalette[idx % routeColorPalette.length]
  }))
})

const routeOptions = computed(() => {
  return [{ id: 'ALL', label: '总览' }, ...sceneRoutes.value.map((route) => ({ id: route.routeId, label: route.label }))]
})

const activeRoutes = computed(() => {
  if (selectedRouteId.value === 'ALL') return sceneRoutes.value
  return sceneRoutes.value.filter((route) => route.routeId === selectedRouteId.value)
})

const routeSummary = computed(() => {
  const all = activeRoutes.value
  const total = all.length
  const drones = all.length
  const running = all.filter((route) => {
    const pathLen = route.path?.length || 1
    const progress = ((routeProgressMap.get(route.routeId) || 0) / pathLen) * 100
    return progress > 3 && progress < 97
  }).length
  return {
    totalRoutes: total,
    totalDrones: drones,
    runningDrones: running
  }
})

const routeDroneRows = computed(() => {
  // 依赖 routeTick，确保定时推进时触发重算
  const _tick = routeTick.value
  void _tick

  return activeRoutes.value.map((route, idx) => {
    const pathLen = route.path?.length || 1
    const progressIndex = routeProgressMap.get(route.routeId) || 0
    const progress = Math.min(100, Math.round((progressIndex / pathLen) * 100))
    const speed = 10 + (idx + 1) * 1.8 + (progress % 5) * 0.2
    const battery = Math.max(18, 95 - Math.floor(progress * 0.6))
    const status = progress < 3 ? '待起飞' : progress < 97 ? '巡航中' : '返航'

    return {
      routeId: route.routeId,
      routeLabel: route.label,
      uavId: route.uavId?.toUpperCase() || `UAV-${idx + 1}`,
      progress,
      speed: speed.toFixed(1),
      battery,
      status
    }
  })
})

function calcRoutesBounds(routes) {
  const init = { west: 180, east: -180, south: 90, north: -90 }
  return routes.reduce((acc, route) => {
    ;(route.path || []).forEach((p) => {
      const lng = Number(p[0])
      const lat = Number(p[1])
      if (Number.isFinite(lng) && Number.isFinite(lat)) {
        acc.west = Math.min(acc.west, lng)
        acc.east = Math.max(acc.east, lng)
        acc.south = Math.min(acc.south, lat)
        acc.north = Math.max(acc.north, lat)
      }
    })
    return acc
  }, init)
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n))
}

function formatNow() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  nowText.value = `${y}-${m}-${day} ${hh}:${mm}:${ss}`
}

function buildAxisStyle() {
  return {
    axisLine: { lineStyle: { color: '#2f98c6' } },
    axisLabel: { color: '#a3e8ff' },
    splitLine: { lineStyle: { color: 'rgba(60, 157, 224, 0.22)' } }
  }
}

function createChart(el) {
  if (!el) return null
  const chart = echarts.init(el)
  charts.push(chart)
  return chart
}

function updateFlightChart(chart) {
  if (!chart) return
  const fallback = Array.from({ length: 20 }, (_, i) => ({
    time: `${i + 1}`,
    speed: 8 + Math.sin(i / 4) * 2,
    altitude: 120 + Math.cos(i / 3) * 18
  }))
  const source = flightHistory.value.length ? flightHistory.value : fallback

  chart.setOption({
    grid: { left: 40, right: 40, top: 38, bottom: 28 },
    legend: { top: 6, textStyle: { color: '#8edcff' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: source.map((d) => d.time),
      ...buildAxisStyle()
    },
    yAxis: [
      {
        type: 'value',
        name: '速度',
        nameTextStyle: { color: '#8edcff' },
        ...buildAxisStyle()
      },
      {
        type: 'value',
        name: '高度',
        nameTextStyle: { color: '#8edcff' },
        ...buildAxisStyle()
      }
    ],
    series: [
      {
        name: '速度 m/s',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#2dd8ff', width: 2 },
        data: source.map((d) => Number(d.speed.toFixed(2)))
      },
      {
        name: '相对高度 m',
        type: 'bar',
        yAxisIndex: 1,
        itemStyle: { color: 'rgba(65, 160, 255, 0.6)' },
        data: source.map((d) => Number(d.altitude.toFixed(2)))
      }
    ]
  })
}

function updateAttitudeChart(chart) {
  if (!chart) return
  const fallback = Array.from({ length: 20 }, (_, i) => ({
    time: `${i + 1}`,
    roll: Math.sin(i / 3) * 12,
    pitch: Math.cos(i / 4) * 10,
    yaw: (i * 14) % 360
  }))
  const source = attitudeHistory.value.length ? attitudeHistory.value : fallback

  chart.setOption({
    grid: { left: 40, right: 20, top: 36, bottom: 28 },
    legend: { top: 6, textStyle: { color: '#8edcff' } },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: source.map((d) => d.time),
      ...buildAxisStyle()
    },
    yAxis: {
      type: 'value',
      ...buildAxisStyle()
    },
    series: [
      {
        name: '横滚',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#43f7cf' },
        data: source.map((d) => Number(d.roll.toFixed(1)))
      },
      {
        name: '俯仰',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#3e95ff' },
        data: source.map((d) => Number(d.pitch.toFixed(1)))
      },
      {
        name: '航向',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#ff9a42' },
        data: source.map((d) => Number(d.yaw.toFixed(1)))
      }
    ]
  })
}

function updateMapChart(chart) {
  if (!chart) return
  const mapData = decodeGeoJson(hebeiMap)
  echarts.registerMap('hebei', mapData)

  const centerCity = selectedCityData.value
  const distance = (a, b) => {
    const dx = a[0] - b[0]
    const dy = a[1] - b[1]
    return Math.sqrt(dx * dx + dy * dy)
  }

  const nearbyCities = [...cityAlertMock]
    .sort((a, b) => distance(a.coord, centerCity.coord) - distance(b.coord, centerCity.coord))
    .slice(0, 6)

  const cityData = nearbyCities.map((item) => ({
    name: item.name,
    shortName: item.shortName,
    value: [item.coord[0], item.coord[1], item.heat]
  }))

  const linesData = nearbyCities
    .filter((item) => item.name !== centerCity.name)
    .map((item) => [{ coord: centerCity.coord }, { coord: item.coord }])

  chart.setOption({
    tooltip: { trigger: 'item' },
    geo: {
      map: 'hebei',
      roam: false,
      center: HOME_LOCK_CENTER,
      zoom: HOME_LOCK_ZOOM,
      scaleLimit: HOME_LOCK_SCALE,
      itemStyle: {
        areaColor: '#103774',
        borderColor: '#1de2ff'
      },
      emphasis: {
        itemStyle: {
          areaColor: '#1e5fb3'
        }
      }
    },
    visualMap: {
      type: 'piecewise',
      min: 0,
      max: 100,
      left: 12,
      bottom: 16,
      textStyle: { color: '#b7ebff' },
      pieces: [
        { min: 80, label: '极高 (80-100)', color: '#ff5f5f' },
        { min: 65, max: 79, label: '高 (65-79)', color: '#ffb14a' },
        { min: 50, max: 64, label: '中 (50-64)', color: '#4ec3ff' },
        { max: 49, label: '低 (0-49)', color: '#3d78ff' }
      ]
    },
    series: [
      {
        type: 'map',
        map: 'hebei',
        geoIndex: 0,
        label: {
          show: false
        },
        itemStyle: {
          areaColor: '#123f7d',
          borderColor: '#53dfff'
        },
        emphasis: {
          itemStyle: {
            areaColor: '#2c6fc1'
          },
          label: { color: '#ffffff' }
        },
        data: cityData.map((item) => ({ name: item.name, value: item.value[2] }))
      },
      {
        type: 'lines',
        coordinateSystem: 'geo',
        effect: {
          show: true,
          period: 6,
          trailLength: 0.2,
          symbolSize: 4
        },
        lineStyle: {
          color: '#6bd8ff',
          width: 1.2,
          opacity: 0.55,
          curveness: 0.18
        },
        data: linesData
      },
      {
        type: 'effectScatter',
        coordinateSystem: 'geo',
        rippleEffect: { scale: 4 },
        symbolSize: (val) => 6 + val[2] / 18,
        label: {
          show: true,
          position: 'right',
          color: '#d7f6ff',
          fontSize: 11,
          formatter: (params) => {
            const name = params.data?.shortName || String(params.name || '').replace('市', '')
            return `${name}\n热度${params.value?.[2] || 0}`
          }
        },
        itemStyle: {
          color: '#ffb25a'
        },
        data: cityData
      }
    ]
  })
}

async function initRealMapScene() {
  if (!elRealMap.value || realMapViewer) return

  const bounds = calcRoutesBounds(sceneRoutes.value)
  const centerLng = (bounds.west + bounds.east) / 2
  const centerLat = (bounds.south + bounds.north) / 2

  Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJiNzEzZjEzYi0wNjg5LTQ0OTMtYWZkNS1iNTVjOTRmMDMwNzEiLCJpZCI6MzIwMjIwLCJpYXQiOjE3NTIyMDAxMzd9.oytvSPRNdHLhiI2KxkAAU8Peyb4bX0OaZFlZE4MDHv8'

  realMapViewer = new Cesium.Viewer(elRealMap.value, {
    terrainProvider: await Cesium.createWorldTerrainAsync(),
    homeButton: false,
    sceneModePicker: false,
    baseLayerPicker: false,
    navigationHelpButton: false,
    geocoder: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    shouldAnimate: true,
    contextOptions: { requestWebgl2: true }
  })

  realMapViewer.cesiumWidget.creditContainer.style.display = 'none'
  realMapViewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(centerLng, centerLat, 32000),
    orientation: { heading: 0, pitch: -Cesium.Math.PI / 2, roll: 0 }
  })

  const cameraCtl = realMapViewer.scene.screenSpaceCameraController
  cameraCtl.enableTilt = false
  cameraCtl.minimumZoomDistance = 2000
  cameraCtl.maximumZoomDistance = 120000

  const limitBounds = {
    west: bounds.west - 0.08,
    east: bounds.east + 0.08,
    south: bounds.south - 0.08,
    north: bounds.north + 0.08
  }

  const keepInBounds = () => {
    if (!realMapViewer) return
    const cart = realMapViewer.camera.positionCartographic
    const lng = Cesium.Math.toDegrees(cart.longitude)
    const lat = Cesium.Math.toDegrees(cart.latitude)
    const clampedLng = clamp(lng, limitBounds.west, limitBounds.east)
    const clampedLat = clamp(lat, limitBounds.south, limitBounds.north)

    if (Math.abs(clampedLng - lng) > 0.0001 || Math.abs(clampedLat - lat) > 0.0001) {
      realMapViewer.camera.setView({
        destination: Cesium.Cartesian3.fromDegrees(clampedLng, clampedLat, cart.height),
        orientation: {
          heading: realMapViewer.camera.heading,
          pitch: realMapViewer.camera.pitch,
          roll: 0
        }
      })
    }
  }

  realMapViewer.camera.moveEnd.addEventListener(keepInBounds)

  const rectanglePositions = [
    Cesium.Cartesian3.fromDegrees(limitBounds.west, limitBounds.north, 80),
    Cesium.Cartesian3.fromDegrees(limitBounds.east, limitBounds.north, 80),
    Cesium.Cartesian3.fromDegrees(limitBounds.east, limitBounds.south, 80),
    Cesium.Cartesian3.fromDegrees(limitBounds.west, limitBounds.south, 80),
    Cesium.Cartesian3.fromDegrees(limitBounds.west, limitBounds.north, 80)
  ]

  realMapViewer.entities.add({
    name: '任务区域边界',
    polyline: {
      positions: rectanglePositions,
      width: 2,
      material: new Cesium.PolylineDashMaterialProperty({
        color: Cesium.Color.fromCssColorString('#61ddff')
      })
    }
  })

  sceneRoutes.value.forEach((route) => {
    routeProgressMap.set(route.routeId, 0)

    const positions = (route.path || []).map((p) => Cesium.Cartesian3.fromDegrees(p[0], p[1], Math.max(60, p[2] || 120)))
    const lineEntity = realMapViewer.entities.add({
      id: `line-${route.routeId}`,
      polyline: {
        positions,
        width: 9,
        material: new Cesium.PolylineOutlineMaterialProperty({
          color: Cesium.Color.fromCssColorString(route.colorHex),
          outlineColor: Cesium.Color.fromCssColorString('#072038'),
          outlineWidth: 2
        })
      }
    })
    routeEntityMap.set(route.routeId, lineEntity)

    const first = route.path?.[0]
    const droneEntity = realMapViewer.entities.add({
      id: `drone-${route.routeId}`,
      position: Cesium.Cartesian3.fromDegrees(first[0], first[1], Math.max(80, first[2] || 140)),
      point: {
        pixelSize: 15,
        color: Cesium.Color.fromCssColorString(route.colorHex),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 3
      },
      label: {
        text: route.uavId?.toUpperCase() || route.routeId,
        font: '12px sans-serif',
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        pixelOffset: new Cesium.Cartesian2(0, -16)
      }
    })
    droneEntityMap.set(route.routeId, droneEntity)
  })

  updateRouteEntitiesVisibility()
}

function updateRouteEntitiesVisibility() {
  const all = selectedRouteId.value === 'ALL'
  routeEntityMap.forEach((entity, routeId) => {
    entity.show = all || routeId === selectedRouteId.value
    if (entity.polyline) {
      entity.polyline.width = all ? 8 : routeId === selectedRouteId.value ? 11 : 7
    }
  })
  droneEntityMap.forEach((entity, routeId) => {
    entity.show = all || routeId === selectedRouteId.value
  })
}

function moveClusterDrones() {
  if (!realMapViewer) return

  sceneRoutes.value.forEach((route) => {
    const path = route.path || []
    if (!path.length) return

    const current = routeProgressMap.get(route.routeId) || 0
    const next = (current + 2) % path.length
    routeProgressMap.set(route.routeId, next)

    const target = path[next]
    const droneEntity = droneEntityMap.get(route.routeId)
    if (droneEntity) {
      droneEntity.position = Cesium.Cartesian3.fromDegrees(target[0], target[1], Math.max(80, target[2] || 140))
    }
  })

  routeTick.value += 1
}

function focusRouteOnMap(routeId) {
  if (!realMapViewer || routeId === 'ALL') return
  const route = sceneRoutes.value.find((item) => item.routeId === routeId)
  if (!route || !route.path?.length) return

  const mid = route.path[Math.floor(route.path.length / 2)]
  realMapViewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(mid[0], mid[1], 14000),
    orientation: { heading: 0, pitch: -Cesium.Math.toRadians(75), roll: 0 },
    duration: 0.8
  })
}

function updateRing(chart, title, val, color) {
  if (!chart) return
  chart.setOption({
    title: {
      text: `${val}`,
      subtext: title,
      left: 'center',
      top: '36%',
      textStyle: { color: '#d5f9ff', fontSize: 28 },
      subtextStyle: { color: '#8adfff', fontSize: 14 }
    },
    series: [
      {
        type: 'pie',
        radius: ['70%', '82%'],
        label: { show: false },
        data: [
          { value: Math.min(val, 100), itemStyle: { color } },
          { value: Math.max(100 - val, 0), itemStyle: { color: 'rgba(59,130,170,0.22)' } }
        ]
      }
    ]
  })
}

function updateRiskRadar(chart) {
  if (!chart) return
  const city = selectedCityData.value
  chart.setOption({
    title: {
      text: `${city.shortName} 避障风险雷达`,
      left: 'center',
      top: 2,
      textStyle: { color: '#8ee6ff', fontSize: 13, fontWeight: 500 }
    },
    radar: {
      indicator: [
        { name: '静态障碍', max: 100 },
        { name: '动态障碍', max: 100 },
        { name: '路径偏差', max: 100 },
        { name: '最小距离', max: 100 },
        { name: '告警频次', max: 100 }
      ],
      splitLine: { lineStyle: { color: 'rgba(90, 184, 255, 0.35)' } },
      splitArea: { areaStyle: { color: ['rgba(19,74,138,0.25)'] } },
      axisName: { color: '#a9ebff' }
    },
    series: [
      {
        type: 'radar',
        areaStyle: { color: 'rgba(246, 168, 59, 0.35)' },
        lineStyle: { color: '#ff9f45' },
        data: [{ value: city.radar }]
      }
    ]
  })
}

function updateRiskBar(chart) {
  if (!chart) return
  const city = selectedCityData.value
  chart.setOption({
    grid: { left: 42, right: 16, top: 20, bottom: 25 },
    xAxis: {
      type: 'category',
      data: ['低风险', '中风险', '高风险', '极高'],
      ...buildAxisStyle()
    },
    yAxis: { type: 'value', ...buildAxisStyle() },
    series: [
      {
        type: 'bar',
        data: city.buckets,
        itemStyle: {
          color: (params) => ['#26e6ff', '#2ea0ff', '#f9b74f', '#ff6f5e'][params.dataIndex]
        }
      }
    ]
  })
}

function updateLinkComputeA(chart) {
  if (!chart) return

  const groupColor = {
    A: '#2cf4ff',
    B: '#4fa8ff',
    C: '#5dffb2',
    D: '#ffbf57'
  }

  const nodes = swarmDronesMock.map((item) => ({
    id: item.id,
    name: item.id,
    value: item.value,
    symbolSize: item.symbolSize,
    category: item.group,
    itemStyle: { color: groupColor[item.group] || '#2cf4ff' },
    label: { color: '#d7f6ff' }
  }))

  const links = communicationLinksMock.map(([source, target, quality]) => ({
    source,
    target,
    value: quality,
    lineStyle: {
      width: 1 + quality * 2.6,
      color: quality >= 0.8 ? '#59ffa5' : quality >= 0.65 ? '#4ec3ff' : '#ffb14a',
      opacity: 0.7
    }
  }))

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'edge') {
          return `${params.data.source} → ${params.data.target}<br/>链路质量: ${(params.data.value * 100).toFixed(0)}%`
        }
        return `${params.data.name}<br/>链路评分: ${params.data.value}`
      }
    },
    legend: {
      top: 4,
      textStyle: { color: '#9ddfff' },
      data: ['A', 'B', 'C', 'D']
    },
    animationDuration: 1200,
    series: [
      {
        type: 'graph',
        layout: 'force',
        left: 6,
        right: 6,
        top: 26,
        bottom: 6,
        roam: true,
        force: {
          repulsion: 180,
          edgeLength: [26, 65],
          gravity: 0.08
        },
        categories: [
          { name: 'A' },
          { name: 'B' },
          { name: 'C' },
          { name: 'D' }
        ],
        label: {
          show: true,
          fontSize: 9
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: [2, 6],
        lineStyle: {
          opacity: 0.75,
          curveness: 0.12
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: {
            width: 3
          }
        },
        data: nodes,
        links
      }
    ]
  })
}

function updateLinkComputeB(chart) {
  if (!chart) return

  const matrixData = []
  for (let i = 0; i < collisionRiskMatrixMock.length; i += 1) {
    for (let j = 0; j < collisionRiskMatrixMock[i].length; j += 1) {
      matrixData.push([j, i, collisionRiskMatrixMock[i][j]])
    }
  }

  chart.setOption({
    grid: { left: 52, right: 14, top: 34, bottom: 36 },
    tooltip: {
      formatter: (params) => {
        const x = collisionMatrixLabels[params.value[0]]
        const y = collisionMatrixLabels[params.value[1]]
        return `${y} vs ${x}<br/>碰撞风险: ${params.value[2]}`
      }
    },
    xAxis: {
      type: 'category',
      data: collisionMatrixLabels,
      axisLabel: { color: '#a3e8ff', fontSize: 10 },
      axisLine: { lineStyle: { color: '#2f98c6' } }
    },
    yAxis: {
      type: 'category',
      data: collisionMatrixLabels,
      axisLabel: { color: '#a3e8ff', fontSize: 10 },
      axisLine: { lineStyle: { color: '#2f98c6' } }
    },
    visualMap: {
      min: 0,
      max: 30,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: { color: '#9ddfff' },
      inRange: {
        color: ['#173b7f', '#2ea6ff', '#5dffb2', '#ffbf57', '#ff6f5e']
      }
    },
    series: [
      {
        name: '碰撞风险矩阵',
        type: 'heatmap',
        data: matrixData,
        label: {
          show: true,
          color: '#e6fdff',
          fontSize: 9
        },
        emphasis: {
          itemStyle: {
            borderColor: '#ffffff',
            borderWidth: 1
          }
        }
      }
    ]
  })
}

function refreshCharts() {
  updateFlightChart(charts[0])
  updateAttitudeChart(charts[1])
  updateRing(charts[2], '在线无人机数', isConnected.value ? 78 : 35, '#36f5bf')
  updateRing(charts[3], '执行中任务数', 64, '#49a2ff')
  updateRing(charts[4], '避障告警指数', isConnected.value ? 34 : 56, '#ff914d')
  updateRiskRadar(charts[5])
  updateRiskBar(charts[6])
  updateLinkComputeA(charts[7])
  updateLinkComputeB(charts[8])
}

function onResize() {
  charts.forEach((chart) => chart && chart.resize())
  if (realMapViewer) {
    realMapViewer.resize()
    realMapViewer.scene.requestRender()
  }
}

watch([flightHistory, attitudeHistory, isConnected], () => {
  refreshCharts()
}, { deep: true })

watch(
  () => droneData.value?.gps?.satellites,
  (satellites) => {
    const next = Number(satellites)
    if (Number.isFinite(next) && next > 0 && stableGpsCount.value === 12) {
      stableGpsCount.value = Math.round(next)
    }
  },
  { immediate: true }
)

watch(selectedCityData, () => {
  updateRiskRadar(charts[5])
  updateRiskBar(charts[6])
})

watch(selectedRouteId, (routeId) => {
  updateRouteEntitiesVisibility()
  if (routeId !== 'ALL') {
    const idx = sceneRoutes.value.findIndex((route) => route.routeId === routeId)
    selectedCity.value = cityAlertMock[idx % cityAlertMock.length].name
  }
  focusRouteOnMap(routeId)
})

watch(rightTopSlide, async (val) => {
  await nextTick()
  if (val === 0) {
    charts[5] && charts[5].resize()
    updateRiskRadar(charts[5])
  } else {
    charts[6] && charts[6].resize()
    updateRiskBar(charts[6])
  }
})

watch(rightBottomSlide, async (val) => {
  await nextTick()
  if (val === 0) {
    charts[7] && charts[7].resize()
    updateLinkComputeA(charts[7])
  } else {
    charts[8] && charts[8].resize()
    updateLinkComputeB(charts[8])
  }
})

onMounted(async () => {
  formatNow()
  clockTimer = setInterval(formatNow, 1000)
  kpiMotionTimer = setInterval(() => {
    kpiMotionTick.value += 1
  }, 600)
  modeTimer = setInterval(() => {
    modeTick.value += 1
  }, 60000)
  slideTimer = setInterval(() => {
    rightTopSlide.value = (rightTopSlide.value + 1) % 2
    rightBottomSlide.value = (rightBottomSlide.value + 1) % 2
  }, 5000)
  routeMoveTimer = setInterval(moveClusterDrones, 1200)

  await nextTick()
  createChart(elFlightTrend.value)
  createChart(elAttitudeTrend.value)
  createChart(elRingOnline.value)
  createChart(elRingTask.value)
  createChart(elRingAlert.value)
  createChart(elRiskRadar.value)
  createChart(elRiskBar.value)
  createChart(elLinkComputeA.value)
  createChart(elLinkComputeB.value)

  await initRealMapScene()

  refreshCharts()
  requestAnimationFrame(() => onResize())
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  if (kpiMotionTimer) clearInterval(kpiMotionTimer)
  if (modeTimer) clearInterval(modeTimer)
  if (slideTimer) clearInterval(slideTimer)
  if (routeMoveTimer) clearInterval(routeMoveTimer)
  window.removeEventListener('resize', onResize)
  charts.forEach((chart) => chart.dispose())
  routeEntityMap.clear()
  droneEntityMap.clear()
  routeProgressMap.clear()
  if (realMapViewer) {
    realMapViewer.destroy()
    realMapViewer = null
  }
})
</script>

<template>
  <div class="uav-screen">
    <header class="uav-screen-header">
      <div class="uav-screen-title">高速公路低空无人机集群管控大数据</div>
      <div class="uav-screen-sub">{{ nowText }}</div>
    </header>

    <section class="uav-grid">
      <div class="left-column">
        <div class="panel">
          <div class="panel-title">飞行状态趋势（速度/高度）</div>
          <div class="panel-body chart" ref="elFlightTrend"></div>
        </div>

        <div class="panel">
          <div class="panel-title">姿态角趋势（俯仰/横滚/航向）</div>
          <div class="panel-body chart" ref="elAttitudeTrend"></div>
        </div>

        <div class="panel">
          <div class="panel-title">基础控制与任务状态</div>
          <div class="panel-body">
            <table class="control-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in metricRows" :key="row.name">
                  <td>{{ row.name }}</td>
                  <td :class="row.value === '在线' ? 'state-online' : row.value === '离线' ? 'state-offline' : ''">
                    {{ row.value }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="center-column">
        <div class="kpi-row">
          <div class="kpi-card" v-for="item in kpis" :key="item.label">
            <div class="kpi-label">{{ item.label }}</div>
            <div class="kpi-value">{{ item.value }} <span class="kpi-unit">{{ item.unit }}</span></div>
          </div>
        </div>

        <div class="panel center-map">
          <div class="panel-title map-title-bar">
            <span>任务空域真实场景（限制区域 + 多路线集群）</span>
            <div class="route-switcher">
              <button
                v-for="item in routeOptions"
                :key="item.id"
                :class="['route-btn', { active: selectedRouteId === item.id }]"
                @click="selectedRouteId = item.id"
              >
                {{ item.label }}
              </button>
            </div>
          </div>
          <div class="panel-body real-map-wrap">
            <div class="real-map-canvas" ref="elRealMap"></div>
            <div :class="['route-overlay', { collapsed: isRouteOverlayCollapsed }]">
              <div class="route-overlay-head">
                <div class="route-overview-row">
                  <span>路线 {{ routeSummary.totalRoutes }}</span>
                  <span>无人机 {{ routeSummary.totalDrones }}</span>
                  <span>执行中 {{ routeSummary.runningDrones }}</span>
                </div>
                <button class="overlay-toggle-btn" @click="isRouteOverlayCollapsed = !isRouteOverlayCollapsed">
                  {{ isRouteOverlayCollapsed ? '展开' : '收起' }}
                </button>
              </div>
              <div class="route-drone-list" v-show="!isRouteOverlayCollapsed">
                <div class="route-drone-item" v-for="row in routeDroneRows" :key="row.routeId">
                  <span>{{ row.routeLabel }} · {{ row.uavId }}</span>
                  <strong>{{ row.status }}</strong>
                  <em>{{ row.progress }}% / {{ row.speed }}m/s / {{ row.battery }}%</em>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="ring-row">
          <div class="panel">
            <div class="panel-body chart" ref="elRingOnline"></div>
          </div>
          <div class="panel">
            <div class="panel-body chart" ref="elRingTask"></div>
          </div>
          <div class="panel">
            <div class="panel-body chart" ref="elRingAlert"></div>
          </div>
        </div>
      </div>

      <div class="right-column">
        <div class="panel">
          <div class="panel-title">避障仿真监控 - {{ selectedCityTitle }}</div>
          <div class="panel-body chart" v-show="rightTopSlide === 0" ref="elRiskRadar"></div>
          <div class="panel-body chart" v-show="rightTopSlide === 1" ref="elRiskBar"></div>
        </div>

        <div class="panel">
          <div class="panel-title">深度图传质量</div>
          <div class="panel-body">
            <div class="metrics-list">
              <div class="metrics-line" v-for="item in depthStats" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">集群监控（通信拓扑 / 碰撞风险矩阵）</div>
          <div class="panel-body chart" v-show="rightBottomSlide === 0" ref="elLinkComputeA"></div>
          <div class="panel-body chart" v-show="rightBottomSlide === 1" ref="elLinkComputeB"></div>
        </div>
      </div>
    </section>
  </div>
</template>
