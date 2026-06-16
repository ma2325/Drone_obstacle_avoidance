import json
import os

def convert_segment_to_3d(segment, height=300):
    coords = segment['coords']
    points = []

    # 每两个元素构成一个经纬度对
    for i in range(0, len(coords), 2):
        lng = coords[i]
        lat = coords[i + 1]
        points.append([lng, lat, height])

    return points

def main():
    input_file = 'src/assets/segmented_route.json' #json和脚本放在一个同级路径下
    output_dir = 'routes_3d'

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        segments = json.load(f)

    for i, segment in enumerate(segments):
        points_3d = convert_segment_to_3d(segment)
        filename = f'route_{i}_3d.json'
        filepath = os.path.join(output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as out:
            json.dump(points_3d, out, indent=2)

        print(f'✅ 已保存：{filepath}')

if __name__ == '__main__':
    main()
