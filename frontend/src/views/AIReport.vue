<template>
  <div class="ai-report" v-loading="loading">
    <div class="toolbar">
      <div class="title">
        <el-icon :size="20" color="#9254DE"><MagicStick /></el-icon>
        <span>AI 群日报</span>
        <el-tag size="small" :type="byAi ? 'success' : 'info'">
          {{ byAi ? '智谱AI生成' : '规则版(未配置智谱)' }}
        </el-tag>
      </div>
      <div class="ops">
        <el-date-picker v-model="day" type="date" value-format="YYYY-MM-DD"
                        :clearable="false" @change="load" />
        <el-button type="primary" :loading="running" @click="run">
          <el-icon><Refresh /></el-icon> 生成日报
        </el-button>
      </div>
    </div>

    <!-- 全局情报 -->
    <div class="brief" v-if="brief.brief">
      <el-icon class="b-ico" :size="18"><DataAnalysis /></el-icon>
      <span>{{ brief.brief }}</span>
    </div>

    <!-- 群日报卡片 -->
    <div v-if="!summaries.length && !loading" class="empty">
      <el-empty description="当日暂无日报，点右上角「生成日报」">
        <el-button type="primary" :loading="running" @click="run">立即生成</el-button>
      </el-empty>
    </div>

    <div class="grid">
      <div v-for="s in summaries" :key="s.chat_id" class="card" :class="'risk-' + s.risk"
           @click="$router.push(`/groups/${s.chat_id}`)">
        <div class="card-head">
          <span class="g-name">{{ s.group_name }}</span>
          <el-tag size="small" :type="riskType(s.risk)" effect="dark" v-if="s.risk !== 'none'">
            {{ s.risk_name }}风险
          </el-tag>
        </div>
        <div class="summary">{{ s.summary }}</div>
        <div class="meta">
          <span class="senti" :class="s.sentiment">{{ s.sentiment_name }} {{ s.sentiment_score }}</span>
          <span class="msgs">{{ s.msg_count }} 条</span>
        </div>
        <div class="kws" v-if="s.keywords && s.keywords.length">
          <el-tag v-for="k in s.keywords" :key="k" size="small" effect="plain" type="danger">{{ k }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { aiApi } from '@/api'

const loading = ref(false)
const running = ref(false)
const day = ref(dayjs().format('YYYY-MM-DD'))
const summaries = ref<any[]>([])
const brief = ref<any>({})
const byAi = ref(false)

const riskType = (r: string) => ({ high: 'danger', medium: 'warning', low: 'info' } as any)[r] || 'info'

const load = async () => {
  loading.value = true
  try {
    const params = { report_date: day.value }
    summaries.value = (await aiApi.summaries(params)) as any
    brief.value = (await aiApi.brief(params)) as any
    byAi.value = !!brief.value.by_ai
  } finally {
    loading.value = false
  }
}

const run = async () => {
  running.value = true
  try {
    await aiApi.run({ report_date: day.value })
    ElMessage.success('日报生成中，稍候自动刷新')
    setTimeout(load, 1800)
  } finally {
    running.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.title { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 700; }
.ops { display: flex; gap: 10px; }
.brief {
  display: flex; gap: 10px; background: #f4f1ff; color: #5a4b8a; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 16px; line-height: 1.7; font-size: 14px;
}
.b-ico { color: #9254DE; flex-shrink: 0; margin-top: 2px; }
.empty { background: #fff; border-radius: 12px; padding: 30px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.card {
  background: #fff; border-radius: 12px; padding: 16px 18px; cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04); border-left: 4px solid transparent;
  transition: transform 0.12s, box-shadow 0.12s;
}
.card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,0.08); }
.card.risk-high { border-left-color: #F56C6C; }
.card.risk-medium { border-left-color: #E6A23C; }
.card.risk-low { border-left-color: #409EFF; }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.g-name { font-weight: 600; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.summary { color: #303133; font-size: 14px; line-height: 1.6; min-height: 44px; }
.meta { display: flex; gap: 14px; margin-top: 10px; font-size: 12px; color: #909399; }
.senti.negative { color: #F56C6C; font-weight: 600; }
.senti.positive { color: #67C23A; font-weight: 600; }
.kws { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
</style>
