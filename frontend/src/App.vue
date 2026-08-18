<template>
  <div class="app">
    <div class="app-bg"></div>

    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <path d="M7 9h2m4 0h4M7 13h2m4 0h4M7 17h8" stroke-linecap="round" />
          </svg>
        </div>
        <div class="logo-text">
          <div class="logo-title">台账中心</div>
          <div class="logo-sub">设备 · 卡 · 盒子</div>
        </div>
      </div>

      <nav class="nav">
        <div class="nav-label">数据模块</div>
        <template v-for="m in menus" :key="m.title">
          <button
            v-if="!m.children"
            class="nav-item"
            :class="{ active: active === m.resource }"
            @click="active = m.resource"
          >
            <el-icon class="nav-icon"><component :is="m.icon" /></el-icon>
            <span>{{ m.title }}</span>
            <span class="nav-dot" />
          </button>

          <div v-else class="nav-group" :class="{ open: groupOpen(m) }">
            <button class="nav-item nav-group-head" @click="toggleGroup(m)">
              <el-icon class="nav-icon"><component :is="m.icon" /></el-icon>
              <span>{{ m.title }}</span>
              <span class="nav-dot" :class="{ active: isGroupActive(m) }" />
            </button>
            <div class="nav-sub">
              <button
                v-for="c in m.children"
                :key="c.resource"
                class="nav-item nav-sub-item"
                :class="{ active: active === c.resource }"
                @click="active = c.resource"
              >
                <span class="nav-sub-bullet" :class="{ active: active === c.resource }" />
                <span>{{ c.title }}</span>
              </button>
            </div>
          </div>
        </template>
      </nav>

      <div class="sidebar-footer">
        <div class="online-dot" />
        <span>服务运行中</span>
        <span class="ver">v2.0</span>
      </div>
    </aside>

    <main class="main">
      <header class="header">
        <div>
          <div class="header-title">{{ current.title }}</div>
          <div class="header-sub">{{ current.desc }}</div>
        </div>
        <div class="header-right">
          <div class="live-badge">
            <span class="live-dot"></span>
            数据实时同步
          </div>
        </div>
      </header>

      <transition name="fade-slide" mode="out-in">
        <LedgerView :key="active" :resource="active" :title="current.title" />
      </transition>
    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Cpu, CreditCard, Box, User, Suitcase, Files } from '@element-plus/icons-vue'
import LedgerView from './LedgerView.vue'

const menus = [
  { resource: 'devices', title: '设备台账', desc: '管理设备、ICCID 卡绑定与部署去向', icon: Cpu },
  { resource: 'iot_cards', title: '物联网卡台账', desc: '管理物联网卡 iccid、运营商与卡状态', icon: CreditCard },
  { resource: 'edge_boxes', title: '边缘盒子台账', desc: '管理边缘盒子 SN、PN 与部署去向', icon: Box },
  { resource: 'customers', title: '客户管理', desc: '维护客户信息，供设备与边缘盒子引用', icon: User },
  {
    title: '资产管理',
    icon: Suitcase,
    children: [
      { resource: 'assets', title: '型号管理', desc: '维护设备类型与型号，供批次引用', icon: Suitcase },
      { resource: 'batches', title: '批次管理', desc: '管理设备 PN 批次，支持批量导入', icon: Files },
    ],
  },
]

const active = ref('devices')
const openGroups = ref(new Set())

function isGroupActive(m) {
  return m.children.some((c) => c.resource === active.value)
}
function groupOpen(m) {
  return isGroupActive(m) || openGroups.value.has(m.title)
}
function toggleGroup(m) {
  if (openGroups.value.has(m.title)) openGroups.value.delete(m.title)
  else openGroups.value.add(m.title)
}

const current = computed(() => {
  const flat = menus.flatMap((m) => m.children || [m])
  return flat.find((m) => m.resource === active.value)
})
</script>

<style scoped>
.app {
  height: 100vh;
  display: flex;
  position: relative;
}

/* ---------- 侧边栏 ---------- */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #141c2e 0%, #0f1626 100%);
  color: #e2e8f0;
  padding: 22px 16px 18px;
  position: relative;
  z-index: 2;
}

.sidebar::after {
  content: '';
  position: absolute;
  top: -40%;
  right: -60%;
  width: 90%;
  height: 80%;
  background: radial-gradient(closest-side, rgba(99, 102, 241, 0.22), transparent);
  pointer-events: none;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px 22px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  margin-bottom: 18px;
}

.logo-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--gradient);
  color: #fff;
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.45);
}
.logo-icon svg {
  width: 24px;
  height: 24px;
}

.logo-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 2px;
  background: linear-gradient(90deg, #fff, #c7d2fe);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.logo-sub {
  font-size: 11px;
  color: #7a8aa3;
  letter-spacing: 1px;
  margin-top: 2px;
}

.nav-label {
  font-size: 11px;
  letter-spacing: 2px;
  color: #5d6d87;
  padding: 0 12px 8px;
}

.nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: #9fb0c8;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #e2e8f0;
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.28), rgba(139, 92, 246, 0.18));
  color: #fff;
  box-shadow: inset 0 0 0 1px rgba(139, 92, 246, 0.35);
}

.nav-icon {
  font-size: 18px;
}

.nav-dot {
  margin-left: auto;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: transparent;
  transition: all 0.2s;
}

.nav-item.active .nav-dot {
  background: var(--primary-3);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.8);
}

.nav-group {
  position: relative;
}

.nav-group-head .nav-dot {
  transition: transform 0.2s ease;
}

.nav-sub {
  display: none;
  margin: 2px 0 2px 14px;
  padding-left: 12px;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  flex-direction: column;
  gap: 2px;
}

.nav-group.open .nav-sub {
  display: flex;
}

.nav-sub-item {
  padding: 9px 12px;
  font-size: 13px;
}

.nav-sub-bullet {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.16);
  flex-shrink: 0;
  transition: all 0.2s;
}

.nav-sub-bullet.active {
  background: var(--primary-3);
  box-shadow: 0 0 8px rgba(34, 211, 238, 0.8);
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 10px 0;
  font-size: 12px;
  color: #7a8aa3;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 12px;
}

.online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.2);
}

.ver {
  margin-left: auto;
  color: #56627a;
  font-size: 11px;
}

/* ---------- 主区域 ---------- */
.main {
  flex: 1;
  overflow: auto;
  padding: 26px 30px 30px;
}

.header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 1px;
  background: linear-gradient(135deg, #1e293b, #6366f1);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.header-sub {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 6px;
}

.header-right {
  display: flex;
  align-items: center;
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #059669;
  background: rgba(52, 211, 153, 0.12);
  border: 1px solid rgba(52, 211, 153, 0.25);
  padding: 7px 14px;
  border-radius: 999px;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  animation: pulse 1.6s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.8); }
}
</style>