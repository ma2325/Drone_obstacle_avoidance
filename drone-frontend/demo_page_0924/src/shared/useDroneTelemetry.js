import { computed, onMounted, onUnmounted, ref } from 'vue'

const DEFAULT_WS_URL = 'ws://localhost:8765'

function createDefaultDroneData() {
  return {
    connected: false,
    position: { lat: 0, lon: 0, alt: 0, relative_alt: 0, heading: 0 },
    attitude: { roll: 0, pitch: 0, yaw: 0 },
    battery: { voltage: 0, current: 0, remaining: 100 },
    gps: { fix_type: 0, satellites: 0 },
    mode: 'UNKNOWN',
    armed: false,
    velocity: { vx: 0, vy: 0, vz: 0 },
    ground_speed: 0,
    rangefinder: { distance: 0, available: false },
    last_update: null
  }
}

export function useDroneTelemetry(options = {}) {
  const wsUrl = options.wsUrl || DEFAULT_WS_URL
  const maxPoints = Number.isFinite(options.maxPoints) ? options.maxPoints : 60

  const isConnected = ref(false)
  const droneData = ref(createDefaultDroneData())
  const flightHistory = ref([])
  const attitudeHistory = ref([])

  let ws = null
  let reconnectTimer = null
  let unmounted = false

  const totalSpeed = computed(() => {
    const vx = Number(droneData.value?.velocity?.vx || 0)
    const vy = Number(droneData.value?.velocity?.vy || 0)
    const vz = Number(droneData.value?.velocity?.vz || 0)
    return Math.sqrt(vx * vx + vy * vy + vz * vz)
  })

  const climbRate = computed(() => {
    const vz = Number(droneData.value?.velocity?.vz || 0)
    return -vz
  })

  const onlineText = computed(() => (isConnected.value && droneData.value?.connected ? '在线' : '离线'))

  const pushHistory = (data) => {
    const now = new Date()
    const label = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`

    flightHistory.value.push({
      time: label,
      speed: Number.isFinite(totalSpeed.value) ? Number(totalSpeed.value.toFixed(2)) : 0,
      altitude: Number(data?.position?.relative_alt || 0)
    })

    attitudeHistory.value.push({
      time: label,
      roll: Number(data?.attitude?.roll || 0),
      pitch: Number(data?.attitude?.pitch || 0),
      yaw: Number(data?.attitude?.yaw || 0)
    })

    if (flightHistory.value.length > maxPoints) {
      flightHistory.value.splice(0, flightHistory.value.length - maxPoints)
    }
    if (attitudeHistory.value.length > maxPoints) {
      attitudeHistory.value.splice(0, attitudeHistory.value.length - maxPoints)
    }
  }

  const clearReconnect = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  const scheduleReconnect = () => {
    if (unmounted || reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, 5000)
  }

  const connect = () => {
    if (ws || unmounted) return

    try {
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        isConnected.value = true
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          if (message?.type !== 'drone_data' || !message?.data) return
          droneData.value = message.data
          pushHistory(message.data)
        } catch (error) {
          console.error('[useDroneTelemetry] parse error:', error)
        }
      }

      ws.onerror = (error) => {
        console.error('[useDroneTelemetry] websocket error:', error)
      }

      ws.onclose = () => {
        isConnected.value = false
        ws = null
        scheduleReconnect()
      }
    } catch (error) {
      console.error('[useDroneTelemetry] connect error:', error)
      ws = null
      scheduleReconnect()
    }
  }

  const disconnect = () => {
    clearReconnect()
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  onMounted(() => {
    unmounted = false
    connect()
  })

  onUnmounted(() => {
    unmounted = true
    disconnect()
  })

  return {
    isConnected,
    droneData,
    flightHistory,
    attitudeHistory,
    totalSpeed,
    climbRate,
    onlineText,
    connect,
    disconnect
  }
}
