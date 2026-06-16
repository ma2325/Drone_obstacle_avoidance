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
# gcj02_points = [
#     [116.309453, 39.867578],
#     [116.309418, 39.867555],
#     [116.309246, 39.867458],
#     [116.309112, 39.867399],
#     [116.308988, 39.867351]
#     # ...替换为你的完整 GCJ-02 轨迹
# ]
# === 从文件读取轨迹点 ===

gcj02_points = []

# "route_1.txt"（这是一开始总的路线）替换成任意需要转换的原txt纯数组文件
with open("route_1.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue  # 跳过空行
        try:
            lng, lat = map(float, line.split(','))
            gcj02_points.append([lng, lat])
        except ValueError:
            print(f"[⚠️ 警告] 无法解析行: {line}")


# === 执行坐标转换 ===
wgs84_points = []
cesium_coords = []

for lng, lat in gcj02_points:
    lng_wgs, lat_wgs = gcj02_to_wgs84(lng, lat)
    wgs84_points.append((lng_wgs, lat_wgs))
    cesium_coords.extend([round(lng_wgs, 6), round(lat_wgs, 6)])

# === 导出为文本文件 ===
#route_1_WGS84.txt可替换成你想保存的txt 
with open("route_1_WGS84.txt", "w", encoding="utf-8") as f:
    for lng, lat in wgs84_points:
        f.write(f"{lng:.6f},{lat:.6f}\n")
print("✅ 已保存 WGS-84 坐标到：route_1_WGS84.txt")

# === 导出为 JSON 数组（可直接导入 Vue/Cesium） ===
# cesium_route_1_wgs84.json可替换成你想保存的json
with open("cesium_route_1_wgs84.json", "w", encoding="utf-8") as f:
    json.dump(cesium_coords, f, indent=2)
print("✅ 已保存 Cesium 坐标数组到：cesium_route_1_wgs84.json")
