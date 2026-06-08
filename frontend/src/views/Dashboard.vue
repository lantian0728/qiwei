<template>
  <div class="dashboard">
    <!-- 指标条 -->
    <div class="stat-row">
      <div class="stat-card" v-for="c in cards" :key="c.label">
        <div class="stat-icon" :style="{ background: c.color + '1a', color: c.color }">
          <el-icon :size="20"><component :is="c.icon" /></el-icon>
        </div>
        <div>
          <div class="stat-value">{{ c.value }}</div>
          <div class="stat-label">{{ c.label }}</div>
        </div>
      </div>
    </div>

    <el-row :gutter="16" style="margin-top:16px">
      <!-- 今日必须处理 -->
      <el-col :span="14">
        <div class="panel">
          <div class="panel-head">
            <span>今日必须处理 <el-tag size="small" type="danger" round>{{ actions.length }}</el-tag></span>
            <el-link type="primary" :underline="false" @click="$router.push('/staff')">查看客服效能 →</el-link>
          </div>
          <div v-if="!actions.length" class="empty">🎉 今日暂无待处理事项</div>
          <div v-for="(a, i) in actions" :key="i" class="action-item" @click="goGroup(a.chat_id)">
            <span class="dot" :class="a.level"></span>
            <el-tag size="small" effect="plain" class="action-type">{{ a.type }}</el-tag>
            <span class="action-text">{{ a.text }}</span>
          </div>
        </div>

        <!-- AI 今日群情报 -->
        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><span>AI 今日群情报</span><el-tag size="small" type="info">智谱</el-tag></div>
          <div class="ai-brief">
            <el-icon class="ai-ico" :size="18"><MagicStick /></el-icon>
            <span>{{ aiBrief }}</span>
          </div>
          <div class="ai-tip">提示：在群档案页点「智谱分析」可生成单群情绪与风险洞察；后续将自动每日推送全局情报。</div>
        </div>
      </el-col>

      <!-- 右侧：健康分布 + 首响榜 -->
      <el-col :span="10">
        <div class="panel">
          <div class="panel-head"><span>群活跃度分布</span></div>
          <div ref="pieRef" style="height:240px"></div>
        </div>
        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><span>客服首响榜(近7日)</span></div>
          <div v-for="(s, i) in topStaff" :key="s.userid" class="rank-row">
            <span class="rank-no" :class="{ top: i < 3 }">{{ i + 1 }}</span>
            <span class="rank-name">{{ s.name }}</span>
            <span class="rank-metric">{{ s.median_first_response }}<small>分(中位)</small></span>
            <el-tag size="small" :type="s.timeout_rate > 20 ? 'danger' : 'success'" effect="plain">
              超时{{ s.timeout_rate }}%
            </el-tag>
          </div>
          <div v-if="!topStaff.length" class="empty">暂无数据</div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { groupApi, dashboardApi, staffApi, aiApi } from '@/api'

const router = useRouter()
const overview = ref<any>({})
const actions = ref<any[]>([])
const topStaff = ref<any[]>([])
const briefText = ref('')
const pieRef = ref<HTMLElement>()

const cards = computed(() => [
  { label: '监测群数', value: overview.value.total_groups ?? 0, color: '#409EFF', icon: 'ChatLineSquare' },
  { label: '群成员', value: overview.value.total_members ?? 0, color: '#67C23A', icon: 'User' },
  { label: '今日消息', value: overview.value.today_messages ?? 0, color: '#E6A23C', icon: 'ChatDotRound' },
  { label: '今日活跃', value: overview.value.today_active_members ?? 0, color: '#9254DE', icon: 'TrendCharts' },
  { label: '待处理', value: actions.value.length, color: '#F56C6C', icon: 'Warning' },
])

const aiBrief = computed(() => {
  if (briefText.value) return briefText.value
  const ov = overview.value
  if (!ov.total_groups) return '暂无数据，点右上角「同步数据」生成。'
  const d = ov.level_distribution || {}
  return `今日 ${ov.total_groups} 个群共 ${ov.today_messages || 0} 条消息，` +
    `活跃成员 ${ov.today_active_members || 0} 人，平均回复率 ${ov.avg_reply_rate || 0}%；` +
    `其中沉默群 ${d.silent || 0} 个、低活跃 ${d.low || 0} 个需关注，未读预警 ${ov.unread_alerts || 0} 条。`
})

const goGroup = (chatId: string) => { if (chatId) router.push(`/groups/${chatId}`) }

const renderPie = () => {
  if (!pieRef.value) return
  const chart = echarts.init(pieRef.value)
  const d = overview.value.level_distribution || {}
  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, icon: 'circle' },
    series: [{
      type: 'pie', radius: ['45%', '70%'],
      label: { formatter: '{b}\n{c}' },
      data: [
        { value: d.high || 0, name: '高活跃', itemStyle: { color: '#67C23A' } },
        { value: d.normal || 0, name: '正常', itemStyle: { color: '#409EFF' } },
        { value: d.low || 0, name: '低活跃', itemStyle: { color: '#E6A23C' } },
        { value: d.silent || 0, name: '沉默', itemStyle: { color: '#C0C4CC' } },
      ],
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  overview.value = await groupApi.overview()
  const ta: any = await dashboardApi.todayActions()
  actions.value = ta.actions || []
  const rank: any = await staffApi.ranking()
  topStaff.value = (rank || []).slice(0, 5)
  try {
    const b: any = await aiApi.brief()
    if (b && b.brief) briefText.value = b.brief
  } catch {}
  renderPie()
})
</script>

<style scoped>
.stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; }
.stat-card {
  background: #fff; border-radius: 12px; padding: 18px; display: flex; align-items: center; gap: 14px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.stat-value { font-size: 24px; font-weight: 700; line-height: 1.1; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }

.panel { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.panel-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 15px; font-weight: 600; margin-bottom: 14px;
}
.panel-head span { display: flex; align-items: center; gap: 8px; }

.action-item {
  display: flex; align-items: center; gap: 10px; padding: 12px 8px;
  border-radius: 8px; cursor: pointer; transition: background 0.15s;
}
.action-item:hover { background: #f5f7fa; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.high { background: #F56C6C; box-shadow: 0 0 0 3px #f56c6c22; }
.dot.medium { background: #E6A23C; box-shadow: 0 0 0 3px #e6a23c22; }
.dot.low { background: #909399; }
.action-type { flex-shrink: 0; }
.action-text { color: #303133; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { text-align: center; color: #c0c4cc; padding: 24px 0; font-size: 14px; }

.ai-brief { display: flex; gap: 10px; background: #f4f1ff; border-radius: 8px; padding: 14px; color: #5a4b8a; line-height: 1.7; font-size: 14px; }
.ai-ico { color: #9254DE; flex-shrink: 0; margin-top: 2px; }
.ai-tip { color: #909399; font-size: 12px; margin-top: 10px; }

.rank-row { display: flex; align-items: center; gap: 12px; padding: 9px 4px; border-bottom: 1px solid #f5f5f5; }
.rank-row:last-child { border-bottom: none; }
.rank-no { width: 22px; height: 22px; border-radius: 6px; background: #f0f2f5; color: #909399; font-size: 13px; display: flex; align-items: center; justify-content: center; font-weight: 600; }
.rank-no.top { background: #fff3e0; color: #E6A23C; }
.rank-name { flex: 1; font-size: 14px; }
.rank-metric { font-weight: 700; color: #303133; }
.rank-metric small { font-size: 12px; color: #909399; font-weight: 400; }
</style>
