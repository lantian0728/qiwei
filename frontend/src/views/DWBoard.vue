<template>
  <div class="dw-board" v-loading="loading">
    <div class="hd">
      <h3>DW 核准看板 <small>转运中 {{ total }} 票 · {{ warehouses.length }} 个仓(推迟仓置顶,逐票核准)</small></h3>
      <div>
        <el-button size="small" @click="$router.push('/warehouse-dw')">更新仓库预约数据</el-button>
        <el-button size="small" type="primary" @click="load">刷新</el-button>
      </div>
    </div>

    <el-collapse v-model="activeWh" v-if="warehouses.length">
      <el-collapse-item v-for="w in warehouses" :key="w.warehouse" :name="w.warehouse">
        <template #title>
          <b style="font-size:15px">{{ w.warehouse }}</b>
          <el-tag :type="w.delay_days>=99?'danger':w.delay_days>=14?'warning':w.delay_days>0?'info':'success'"
                  size="small" style="margin:0 10px">
            {{ w.delay_days>=99 ? w.wh_status : w.delay_days>0 ? ('预约推迟 '+w.delay_days+' 天') : '正常' }}
          </el-tag>
          <span style="color:#909399;font-size:13px">{{ w.count }} 票 · 待核准 {{ w.pending }}</span>
          <el-button v-if="w.pending" size="small" type="primary" plain
                     style="margin-left:12px" @click.stop="approveWh(w)">本仓全部确认</el-button>
        </template>
        <el-table :data="w.items" size="small">
          <el-table-column prop="shipment_id" label="单号" width="110" />
          <el-table-column prop="username" label="客户" min-width="110" show-overflow-tooltip />
          <el-table-column prop="service_name" label="渠道" min-width="150" show-overflow-tooltip />
          <el-table-column prop="ship_date" label="开船" width="70" align="center" />
          <el-table-column label="预计 DW(可改)" width="160">
            <template #default="{ row }">
              <el-date-picker v-model="row.eta_dw" type="date" value-format="YYYY-MM-DD"
                              size="small" style="width:140px" :clearable="false" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.status==='approved'" type="success" size="small">已核准</el-tag>
              <el-button v-else size="small" type="primary" @click="approveOne(w, row)">确认</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
    <div v-else-if="!loading" class="empty">暂无转运中的货</div>
    <div class="tip">预填 DW = 开船日 + 渠道实际时效 + 该仓当前预约推迟。可手动改后再确认。不批约/关单的仓不加推迟天数、需你判断。</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { trackingApi } from '@/api'
import { startTask } from '@/utils/loading'

const loading = ref(false)
const warehouses = ref<any[]>([])
const total = ref(0)
const activeWh = ref<string[]>([])

const load = async () => {
  loading.value = true
  const t = startTask('📊 汇总转运中货 + 预填 DW')
  try {
    const r: any = await trackingApi.dwBoard()
    if (r.computing) {
      ElMessage.info('首次汇总中(拉运单+算DW),约 1 分钟后自动刷新…')
      setTimeout(load, 30000)
      return
    }
    warehouses.value = r.warehouses || []
    total.value = r.total || 0
    activeWh.value = warehouses.value.filter((w) => w.delay_days > 0).map((w) => w.warehouse)
  } finally {
    loading.value = false
    t.close()
  }
}

const approveOne = async (w: any, row: any) => {
  try {
    await trackingApi.dwApprove({
      shipment_id: row.shipment_id, eta_dw: row.eta_dw,
      warehouse: w.warehouse, service_name: row.service_name, delay_days: w.delay_days,
    })
    row.status = 'approved'
    w.pending = w.items.filter((i: any) => i.status === 'pending').length
    ElMessage.success('已核准 ' + row.shipment_id)
  } catch {
    ElMessage.error('核准失败')
  }
}

const approveWh = async (w: any) => {
  const pend = w.items.filter((i: any) => i.status === 'pending')
  const t = startTask(`核准 ${w.warehouse} 本仓 ${pend.length} 票`)
  try {
    for (const row of pend) {
      await trackingApi.dwApprove({
        shipment_id: row.shipment_id, eta_dw: row.eta_dw,
        warehouse: w.warehouse, service_name: row.service_name, delay_days: w.delay_days,
      })
      row.status = 'approved'
    }
    w.pending = 0
    ElMessage.success(`${w.warehouse} 本仓已全部核准`)
  } finally {
    t.close()
  }
}

onMounted(load)
</script>

<style scoped>
.dw-board .hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.hd h3 { margin: 0; font-size: 16px; }
.hd small { color: #909399; font-weight: 400; font-size: 13px; margin-left: 8px; }
.empty { text-align: center; color: #c0c4cc; padding: 40px 0; }
.tip { color: #909399; font-size: 12px; margin-top: 14px; }
:deep(.el-collapse-item__header) { font-weight: 400; }
</style>
