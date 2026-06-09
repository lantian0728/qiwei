<template>
  <div class="cust-biz" v-loading="loading">
    <div class="hd">
      <h3>客户业务量 <small>近 {{ days }} 天 vs 上 {{ days }} 天</small></h3>
      <el-radio-group v-model="days" size="small" @change="load">
        <el-radio-button :value="30">近30天</el-radio-button>
        <el-radio-button :value="60">近60天</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="dropping.length" class="drop-warn">
      ⚠️ 掉量预警：<b>{{ dropping.length }}</b> 个客户单量跌一半以上 ——
      <span v-for="d in dropping" :key="d.user_number" class="drop-c">
        {{ d.username }}（{{ d.prev_orders }}→{{ d.cur_orders }}单）
      </span>
    </div>

    <el-table :data="customers" size="default" max-height="640" :default-sort="{ prop: 'cur_orders', order: 'descending' }">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column prop="username" label="客户" min-width="160" show-overflow-tooltip />
      <el-table-column prop="cur_orders" label="本期单量" width="100" align="center" sortable />
      <el-table-column prop="prev_orders" label="上期单量" width="100" align="center" />
      <el-table-column prop="order_change" label="单量环比" width="110" align="center" sortable>
        <template #default="{ row }">
          <span :style="{ color: row.order_change < 0 ? '#F56C6C' : row.order_change > 0 ? '#67C23A' : '#909399', fontWeight: 600 }">
            {{ row.order_change > 0 ? '+' : '' }}{{ row.order_change }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="cur_weight" label="本期货量(kg)" width="120" align="center">
        <template #default="{ row }">{{ row.cur_weight > 0 ? row.cur_weight : '—' }}</template>
      </el-table-column>
      <el-table-column prop="cur_amount" label="本期金额" width="120" align="center">
        <template #default="{ row }">{{ row.cur_amount > 0 ? row.cur_amount : '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.dropping" type="danger" size="small">掉量</el-tag>
          <el-tag v-else-if="row.order_change > 20" type="success" size="small">增长</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!loading && !customers.length" class="empty">暂无数据（确认 TMS 已配置、近期有运单）</div>
    <div class="tip">说明：单量最准；货量/金额为「—」表示该单未结算/未称重。掉量预警 = 上期≥4单且本期跌一半。</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { trackingApi } from '@/api'
import { startTask } from '@/utils/loading'

const loading = ref(false)
const days = ref(30)
const customers = ref<any[]>([])
const dropping = ref<any[]>([])

const load = async () => {
  loading.value = true
  const t = startTask('📊 正在汇总客户业务量')
  try {
    const r: any = await trackingApi.customerBusiness(days.value)
    customers.value = r.customers || []
    dropping.value = r.dropping || []
    ElMessage.success(`已加载 ${customers.value.length} 个客户`)
  } catch (e: any) {
    ElMessage.error('加载失败：' + (e?.response?.data?.detail || e?.message || '稍后重试'))
  } finally {
    loading.value = false
    t.close()
  }
}

onMounted(load)
</script>

<style scoped>
.cust-biz { background: #fff; border-radius: 12px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.hd h3 { margin: 0; font-size: 16px; }
.hd small { color: #909399; font-weight: 400; font-size: 13px; margin-left: 8px; }
.drop-warn { background: #fef0f0; color: #F56C6C; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 13px; line-height: 1.8; }
.drop-c { margin-right: 6px; }
.empty { text-align: center; color: #c0c4cc; padding: 30px 0; }
.tip { color: #909399; font-size: 12px; margin-top: 12px; }
</style>
