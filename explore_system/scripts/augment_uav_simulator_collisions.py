#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 uav_simulator（或其它 Gazebo 资源目录）下的 SDF / world 中缺少 <collision> 的 <link>
自动补全碰撞体：从首个 <visual> 复制 <pose> 与 <geometry>（与视觉一致，解决「只有 visual、穿模」）。

用法（在 explore_system 根目录）:
  python3 scripts/augment_uav_simulator_collisions.py --dry-run
  python3 scripts/augment_uav_simulator_collisions.py --yes

环境变量:
  CATKIN_WS  或  UAV_SIM_SRC  指向含 uav_simulator 的目录；默认 ~/catkin_ws/src/uav_simulator

注意:
  - 仅处理「link 内已有 visual、且无任何 collision」的情况；已有 collision 的 link 不修改。
  - 写入前会生成同路径 .bak（若已存在 .bak 则跳过备份）。
  - Actor/插件动态模型若结构非标准 link，可能需手工改仿真包。
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _findall(parent, name: str):
    for ch in list(parent):
        if _local(ch.tag) == name:
            yield ch


def _link_needs_collision(link_el) -> bool:
    has_vis = any(_local(c.tag) == "visual" for c in link_el)
    has_col = any(_local(c.tag) == "collision" for c in link_el)
    return has_vis and not has_col


def _first_visual(link_el):
    for c in link_el:
        if _local(c.tag) == "visual":
            return c
    return None


def _build_collision_from_visual(visual_el, link_name: str):
    geom = None
    pose_el = None
    for ch in visual_el:
        ln = _local(ch.tag)
        if ln == "geometry":
            geom = ch
        elif ln == "pose":
            pose_el = ch
    if geom is None:
        return None
    col = ET.Element("collision")
    col.set("name", "auto_collision_%s" % (link_name or "link").replace(" ", "_")[:48])
    if pose_el is not None:
        col.append(copy.deepcopy(pose_el))
    col.append(copy.deepcopy(geom))
    return col


def _process_root(root):
    """返回本树中新增的 collision 数量。"""
    added = 0
    for link in root.iter():
        if _local(link.tag) != "link":
            continue
        if not _link_needs_collision(link):
            continue
        vis = _first_visual(link)
        if vis is None:
            continue
        lname = link.get("name", "link")
        col = _build_collision_from_visual(vis, lname)
        if col is None:
            continue
        link.append(col)
        added += 1
    return added


def process_file(path: str, dry_run: bool):
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return 0, "parse error: %s" % e
    root = tree.getroot()
    n = _process_root(root)
    if n == 0 or dry_run:
        return n, None
    bak = path + ".bak"
    if not os.path.isfile(bak):
        try:
            with open(path, "rb") as rf:
                data = rf.read()
            with open(bak, "wb") as wf:
                wf.write(data)
        except OSError as e:
            return 0, "backup failed: %s" % e
    try:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    except OSError as e:
        return 0, "write failed: %s" % e
    return n, None


def main():
    ap = argparse.ArgumentParser(description="Augment Gazebo SDF/world with missing link collisions.")
    ap.add_argument(
        "--root",
        default=os.environ.get(
            "UAV_SIM_SRC",
            os.path.join(
                os.path.expanduser(os.environ.get("CATKIN_WS", "~/catkin_ws")),
                "src",
                "uav_simulator",
            ),
        ),
        help="uav_simulator 根目录（内含 worlds/models 等）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只报告会改哪些文件，不写盘")
    ap.add_argument("--yes", action="store_true", help="确认写盘（否则仅 dry-run 语义）")
    args = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        print("错误: 目录不存在: %s" % root, file=sys.stderr)
        print("请设置 CATKIN_WS 或 UAV_SIM_SRC，或将 uav_simulator 克隆到 ~/catkin_ws/src/", file=sys.stderr)
        return 1
    if not args.dry_run and not args.yes:
        print("未指定 --yes，按 dry-run 运行（不写盘）。加 --yes 执行写入。")
        args.dry_run = True

    exts = (".sdf", ".world")
    total_added = 0
    touched = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        # 跳过体积大的构建目录
        low = dirpath.lower()
        if "/build/" in low + "/" or "/devel/" in low + "/" or "/.git/" in low + "/":
            continue
        for fn in filenames:
            if not fn.endswith(exts):
                continue
            fp = os.path.join(dirpath, fn)
            n, err = process_file(fp, dry_run=args.dry_run)
            if err:
                print("跳过 %s: %s" % (fp, err))
                continue
            if n:
                touched += 1
                total_added += n
                mode = "dry-run" if args.dry_run else "已写入"
                print("[%s] %s  -> 新增 %d 个 <collision>" % (mode, fp, n))
    print("完成: 处理文件数=%d, 新增 collision 元素总数=%d" % (touched, total_added))
    if total_added == 0:
        print(
            "提示: 若仍为 0，可能 link 已有 collision、或障碍在 include 的外部模型/插件中，"
            "需打开对应 .sdf 手工补，见 docs/GAZEBO_COLLISION.md"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
