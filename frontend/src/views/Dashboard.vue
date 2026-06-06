<template>
  <div class="dashboard">
    <!-- 指标卡 -->
    <el-row :gutter="16">
      <el-col :span="4" v-for="card in cards" :key="card.label">
        <div class="stat-card" :style="{ borderTopColor: card.color }">
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <!-- 活跃度分布饼图 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><b>群活跃度分布</b></template>
          <div ref="pieRef" style="height:320px"></div>
        </el-card>
      </el-col>

      <!-- 四级分类卡片 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><b>四级活跃度概览</b></template>
          <div class="level-grid">
            <div v-for="lv in levels" :key="lv.level" class="level-box"
                 :style="{ background: lv.color + '15', borderColor: lv.color }"
                 @click="goLevel(lv.level)">
              <div class="level-name" :style="{ color: lv.color }">{{ lv.level_name }}</div>
              <div class="level-count">{{ lv.count }}<span>个群</span></div>
              <div class="level-percent">占比 {{ lv.percent }}%</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { groupApi } from '@/api'

const router = useRouter()
const overview = ref<any>({})
const levels = ref<any[]>([])
const pieRef = ref<HTMLElement>()

const cards = computed(() => [
  { label: '监测群数', value: overview.value.total_groups ?? 0, color: '#409EFF' },
  { label: '群成员总数', value: overview.value.total_members ?? 0, color: '#67C23A' },
  { label: '今日消息', value: overview.value.today_messages ?? 0, color: '#E6A23C' },
  { label: '今日活跃成员', value: overview.value.today_active_members ?? 0, color: '#F56C6C' },
  { label: '平均回复率', value: (overview.value.avg_reply_rate ?? 0) + '%', color: '#909399' },
  { label: '未读预警', value: overview.value.unread_alerts ?? 0, color: '#F56C6C' },
])

const goLevel = (level: number) => router.push({ path: '/groups', query: { level } })

const renderPie = () => {
  if (!pieRef.value) return
  const chart = echarts.init(pieRef.value)
  const dist = overview.value.level_distribution || {}
  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '70%'], avoidLabelOverlap: false,
      label: { formatter: '{b}: {c}' },
      data: [
        { value: dist.high || 0, name: '高活跃', itemStyle: { color: '#67C23A' } },
        { value: dist.normal || 0, name: '正常', itemStyle: { color: '#409EFF' } },
        { value: dist.low || 0, name: '低活跃', itemStyle: { color: '#E6A23C' } },
        { value: dist.silent || 0, name: '沉默', itemStyle: { color: '#909399' } },
      ],
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  overview.value = await groupApi.overview()
  const summary: any = await groupApi.levelSummary()
  levels.value = summary.levels || []
  renderPie()
})
</script>

<style scoped>
.stat-card {
  background: #fff; border-radius: 8px; padding: 20px; text-align: center;
  border-top: 3px solid #409EFF;
}
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-label { font-size: 13px; color: #909399; margin-top: 6px; }
.level-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.level-box {
  border: 1px solid; border-radius: 8px; padding: 20px; text-align: center; cursor: pointer;
  transition: transform 0.2s;
}
.level-box:hover { transform: translateY(-4px); }
.level-name { font-size: 16px; font-weight: 600; }
.level-count { font-size: 26px; font-weight: 700; margin: 8px 0; color: #303133; }
.level-count span { font-size: 12px; color: #909399; font-weight: 400; margin-left: 4px; }
.level-percent { font-size: 12px; color: #909399; }
</style>
