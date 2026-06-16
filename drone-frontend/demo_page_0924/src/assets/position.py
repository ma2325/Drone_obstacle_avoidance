import requests

key = "eb2fef3f307d823d9b33d0b4856ac3b3"

def read_polyline_points(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        points = [line.strip() for line in f if line.strip()]
    return points

def query_toll_stations(polyline_points):
    lngs = [float(pt.split(",")[0]) for pt in polyline_points]
    lats = [float(pt.split(",")[1]) for pt in polyline_points]
    buffer = 0.02  # 大约2公里缓冲，可根据需要调整

    min_lng, max_lng = min(lngs) - buffer, max(lngs) + buffer
    min_lat, max_lat = min(lats) - buffer, max(lats) + buffer

    polygon = f"{min_lng},{min_lat};{min_lng},{max_lat};{max_lng},{max_lat};{max_lng},{min_lat}"
    print("查询多边形坐标:", polygon)

    poi_url = "https://restapi.amap.com/v3/place/polygon"
    params = {
        "key": key,
        "polygon": polygon,
        "keywords": "收费站",
        "types": "150200",  # 高速收费站分类
        "offset": 50,
        "page": 1,
        "extensions": "all",
    }

    response = requests.get(poi_url, params=params)
    data = response.json()

    if data.get("status") == "1":
        pois = data.get("pois", [])
        if pois:
            print(f"找到收费站数量：{len(pois)}")
            for poi in pois:
                name = poi.get("name")
                location = poi.get("location")
                address = poi.get("address")
                print(f"收费站名称: {name}, 位置: {location}, 地址: {address}")
        else:
            print("未找到收费站，建议适当扩大缓冲范围或改用关键词搜索接口。")
    else:
        print("查询失败，错误信息：", data.get("info"))

def main():
    file_path = "jingshi_code.txt"  # 你的轨迹坐标文件路径
    polyline_points = read_polyline_points(file_path)
    query_toll_stations(polyline_points)

if __name__ == "__main__":
    main()
