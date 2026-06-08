<template>
  <el-container class="layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <el-icon size="24" color="#fff"><ChatDotRound /></el-icon>
        <span>企微群会话分析</span>
      </div>
      <el-menu :default-active="activeMenu" router class="menu"
               background-color="#1f2d3d" text-color="#bfcbd9" active-text-color="#fff">
        <el-menu-item index="/dashboard"><el-icon><Odometer /></el-icon><span>经营驾驶舱</span></el-menu-item>
        <el-menu-item index="/staff"><el-icon><Avatar /></el-icon><span>客服效能</span></el-menu-item>
        <el-menu-item index="/ai-report"><el-icon><MagicStick /></el-icon><span>AI群日报</span></el-menu-item>
        <el-menu-item index="/churn"><el-icon><TrendCharts /></el-icon><span>客户健康度</span></el-menu-item>
        <el-menu-item index="/risk"><el-icon><Warning /></el-icon><span>投诉雷达</span></el-menu-item>
        <el-menu-item index="/tracking"><el-icon><Search /></el-icon><span>查件</span></el-menu-item>
        <el-menu-item index="/groups"><el-icon><ChatLineSquare /></el-icon><span>群档案</span></el-menu-item>
        <el-menu-item index="/alerts"><el-icon><Bell /></el-icon><span>预警中心</span></el-menu-item>
        <el-menu-item index="/admin"><el-icon><Setting /></el-icon><span>配置</span></el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-title">{{ currentTitle }}</div>
        <div class="header-right">
          <el-button size="small" :loading="syncing" @click="handleSync">
            <el-icon><Refresh /></el-icon>&nbsp;同步数据
          </el-button>
          <el-dropdown @command="handleCommand">
            <span class="user">
              <el-icon><UserFilled /></el-icon>
              {{ userInfo?.real_name || userInfo?.username || '未登录' }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { groupApi } from '@/api'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const userInfo = authStore.userInfo
const syncing = ref(false)

const activeMenu = computed(() => '/' + (route.path.split('/')[1] || 'dashboard'))
const currentTitle = computed(() => (route.meta.title as string) || '企微群会话分析系统')

const handleSync = async () => {
  syncing.value = true
  try {
    const res: any = await groupApi.sync()
    ElMessage.success(res.message || '同步任务已触发')
  } finally {
    syncing.value = false
  }
}

const handleCommand = (cmd: string) => {
  if (cmd === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout { height: 100vh; }
.sidebar { background: #1f2d3d; }
.logo {
  height: 60px; display: flex; align-items: center; gap: 10px;
  color: #fff; font-size: 16px; font-weight: 600; padding: 0 20px;
  background: #18222e;
}
.menu { border-right: none; }
.header {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #e4e7ed;
}
.header-title { font-size: 18px; font-weight: 600; }
.header-right { display: flex; align-items: center; gap: 16px; }
.user { display: flex; align-items: center; gap: 4px; cursor: pointer; color: #303133; }
.main { background: #f0f2f5; padding: 20px; }
</style>
