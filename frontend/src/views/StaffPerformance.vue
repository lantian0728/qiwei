<template>
  <div class="staff-perf" v-loading="loading">
    <!-- 概览 -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-value">{{ ov.total_questions ?? 0 }}</div>
        <div class="stat-label">客户提问总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ ov.avg_first_response ?? 0 }}<small>分</small></div>
        <div class="stat-label">平均首响时长</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ ov.median_first_response ?? 0 }}<small>分</small></div>
        <div class="stat-label">首响中位数</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-value">{{ ov.timeout_count ?? 0 }}</div>
        <div class="stat-label">超时/未响应</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-value">{{ ov.timeout_rate ?? 0 }}<small>%</small></div>
        <div class="stat-label">超时率</div>
      </div>
    </div>

    <div class="cfg-tip" v-if="ov.config">
      考核口径：工作时间 {{ ov.config.work_start_hour }}:00–{{ ov.config.work_end_hour }}:00 ·
      超时阈值 {{ ov.config.sla_minutes }} 分钟 ·
      统计区间近 7 日（可在「配置」里调整）
    </div>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="14">
        <div class="panel">
          <div class="panel-head">客服排名榜</div>
          <el-table :data="ranking" size="default">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="name" label="客服" min-width="100" />
            <el-table-column prop="group_count" label="管群数" width="80" align="center" />
            <el-table-column prop="speak_count" label="发言数" width="110" align="center" sortable>
              <template #default="{ row }">
                <b style="color:#409EFF;font-size:15px">{{ row.speak_count }}</b>
                <span style="color:#c0c4cc;font-size:12px"> ({{ row.text_count }}文字)</span>
              </template>
            </el-table-column>
            <el-table-column prop="answered_count" label="响应数" width="80" align="center" />
            <el-table-column label="平均首响" width="100" align="center" sortable
                             :sort-by="'avg_first_response'">
              <template #default="{ row }">
                <span :class="{ slow: row.avg_first_response > (ov.config?.sla_minutes || 30) }">
                  {{ row.avg_first_response }}分
                </span>
              </template>
            </el-table-column>
            <el-table-column label="超时率" width="120" align="center">
              <template #default="{ row }">
                <el-progress :percentage="Math.min(row.timeout_rate, 100)" :stroke-width="10"
                  :color="row.timeout_rate > 20 ? '#F56C6C' : '#67C23A'"
                  :format="() => row.timeout_rate + '%'" />
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!ranking.length" class="empty">暂无客服数据</div>
        </div>
      </el-col>

      <el-col :span="10">
        <div class="panel">
          <div class="panel-head">平均首响对比</div>
          <div ref="barRef" style="height:300px"></div>
        </div>
      </el-col>
    </el-row>

    <div class="panel" style="margin-top:16px">
      <div class="panel-head">
        超时 / 未响应清单
        <el-tag size="small" type="danger">{{ timeouts.length }}</el-tag>
      </div>
      <el-table :data="timeouts" size="small" max-height="360">
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === '未回复' ? 'danger' : 'warning'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="group_name" label="群" min-width="180" show-overflow-tooltip />
        <el-table-column label="客户提问时间" width="170">
          <template #default="{ row }">{{ dayjs(row.customer_time).format('MM-DD HH:mm') }}</template>
        </el-table-column>
        <el-table-column label="等待时长" width="110">
          <template #default="{ row }">{{ row.wait_min ? row.wait_min + ' 分钟' : '—' }}</template>
        </el-table-column>
        <el-table-column prop="staff_name" label="回复客服" width="110">
          <template #default="{ row }">{{ row.staff_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/groups/${row.chat_id}`)">进群档案</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!timeouts.length" class="empty">🎉 区间内无超时</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import dayjs from 'dayjs'
import * as echarts from 'echarts'
import { staffApi } from '@/api'

const loading = ref(false)
const ov = ref<any>({})
const ranking = ref<any[]>([])
const timeouts = ref<any[]>([])
const barRef = ref<HTMLElement>()

const renderBar = () => {
  if (!barRef.value) return
  const chart = echarts.init(barRef.value)
  const data = [...ranking.value].sort((a, b) => a.avg_first_response - b.avg_first_response)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 20, top: 20, bottom: 20 },
    xAxis: { type: 'value', name: '分钟' },
    yAxis: { type: 'category', data: data.map((d) => d.name) },
    series: [{
      type: 'bar', data: data.map((d) => d.avg_first_response),
      itemStyle: { color: '#409EFF', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', formatter: '{c}分' },
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  loading.value = true
  try {
    const [o, r, t] = await Promise.all([
      staffApi.overview(), staffApi.ranking(), staffApi.timeouts(),
    ])
    ov.value = o
    ranking.value = r as any
    timeouts.value = t as any
    await nextTick()
    renderBar()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; }
.stat-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.stat-card.warn .stat-value { color: #F56C6C; }
.stat-value { font-size: 26px; font-weight: 700; }
.stat-value small { font-size: 13px; color: #909399; font-weight: 400; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 6px; }
.cfg-tip { margin-top: 12px; font-size: 12px; color: #909399; background: #f5f7fa; padding: 8px 14px; border-radius: 8px; }
.panel { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.panel-head { font-size: 15px; font-weight: 600; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
.empty { text-align: center; color: #c0c4cc; padding: 24px 0; font-size: 14px; }
.slow { color: #F56C6C; font-weight: 600; }
</style>
