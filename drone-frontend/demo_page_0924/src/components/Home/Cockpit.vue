<template>
  <div class="cockpit-container">
    <!-- 状态信息区域 -->
    <div class="status-section">
      <div class="status-item">
        <span class="label">电池电量</span>
        <span class="value">{{ battery }}%</span>
      </div>
      <div class="status-item">
        <span class="label">剩余作业时间</span>
        <span class="value">{{ remainingWorkTime }}</span>
      </div>
      <div class="status-item">
        <span class="label">剩余飞行时间</span>
        <span class="value">{{ remainingFlightTime }}</span>
      </div>
      <div class="status-item">
        <span class="label">RTK搜星数量</span>
        <span class="value">{{ rtkSatelliteCount }}</span>
      </div>
    </div>

    <!-- 飞行参数与罗盘区域 -->
    <div class="flight-section">
      <div class="compass">
        <div class="compass-face">
          <!-- 方向刻度 N / E / S / W -->
          <div class="tick major" v-for="(d, idx) in ['N', 'E', 'S', 'W']" :key="'major' + idx"
            :style="{ transform: `rotate(${idx * 90}deg)` }">
            <span :class="['label', d === 'N' ? 'north' : '']">{{ d }}</span>
          </div>

          <!-- 细刻度（每10°一个） -->
          <div class="tick minor" v-for="i in 36" :key="'minor' + i" :style="{ transform: `rotate(${(i - 1) * 10}deg)` }">
          </div>

          <!-- 指针 -->
          <div class="needle" :style="{ transform: `translate(-50%, -70%) rotate(${compassAngle}deg)` }"
            aria-label="compass-needle">
            <i class="needle-head"></i>
            <i class="needle-tail"></i>
          </div>

          <!-- 中心圆帽 -->
          <div class="hub"></div>

          <!-- 背景光晕 -->
          <div class="glow"></div>
        </div>

        <!-- 角度读数（0~359） -->
        <div class="heading">
          {{ (Math.round(((compassAngle % 360) + 360) % 360)) }}°
        </div>
      </div>
    </div>


    <!-- 右上角：云台控制区域 -->
    <div class="gimbal-section">
      <div class="gimbal-buttons">
        <div class="direction-icon">
          <el-icon>
            <TopLeft />
          </el-icon>
          <el-icon>
            <ArrowUp />
          </el-icon>
          <el-icon>
            <TopRight />
          </el-icon>
          <el-icon>
            <ArrowUpBold />
          </el-icon>
        </div>
        <button class="gimbal-btn" @click="handleGimbal('Q')">Q</button>
        <button class="gimbal-btn" @click="handleGimbal('W')">W</button>
        <button class="gimbal-btn" @click="handleGimbal('E')">E</button>
        <button class="gimbal-btn" @click="handleGimbal('C')">C</button>
        <div class="direction-icon">
          <el-icon>
            <ArrowLeft />
          </el-icon>
          <el-icon>
            <ArrowDown />
          </el-icon>
          <el-icon>
            <ArrowRight />
          </el-icon>
          <el-icon>
            <ArrowDownBold />
          </el-icon>
        </div>
        <button class="gimbal-btn" @click="handleGimbal('A')">A</button>
        <button class="gimbal-btn" @click="handleGimbal('S')">S</button>
        <button class="gimbal-btn" @click="handleGimbal('D')">D</button>
        <button class="gimbal-btn" @click="handleGimbal('Z')">Z</button>
        <div class="direction-icon">云台控制</div>
        <button class="gimbal-btn" @click="handleGimbal('up')">↑</button>
        <button class="gimbal-btn" @click="handleGimbal('down')">↓</button>
        <button class="gimbal-btn" @click="handleGimbal('left')">←</button>
        <button class="gimbal-btn" @click="handleGimbal('right')">→</button>
      </div>
    </div>

    <!-- 右下角：功能按钮区域 -->
    <div class="func-section">
      <button class="func-btn" @click="handleFunc('restoreRoute')">恢复航线</button>
      <button class="func-btn" @click="handleFunc('returnHome')">返航</button>
      <button class="func-btn danger" style="background: red;"@click="handleFunc('emergencyLand')">紧急降落</button>
      <button class="func-btn danger" style="background: red;" @click="handleFunc('emergencyStop')">急停 [Space]</button>
      <button class="func-btn exit-btn" @click="handleExit">退出中控台</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { TopLeft, ArrowUp, TopRight, ArrowUpBold, ArrowLeft, ArrowDown, ArrowRight, ArrowDownBold, } from '@element-plus/icons-vue';

// 定义emit事件
const emit = defineEmits(['action']);

// 模拟数据，实际需从设备或接口获取
const battery = ref(83);
const remainingWorkTime = ref('26:24');
const remainingFlightTime = ref('40:01');
const rtkSatelliteCount = ref(48);
const flightSpeed = ref(0.00);
const compassAngle = ref(-75.5); // 罗盘角度，可动态更新
const flightAltitude = ref(79.80);
const aslValue = ref(116.95);

// 云台控制事件，实际需和无人机控制逻辑对接
const handleGimbal = (action) => {
  console.log('云台控制动作：', action);
  // 这里可添加向无人机发送控制指令的逻辑
};

// 功能按钮事件，实际需和无人机控制逻辑对接
const handleFunc = (action) => {
  console.log('功能动作：', action);
  // 这里可添加向无人机发送功能指令的逻辑，比如恢复航线、返航等
};

// 退出中控台
const handleExit = () => {
  console.log('退出中控台');
  emit('action', { type: 'exit-cockpit-view' });
};
</script>

<style scoped>
.cockpit-container {
  height: 100%;
  display: flex;
  flex-direction: row;
  gap: 20px; /* 区域间距 */
  align-items: stretch;
  margin-right: 50px;
  /* background-color: #0f1116; */
}

/* 用 flex 比例代替固定宽度 */
.status-section {
  flex: 1;  /* 占比最小 */
  min-width: 100px;
  border-right: 2px solid #817f7f;
}

.flight-section {
  flex: 3;  /* 罗盘区域最大 */
  min-width: 280px;
  border-right: 2px solid #817f7f;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gimbal-section {
  flex: 1,5;
  min-width: 180px;
  border-right: 2px solid #817f7f;
  color: #ffffff;
}

.func-section {
  flex: 0.5;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}


/* 每个功能按钮样式 */
.func-section .func-btn {
  padding: 10px 12px;
  text-align: center;
  background: #2A2A3A;
  color: #fff;
  border-radius: 8px;
  cursor: pointer;
  user-select: none;
  transition: all 0.3s ease;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
  /* 默认立体阴影 */
}

/* 鼠标悬停效果 */
.func-section .func-btn:hover {
  transform: translateY(-3px);
  /* 微微浮起 */
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
  background: #344055;
  /* 背景加深 */
}

/* 点击时效果 */
.func-section .func-btn:active {
  transform: translateY(1px);
  /* 按下去 */
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}


.status-item .value{

    text-align: left;
    margin-top: 20px;
margin-left: 40px;
font-size: 15px;
}

.status-item .label {
  display: block;
  margin-top: 10px;
  margin-left: 40px;
}

.label {
  margin-top: 10px;
  color: #ccc4c4;
  font-size: small;
}

.value {
  color: #ffffff;
}

/* 飞行参数区域框体（保持原宽度，也可按需调整） */
.flight-section {
  width: 380px;
  height: 100%;
  border-right: 2px solid #817f7f;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 外层容器：竖排布局，上面是罗盘，下面是读数 */
.compass {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

/* 罗盘圆盘 */
.compass-face {
  position: relative;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  /* 高光玻璃质感 + 暗色渐变 */
  background:
    radial-gradient(120% 120% at 30% 30%, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0) 35%),
    radial-gradient(80% 80% at 70% 70%, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.6) 60%),
    linear-gradient(135deg, #1a1c22 0%, #0f1116 100%);
  box-shadow:
    inset 0 0 30px rgba(0, 0, 0, 0.5),
    0 10px 25px rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(4px);
}

/* 外圈刻度环（用 conic-gradient 做轮刻纹理） */
.compass-face::before {
  content: "";
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  background:
    conic-gradient(from 0deg,
      rgba(255, 255, 255, 0.25) 0deg 2deg,
      transparent 2deg 10deg);
  mask:
    radial-gradient(circle at center, transparent 62%, black 63%);
  pointer-events: none;
  filter: drop-shadow(0 0 6px rgba(255, 255, 255, 0.15));
}

/* 主要刻度（N/E/S/W） */
.tick.major {
  position: absolute;
  top: 0;
  left: 0;
  inset: 0;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  transform-origin: 50% 50%;
}

.tick.major .label {
  display: inline-block;
  transform: translateY(10px) rotate(0deg);
  color: #d5d8df;
  font-weight: 700;
  letter-spacing: 1px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  user-select: none;
}

.tick.major .label.north {
  color: #4dd2ff;
  /* 北极点高亮色 */
  text-shadow: 0 0 8px rgba(77, 210, 255, 0.5);
}

/* 次刻度（每10°） */
.tick.minor {
  position: absolute;
  top: 0;
  left: 0;
  inset: 0;
  transform-origin: 50% 50%;
}

.tick.minor::after {
  content: "";
  position: absolute;
  top: 6px;
  left: 50%;
  width: 2px;
  height: 10px;
  transform: translateX(-50%);
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.7), rgba(255, 255, 255, 0.0));
  border-radius: 1px;
  opacity: 0.6;
}

/* 指针容器：用 translate 让底部在圆心、再旋转 */
.needle {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 0;
  height: 0;
  transform-origin: 50% 70%;
  transition: transform 240ms cubic-bezier(.2, .8, .2, 1);
  will-change: transform;
}

/* 指针前端（朝向角） */
.needle-head {
  position: absolute;
  left: -5px;
  top: -90px;
  width: 10px;
  height: 95px;
  background:
    linear-gradient(to bottom, #ff7b7b 0%, #ff3d3d 60%, #b60000 100%);
  clip-path: polygon(50% 0%, 100% 70%, 70% 100%, 30% 100%, 0% 70%);
  box-shadow:
    0 3px 10px rgba(255, 61, 61, 0.45),
    0 0 8px rgba(255, 61, 61, 0.35);
  border-top-left-radius: 3px;
  border-top-right-radius: 3px;
}

/* 指针后端（配重） */
.needle-tail {
  position: absolute;
  left: -3px;
  top: -10px;
  width: 6px;
  height: 28px;
  background: linear-gradient(#99e2ff, #4dd2ff);
  border-radius: 3px;
  box-shadow: 0 0 8px rgba(77, 210, 255, 0.35);
}

/* 中心遮盖帽 */
.hub {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 18px;
  height: 18px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #fefefe, #bfc6d1 55%, #6b7482 100%);
  box-shadow:
    inset 0 0 6px rgba(0, 0, 0, 0.6),
    0 2px 6px rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.35);
}

/* 内部光晕 */
.glow {
  position: absolute;
  inset: 20px;
  border-radius: 50%;
  box-shadow: 0 0 50px rgba(77, 210, 255, 0.15) inset;
  pointer-events: none;
}

/* 数字读数 */
.heading {
  color: #e6ebf3;
  font-weight: 700;
  font-size: 18px;
  letter-spacing: 1px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}


.gimbal-buttons {
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
  align-items: center;
}

.direction-icon {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 5px;
  gap: 25px;
  margin-bottom: 5px;
  margin-right: 20px;
}

.gimbal-btn {
  width: 40px;
  height: 40px;
  background-color: #222;
  border: none;
  color: #fff;
  cursor: pointer;
  border-radius: 4px;
}

.func-btn {
  width: 100%;
  background-color: #333;
  border: none;
  color: #fff;
  padding: 8px 0;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  /* 调整字体大小以适应更多文字 */
}

.danger {
  background-color: #f00;
}

/* 新增退出按钮样式 */
.exit-btn {
  background-color: #ff6b6b;
  margin-top: 10px;
  /* 与其他按钮保持距离 */
}

.exit-btn:hover {
  background-color: #ff5252;
}

.func-btn:hover,
.gimbal-btn:hover {
  background-color: #444;
}
</style>