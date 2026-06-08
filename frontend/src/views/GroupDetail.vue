<template>
  <div class="group-detail" v-loading="loading">
    <el-page-header @back="$router.back()" :content="group.group_name || '群详情'" style="margin-bottom:16px" />

    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="never">
          <template #header><b>群信息</b></template>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="群类型">{{ group.group_type_name }}</el-descriptions-item>
            <el-descriptions-item label="群主">{{ group.owner_name }}</el-descriptions-item>
            <el-descriptions-item label="成员数">{{ group.member_count }}</el-descriptions-item>
            <el-descriptions-item label="活跃度">
              <el-tag :color="group.activity_level_color" effect="dark" style="border:none">
                {{ group.activity_level_name }}（{{ group.activity_score }}）
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="重点群">
              <el-switch v-model="group.is_key_group" @change="updateFlag" />
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" style="margin-top:16px">
          <template #header><b>关键指标</b></template>
          <div class="metric"><span>回复率</span><b>{{ stats.reply_stats?.reply_rate ?? 0 }}%</b></div>
          <div class="metric"><span>响应率</span><b>{{ stats.response_stats?.response_rate ?? 0 }}%</b></div>
          <div class="metric"><span>平均响应</span><b>{{ stats.response_time?.avg_response_minutes ?? 0 }}分钟</b></div>
          <div class="metric"><span>沉默成员</span><b>{{ stats.silent_members_count ?? 0 }}人</b></div>
        </el-card>

        <el-card shadow="never" style="margin-top:16px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <b>AI 情绪分析</b>
              <el-button size="small" type="primary" :loading="sentLoading" @click="analyzeSentiment">
                智谱分析
              </el-button>
            </div>
          </template>
          <div v-if="!sentiment" class="sent-empty">点击「智谱分析」识别群内客户情绪与风险</div>
          <div v-else-if="sentiment.available === false" class="sent-empty">
            {{ sentiment.message }}
          </div>
          <div v-else-if="sentiment.analyzed === false" class="sent-empty">
            {{ sentiment.message }}
          </div>
          <div v-else>
            <div class="metric">
              <span>情绪倾向</span>
              <el-tag :type="sentTagType">{{ sentiment.sentiment_name }}（{{ sentiment.score }}分）</el-tag>
            </div>
            <div class="metric">
              <span>风险等级</span>
              <el-tag :type="riskTagType">{{ riskName }}</el-tag>
            </div>
            <div style="margin-top:10px;font-size:13px;color:#606266;line-height:1.6">
              {{ sentiment.summary }}
            </div>
            <div style="margin-top:8px">
              <el-tag v-for="k in (sentiment.keywords || [])" :key="k" size="small"
                      style="margin:2px" effect="plain">{{ k }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="18">
        <!-- AI 今日提炼：过滤后只看重点 -->
        <el-card shadow="never" style="margin-bottom:16px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <b>🔍 AI 今日提炼</b>
              <el-button size="small" type="primary" :loading="digestLoading" @click="loadDigest">
                让智谱提炼今日
              </el-button>
            </div>
          </template>
          <div v-if="!digest" class="sent-empty">点「让智谱提炼今日」，把今天这个群的客户诉求 / 待办 / 风险理成几条给你</div>
          <div v-else-if="!digest.has_data" class="sent-empty">{{ digest.message }}</div>
          <div v-else>
            <p class="digest-sum">{{ digest.summary }}</p>
            <div class="digest-sec" v-if="digest.customer_demands?.length">
              <span class="dlabel">客户诉求</span>
              <ul><li v-for="(x,i) in digest.customer_demands" :key="'d'+i">{{ x }}</li></ul>
            </div>
            <div class="digest-sec" v-if="digest.handled?.length">
              <span class="dlabel ok">已处理</span>
              <ul><li v-for="(x,i) in digest.handled" :key="'h'+i">{{ x }}</li></ul>
            </div>
            <div class="digest-sec" v-if="digest.todos?.length">
              <span class="dlabel warn">待跟进</span>
              <ul><li v-for="(x,i) in digest.todos" :key="'t'+i">{{ x }}</li></ul>
            </div>
            <div class="digest-sec" v-if="digest.risks?.length">
              <span class="dlabel danger">风险</span>
              <ul><li v-for="(x,i) in digest.risks" :key="'r'+i">{{ x }}</li></ul>
            </div>
          </div>
        </el-card>

        <!-- 聊天记录 -->
        <el-card shadow="never" style="margin-bottom:16px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <b>💬 聊天记录（最近 {{ messages.length }} 条）</b>
              <el-button size="small" :loading="msgLoading" @click="loadMessages">刷新</el-button>
            </div>
          </template>
          <div v-if="!messages.length" class="sent-empty">暂无消息（会话存档同步后显示）</div>
          <div v-else class="chat-box">
            <div v-for="(m,i) in messages" :key="'m'+i" class="chat-row" :class="{ staff: m.is_staff }">
              <div class="chat-meta">
                <b>{{ m.sender_name }}</b>
                <span class="role" :class="{ s: m.is_staff }">{{ m.role }}</span>
                <span class="t">{{ m.time }}</span>
              </div>
              <div class="chat-bubble" :class="{ staff: m.is_staff }">{{ m.content }}</div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header><b>近 7 日活跃趋势</b></template>
          <div ref="trendRef" style="height:280px"></div>
        </el-card>

        <el-row :gutter="16" style="margin-top:16px">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>24小时消息分布</b></template>
              <div ref="hourRef" style="height:240px"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>成员发言排名</b></template>
              <el-table :data="stats.member_ranking || []" size="small" max-height="240">
                <el-table-column type="index" label="#" width="50" />
                <el-table-column prop="name" label="成员" />
                <el-table-column prop="msg_count" label="发言数" width="90" align="center" />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { groupApi } from '@/api'
import { startTask } from '@/utils/loading'

defineOptions({ name: 'GroupDetail' })

const route = useRoute()
const chatId = route.params.chatId as string
const group = ref<any>({})
const stats = ref<any>({})
const loading = ref(false)

const sentiment = ref<any>(null)
const sentLoading = ref(false)
const digest = ref<any>(null)
const digestLoading = ref(false)
const messages = ref<any[]>([])
const msgLoading = ref(false)
const RISK_NAMES: any = { none: '无', low: '低', medium: '中', high: '高' }
const riskName = computed(() => RISK_NAMES[sentiment.value?.risk] ?? sentiment.value?.risk ?? '-')
const sentTagType = computed(() => {
  const s = sentiment.value?.sentiment
  return s === 'positive' ? 'success' : s === 'negative' ? 'danger' : 'info'
})
const riskTagType = computed(() => {
  const r = sentiment.value?.risk
  return r === 'high' ? 'danger' : r === 'medium' ? 'warning' : r === 'low' ? 'info' : 'success'
})

const analyzeSentiment = async () => {
  sentLoading.value = true
  try {
    sentiment.value = await groupApi.sentiment(chatId, 7)
  } finally {
    sentLoading.value = false
  }
}

const loadDigest = async () => {
  digestLoading.value = true
  const task = startTask('✨ 正在提炼今日群聊重点')
  try {
    digest.value = await groupApi.digest(chatId)
  } catch (e: any) {
    ElMessage.error('提炼失败：' + (e?.response?.data?.detail || e?.message || '稍后重试'))
  } finally {
    digestLoading.value = false
    task.close()
  }
}

const loadMessages = async () => {
  msgLoading.value = true
  try {
    messages.value = ((await groupApi.messages(chatId)) as any).items || []
  } finally {
    msgLoading.value = false
  }
}
const trendRef = ref<HTMLElement>()
const hourRef = ref<HTMLElement>()

const updateFlag = async () => {
  await groupApi.update(chatId, { is_key_group: group.value.is_key_group })
  ElMessage.success('已更新')
}

const renderTrend = () => {
  if (!trendRef.value) return
  const chart = echarts.init(trendRef.value)
  const trend = stats.value.daily_trend || []
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['消息数', '活跃成员', '活跃度评分'] },
    xAxis: { type: 'category', data: trend.map((t: any) => t.date.slice(5)) },
    yAxis: [{ type: 'value' }, { type: 'value', max: 100 }],
    series: [
      { name: '消息数', type: 'bar', data: trend.map((t: any) => t.total_msgs), itemStyle: { color: '#409EFF' } },
      { name: '活跃成员', type: 'bar', data: trend.map((t: any) => t.active_members), itemStyle: { color: '#67C23A' } },
      { name: '活跃度评分', type: 'line', yAxisIndex: 1, data: trend.map((t: any) => t.activity_score), itemStyle: { color: '#E6A23C' } },
    ],
  })
}

const renderHour = () => {
  if (!hourRef.value) return
  const chart = echarts.init(hourRef.value)
  const dist = stats.value.hourly_distribution || []
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dist.map((d: any) => d.hour + '时') },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: dist.map((d: any) => d.count), itemStyle: { color: '#409EFF' } }],
  })
}

onMounted(async () => {
  loading.value = true
  try {
    const [g, s] = await Promise.all([
      groupApi.detail(chatId), groupApi.stats(chatId, {}), loadMessages(),
    ])
    group.value = g
    stats.value = s
    await nextTick()
    renderTrend()
    renderHour()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
.metric span { color: #909399; font-size: 13px; }
.metric b { color: #303133; }
.sent-empty { color: #909399; font-size: 13px; text-align: center; padding: 12px 0; }
.digest-sum { font-weight: 600; color: #303133; margin: 0 0 12px; line-height: 1.6; }
.digest-sec { margin-bottom: 10px; }
.dlabel { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 4px; background: #ecf5ff; color: #409EFF; }
.dlabel.ok { background: #f0f9eb; color: #67C23A; }
.dlabel.warn { background: #fdf6ec; color: #E6A23C; }
.dlabel.danger { background: #fef0f0; color: #F56C6C; }
.digest-sec ul { margin: 4px 0 0; padding-left: 18px; }
.digest-sec li { font-size: 13px; color: #606266; line-height: 1.7; }
.chat-box { max-height: 420px; overflow-y: auto; padding: 4px; }
.chat-row { margin-bottom: 12px; }
.chat-row.staff { text-align: right; }
.chat-meta { font-size: 12px; color: #909399; margin-bottom: 2px; }
.chat-meta b { color: #606266; margin-right: 6px; }
.chat-meta .role { background: #f4f4f5; color: #909399; padding: 0 6px; border-radius: 3px; margin-right: 6px; }
.chat-meta .role.s { background: #ecf5ff; color: #409EFF; }
.chat-meta .t { color: #c0c4cc; }
.chat-bubble { display: inline-block; max-width: 75%; text-align: left; padding: 8px 12px; border-radius: 8px;
  background: #f4f4f5; color: #303133; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.chat-bubble.staff { background: #ecf5ff; color: #1f6fd6; }
</style>
