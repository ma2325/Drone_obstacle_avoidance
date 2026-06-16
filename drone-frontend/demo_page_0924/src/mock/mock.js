export const cityAlertMock = [
  {
    name: '保定市',
    shortName: '保定',
    coord: [115.47, 38.87],
    heat: 79,
    radar: [72, 66, 57, 63, 54],
    buckets: [17, 17, 9, 4]
  },
  {
    name: '廊坊市',
    shortName: '廊坊',
    coord: [116.68, 39.53],
    heat: 66,
    radar: [61, 59, 51, 56, 47],
    buckets: [20, 14, 7, 3]
  },
  {
    name: '石家庄市',
    shortName: '石家庄',
    coord: [114.52, 38.05],
    heat: 62,
    radar: [58, 56, 48, 53, 44],
    buckets: [22, 12, 6, 2]
  },
  {
    name: '沧州市',
    shortName: '沧州',
    coord: [116.84, 38.31],
    heat: 57,
    radar: [53, 54, 43, 48, 41],
    buckets: [23, 11, 5, 2]
  },
  {
    name: '衡水市',
    shortName: '衡水',
    coord: [115.67, 37.74],
    heat: 53,
    radar: [49, 51, 41, 45, 39],
    buckets: [24, 10, 4, 1]
  },
  {
    name: '雄安新区',
    shortName: '雄安',
    coord: [115.92, 39.05],
    heat: 50,
    radar: [47, 49, 40, 44, 37],
    buckets: [26, 9, 3, 1]
  }
]

export function findCityAlert(cityName) {
  if (!cityName) return cityAlertMock[0]
  return cityAlertMock.find((city) => city.name === cityName || city.shortName === cityName) || cityAlertMock[0]
}

export function heatLevelText(heat) {
  if (heat >= 80) return '极高'
  if (heat >= 65) return '高'
  if (heat >= 50) return '中'
  return '低'
}

export const swarmDronesMock = [
  { id: 'UAV-01', group: 'A', value: 98, symbolSize: 22 },
  { id: 'UAV-02', group: 'A', value: 91, symbolSize: 20 },
  { id: 'UAV-03', group: 'A', value: 88, symbolSize: 19 },
  { id: 'UAV-04', group: 'A', value: 84, symbolSize: 18 },
  { id: 'UAV-05', group: 'A', value: 80, symbolSize: 18 },
  { id: 'UAV-06', group: 'B', value: 87, symbolSize: 19 },
  { id: 'UAV-07', group: 'B', value: 83, symbolSize: 18 },
  { id: 'UAV-08', group: 'B', value: 79, symbolSize: 17 },
  { id: 'UAV-09', group: 'B', value: 76, symbolSize: 17 },
  { id: 'UAV-10', group: 'B', value: 73, symbolSize: 16 },
  { id: 'UAV-11', group: 'C', value: 82, symbolSize: 18 },
  { id: 'UAV-12', group: 'C', value: 78, symbolSize: 17 },
  { id: 'UAV-13', group: 'C', value: 74, symbolSize: 16 },
  { id: 'UAV-14', group: 'C', value: 71, symbolSize: 16 },
  { id: 'UAV-15', group: 'C', value: 68, symbolSize: 15 },
  { id: 'UAV-16', group: 'D', value: 77, symbolSize: 17 },
  { id: 'UAV-17', group: 'D', value: 73, symbolSize: 16 },
  { id: 'UAV-18', group: 'D', value: 69, symbolSize: 15 },
  { id: 'UAV-19', group: 'D', value: 66, symbolSize: 15 },
  { id: 'UAV-20', group: 'D', value: 63, symbolSize: 14 }
]

export const communicationLinksMock = [
  ['UAV-01', 'UAV-02', 0.96], ['UAV-01', 'UAV-03', 0.91], ['UAV-02', 'UAV-04', 0.88],
  ['UAV-03', 'UAV-05', 0.84], ['UAV-04', 'UAV-06', 0.79], ['UAV-05', 'UAV-07', 0.77],
  ['UAV-06', 'UAV-07', 0.94], ['UAV-06', 'UAV-08', 0.82], ['UAV-07', 'UAV-09', 0.8],
  ['UAV-08', 'UAV-10', 0.76], ['UAV-09', 'UAV-11', 0.74], ['UAV-10', 'UAV-12', 0.72],
  ['UAV-11', 'UAV-12', 0.9], ['UAV-11', 'UAV-13', 0.83], ['UAV-12', 'UAV-14', 0.8],
  ['UAV-13', 'UAV-15', 0.75], ['UAV-14', 'UAV-16', 0.71], ['UAV-15', 'UAV-17', 0.69],
  ['UAV-16', 'UAV-17', 0.87], ['UAV-16', 'UAV-18', 0.78], ['UAV-17', 'UAV-19', 0.74],
  ['UAV-18', 'UAV-20', 0.7], ['UAV-19', 'UAV-20', 0.86], ['UAV-02', 'UAV-08', 0.63],
  ['UAV-04', 'UAV-12', 0.6], ['UAV-07', 'UAV-14', 0.58], ['UAV-09', 'UAV-18', 0.55]
]

export const collisionMatrixLabels = ['A1', 'A2', 'A3', 'A4', 'B1', 'B2', 'B3', 'B4']

export const collisionRiskMatrixMock = [
  [0, 18, 14, 9, 21, 16, 12, 7],
  [18, 0, 23, 11, 17, 13, 9, 5],
  [14, 23, 0, 19, 15, 12, 8, 6],
  [9, 11, 19, 0, 22, 18, 14, 8],
  [21, 17, 15, 22, 0, 26, 19, 12],
  [16, 13, 12, 18, 26, 0, 24, 15],
  [12, 9, 8, 14, 19, 24, 0, 17],
  [7, 5, 6, 8, 12, 15, 17, 0]
]
