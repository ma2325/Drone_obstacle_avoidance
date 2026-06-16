import math
import json

# === 坐标转换核心算法（GCJ-02 → WGS-84） ===

# 地球常量
PI = 3.14159265358979324
A = 6378245.0  # 长半轴
EE = 0.00669342162296594323  # 扁率

def out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)

def transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + \
          0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 
            20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 
            40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 
            320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + \
          0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 
            20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 
            40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 
            300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret

def gcj02_to_wgs84(lng, lat):
    if out_of_china(lng, lat):
        return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglng = lng + dlng
    return lng * 2 - mglng, lat * 2 - mglat

# === 输入原始轨迹 ===
# 示例输入，真实使用时请替换为文件读取或接口获取
gcj02_points = [
    
    [116.211880, 39.841683],
    [116.060709, 39.596631],
    [116.044586, 39.525252],
    [116.043449, 39.482787],
    [115.929583, 39.312441],
    [115.813384, 39.210905],
    [115.701803, 39.044792],
    [115.596324, 38.906130],
    [115.585600, 38.870768],
    [115.455495, 38.743379],
    [115.206412, 38.652636],
    [115.040921, 38.527727],
    [114.715835, 38.334064],
    [114.783750, 38.152523]
]
    # ...替换为你的完整 GCJ-02 轨迹


# === 执行坐标转换 ===
wgs84_points = []
cesium_coords = []

for lng, lat in gcj02_points:
    lng_wgs, lat_wgs = gcj02_to_wgs84(lng, lat)
    wgs84_points.append((lng_wgs, lat_wgs))
    cesium_coords.extend([round(lng_wgs, 6), round(lat_wgs, 6)])

# === 导出为文本文件 ===
with open("station_WGS84_code.txt", "w", encoding="utf-8") as f:
    for lng, lat in wgs84_points:
        f.write(f"{lng:.6f},{lat:.6f}\n")
print("✅ 已保存 WGS-84 坐标到：station_WGS84_code.txt")

