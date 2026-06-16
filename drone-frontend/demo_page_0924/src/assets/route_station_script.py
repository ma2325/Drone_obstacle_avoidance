# 用来把站点投影到全路段轨迹上，输出断点坐标和站点分段后的json文件
import json
import math

def distance_squared(p1, p2):
    return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

def project_point_to_segment(p, a, b):
    # 向量 AB 和 AP
    ax, ay = a
    bx, by = b
    px, py = p

    abx = bx - ax
    aby = by - ay
    apx = px - ax
    apy = py - ay

    ab_squared = abx * abx + aby * aby
    if ab_squared == 0:
        return a, 0  # a == b 的退化情况

    t = (apx * abx + apy * aby) / ab_squared
    t = max(0, min(1, t))  # 限制在 [0, 1] 范围内

    qx = ax + t * abx
    qy = ay + t * aby

    return (qx, qy), t

def find_closest_projection(point, coords):
    min_dist = float('inf')
    closest_point = None
    segment_index = -1

    for i in range(0, len(coords) - 2, 2):
        a = (coords[i], coords[i+1])
        b = (coords[i+2], coords[i+3])
        proj, _ = project_point_to_segment((point['lng'], point['lat']), a, b)
        dist = distance_squared(proj, (point['lng'], point['lat']))
        if dist < min_dist:
            min_dist = dist
            closest_point = proj
            segment_index = i

    return {
        'name': point['name'],
        'station': (point['lng'], point['lat']),
        'projection': closest_point,
        'index': segment_index
    }

def split_trajectory_by_stations(trajectory, stations):
    projections = [find_closest_projection(station, trajectory) for station in stations]
    projections.sort(key=lambda x: x['index'])  # 保证顺序

    segments = []
    for i in range(len(projections) - 1):
        start = projections[i]
        end = projections[i + 1]

        seg_coords = []
        seg_coords.extend(start['projection'])

        # 中间轨迹点
        for j in range(start['index'] + 2, end['index'] + 2, 2):
            seg_coords.append(trajectory[j])
            seg_coords.append(trajectory[j + 1])

        seg_coords.extend(end['projection'])

        segments.append({
            "startStation": start['name'],
            "endStation": end['name'],
            "coords": seg_coords
        })

    return segments

# === 主函数 ===
def main():
    # 这里导入要分割的轨迹文件相对路径，放在同级
    with open('src/assets/jingShiCoords.json', 'r', encoding='utf-8') as f:
        trajectory = json.load(f)

    # 这里导入站点文件相对路径，放在同级
    with open('src/assets/station.json', 'r', encoding='utf-8') as f:
        stations = json.load(f)

    segments = split_trajectory_by_stations(trajectory, stations)

    with open('segmented_route.json', 'w', encoding='utf-8') as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)

    print("✅ 已输出分段轨迹：segmented_route.json")

if __name__ == '__main__':
    main()
