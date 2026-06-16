import requests

# 高德Web服务Key，请替换成你的有效key
key = "eb2fef3f307d823d9b33d0b4856ac3b3"

# # 起点（北京六里桥附近）这是最开始的路段
# origin = "116.30943,39.8676"
# # 终点（石家庄南高营附近）
# destination = "114.5821,38.0036"

# 起点（徐水收费站）这是查找两个收费站的路段
origin = "115.701803,39.044792"
# 终点（保定北收费站）
destination = "115.596324,38.90613"

url = "https://restapi.amap.com/v3/direction/driving"

params = {
    "key": key,
    "origin": origin,
    "destination": destination,
    "strategy": 0,
    "extensions": "all",
    "output": "json"
}

def main():
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    if data.get("status") != "1":
        print("请求失败，错误信息：", data.get("info"))
        return

    # 解析路径步骤中的polyline坐标串，合并所有点
    steps = data.get("route", {}).get("paths", [])[0].get("steps", [])
    polyline_points = []
    for step in steps:
        line = step.get("polyline")
        if line:
            points = line.split(";")
            polyline_points.extend(points)

    print(f"总共轨迹点数量：{len(polyline_points)}")

    # 保存原始轨迹坐标（字符串格式，经度,纬度）
    with open("京石高速_轨迹坐标.txt", "w", encoding="utf-8") as f:
        for pt in polyline_points:
            f.write(pt + "\n")
    print("✅ 已保存轨迹坐标到：京石高速_轨迹坐标.txt")

    # 转换为Cesium需要的 [lng1, lat1, lng2, lat2, ...] 格式
    coords = []
    for pt in polyline_points:
        lng, lat = pt.split(",")
        coords.append(float(lng))
        coords.append(float(lat))

    cesium_array_str = "[" + ", ".join(f"{c:.6f}" for c in coords) + "]"
    with open("cesium_coords_array.txt", "w", encoding="utf-8") as f:
        f.write(cesium_array_str)
    print("✅ 已保存Cesium格式坐标数组到：cesium_coords_array.txt")

if __name__ == "__main__":
    main()
