# 静态轨迹要1维数组，动态要二维，所以需要把json文件中的数组转化

import json

# 输入输出路径（按需修改为你的绝对路径）
input_path = 'src/assets/route_1.json'
# 输出二维轨迹
output_2d = 'src/assets/route_1_2d.json'
# 输出三维轨迹
output_3d = 'src/assets/route_1_3d.json'
# 固定高度（单位：米）
fixed_height = 300

# 读取一维数组
with open(input_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 检查偶数性
if len(data) % 2 != 0:
    raise ValueError("经纬度数组元素个数不是偶数，检查数据格式！")

# 转换为二维数组
converted = [[data[i], data[i + 1]] for i in range(0, len(data), 2)]


# 转换为三维经纬高数组
converted_3d = [[data[i], data[i + 1], fixed_height] for i in range(0, len(data), 2)]


# 写入二维文件
with open(output_2d, 'w', encoding='utf-8') as f:
    json.dump(converted, f, ensure_ascii=False, indent=2)


# 写入三维文件
with open(output_3d, 'w', encoding='utf-8') as f:
    json.dump(converted_3d, f, ensure_ascii=False, indent=2)    

print(f"✅ 转换成功，已保存为 {output_2d}")
print(f"✅ 转换成功，已保存为 {output_3d}，高度 {fixed_height} 米")