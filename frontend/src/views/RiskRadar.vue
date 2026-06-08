<template>
  <div class="risk" v-loading="loading">
    <div class="stat-row">
      <div class="stat-card danger"><div class="v">{{ highCount }}</div><div class="l">高风险群</div></div>
      <div class="stat-card warn"><div class="v">{{ mediumCount }}</div><div class="l">风险苗头</div></div>
      <div class="stat-card"><div class="v">{{ negCount }}</div><div class="l">负面情绪群</div></div>
      <div class="stat-card"><div class="v">{{ riskAlerts.length }}</div><div class="l">投诉风险预警</div></div>
    </div>

    <el-row :gutter="16">
      <el-col :span="15">
        <div class="panel">
          <div class="panel-head">风险群清单(按风险排序)</div>
          <div v-for="s in riskGroups" :key="s.chat_id" class="risk-item" @click="$router.push(`/groups/${s.chat_id}`)">
            <el-tag :type="riskType(s.risk)" effect="dark" size="small">{{ s.risk_name }}</el-tag>
            <div class="ri-main">
              <div class="ri-name">{{ s.group_name }}</div>
              <div class="ri-sum">{{ s.summary }}</div>
            </div>
            <div class="ri-kws">
              <el-tag v-for="k in s.keywords.slice(0,3)" :key="k" size="small" type="danger" effect="plain">{{ k }}</el-tag>
            </div>
          </div>
          <div v-if="!riskGroups.length" class="empty">🎉 暂无风险群</div>
        </div>
      </el-col>
      <el-col :span="9">
        <div class="panel">
          <div class="panel-head">风险关键词云</div>
          <div ref="cloudRef" style="height:260px"></div>
          <div v-if="!keywords.length" class="empty">暂无关键词</div>
        </div>
        <div class="panel" style="margin-top:16px">
          <div class="panel-head">情绪分布</div>
          <div ref="sentiRef" style="height:200px"></div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { aiApi, alertApi } from '@/api'

const loading = ref(false)
const summaries = ref<any[]>([])
const riskAlerts = ref<any[]>([])
const cloudRef = ref<HTMLElement>()
const sentiRef = ref<HTMLElement>()

const riskGroups = computed(() => summaries.value.filter((s) => s.risk === 'high' || s.risk === 'medium'))
const highCount = computed(() => summaries.value.filter((s) => s.risk === 'high').length)
const mediumCount = computed(() => summaries.value.filter((s) => s.risk === 'medium').length)
const negCount = computed(() => summaries.value.filter((s) => s.sentiment === 'negative').length)
const keywords = computed(() => {
  const freq: Record<string, number> = {}
  summaries.value.forEach((s) => (s.keywords || []).forEach((k: string) => { if (k) freq[k] = (freq[k] || 0) + 1 }))
  return Object.entries(freq).map(([name, value]) => ({ name, value }))
})
const riskType = (r: string) => ({ high: 'danger', medium: 'warning', low: 'info' } as any)[r] || 'info'

const renderCloud = () => {
  if (!cloudRef.value || !keywords.value.length) return
  const chart = echarts.init(cloudRef.value)
  const max = Math.max(...keywords.value.map((k) => k.value))
  chart.setOption({
    tooltip: {},
    series: [{
      type: 'graph', layout: 'force', roam: true,
      force: { repulsion: 120, edgeLength: 10 },
      label: { show: true, formatter: '{b}' },
      data: keywords.value.map((k) => ({
        name: k.name, symbolSize: 24 + (k.value / max) * 36,
        itemStyle: { color: ['#F56C6C', '#E6A23C', '#9254DE', '#409EFF'][k.value % 4] },
      })),
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}
const renderSenti = () => {
  if (!sentiRef.value) return
  const chart = echarts.init(sentiRef.value)
  const pos = summaries.value.filter((s) => s.sentiment === 'positive').length
  const neu = summaries.value.filter((s) => s.sentiment === 'neutral').length
  const neg = negCount.value
  chart.setOption({
    tooltip: { trigger: 'item' }, legend: { bottom: 0, icon: 'circle' },
    series: [{
      type: 'pie', radius: ['40%', '68%'], label: { formatter: '{b} {c}' },
      data: [
        { value: pos, name: '正面', itemStyle: { color: '#67C23A' } },
        { value: neu, name: '中性', itemStyle: { color: '#909399' } },
        { value: neg, name: '负面', itemStyle: { color: '#F56C6C' } },
      ],
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  loading.value = true
  try {
    summaries.value = (await aiApi.summaries()) as any
    const al: any = await alertApi.list({ page: 1, page_size: 100 })
    riskAlerts.value = (al.items || []).filter((a: any) => a.alert_type === 3)
    await nextTick()
    renderCloud(); renderSenti()
  } finally { loading.value = false }
})
</script>

<style scoped>
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.stat-card .v { font-size: 26px; font-weight: 700; }
.stat-card.danger .v { color: #F56C6C; }
.stat-card.warn .v { color: #E6A23C; }
.stat-card .l { font-size: 12px; color: #909399; margin-top: 6px; }
.panel { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.panel-head { font-size: 15px; font-weight: 600; margin-bottom: 14px; }
.risk-item { display: flex; align-items: center; gap: 12px; padding: 12px 6px; border-bottom: 1px solid #f5f5f5; cursor: pointer; }
.risk-item:hover { background: #fafafa; }
.ri-main { flex: 1; min-width: 0; }
.ri-name { font-weight: 600; font-size: 14px; }
.ri-sum { color: #909399; font-size: 12px; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ri-kws { display: flex; gap: 4px; flex-shrink: 0; }
.empty { text-align: center; color: #c0c4cc; padding: 24px 0; font-size: 14px; }
</style>
