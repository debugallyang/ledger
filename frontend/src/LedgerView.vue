<template>
  <div class="lv">
    <!-- 统计卡片 -->
    <div class="stats" v-loading="statsLoading" element-loading-background="transparent">
      <div class="stat-card" v-for="s in statCards" :key="s.label">
        <div class="stat-icon" :style="{ background: s.bg, color: s.color }">
          <el-icon>
            <component :is="s.icon" />
          </el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="panel toolbar">
      <div class="search-box">
        <el-input v-model="keyword" placeholder="关键词搜索，匹配所有列..." clearable :prefix-icon="Search"
          @input="debouncedSearch">
        </el-input>
      </div>

      <div class="spacer"></div>

      <el-select v-if="hasCustomerCol" v-model="customerFilter" filterable clearable placeholder="按客户筛选"
        style="width: 190px" @change="onCustomerFilter">
        <el-option v-for="c in customerOptions" :key="c" :label="c === '__none__' ? '未分配' : c" :value="c" />
      </el-select>

      <el-button v-if="!isBatches" :icon="Download" class="ghost-btn" @click="downloadTemplate">模板下载</el-button>
      <el-upload v-if="!isBatches" :show-file-list="false" :http-request="doImport" accept=".xlsx,.xls">
        <el-button :icon="Upload" class="ghost-btn">导入 Excel</el-button>
      </el-upload>
      <el-dropdown trigger="click" @command="exportFile">
        <el-button type="primary" :icon="Download">导出</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="xlsx">导出为 Excel (.xlsx)</el-dropdown-item>
            <el-dropdown-item command="csv">导出为 CSV (.csv)</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button :icon="Refresh" circle title="刷新" @click="refresh" />
      <el-button type="danger" :icon="Delete" :disabled="!selection.length" @click="batchDelete" class="danger-btn">
        删除 <span v-if="selection.length">({{ selection.length }})</span>
      </el-button>
      <el-button type="primary" :icon="Plus" @click="openDialog()">新增</el-button>
    </div>

    <!-- 表格 -->
    <div class="panel table-panel">
      <el-table :data="items" v-loading="loading" stripe @selection-change="(rows) => (selection = rows)"
        :header-cell-style="{
          background: 'linear-gradient(180deg,#f8fafc,#f1f5f9)',
          color: '#334155',
          fontWeight: 600,
        }" row-class-name="trow">
        <el-table-column type="selection" width="46" fixed="left" />
        <el-table-column type="index" label="#" width="58" fixed="left" />
        <el-table-column v-for="col in tableColumns" :key="col[0]" :prop="col[0]" :label="col[1]"
          :width="isIccidCol(col[0]) ? 215 : undefined" :min-width="isIccidCol(col[0]) ? undefined : 150"
          show-overflow-tooltip>
          <template #default="{ row }">
            <!-- ICCID 状态着色 -->
            <span v-if="colorBy[col[0]] && row[col[0]]" class="iccid-chip" :class="chipType(row[colorBy[col[0]]])">
              {{ row[col[0]] }}
            </span>
            <span v-else-if="isStatusCol(col) && row[col[0]]" class="status-tag" :class="statusType(row[col[0]])">
              <span class="status-dot"></span>{{ row[col[0]] }}
            </span>
            <span v-else-if="isSnCol(col) && row[col[0]]" class="mono">{{ row[col[0]] }}</span>
            <span v-else-if="isEmpty(row[col[0]])" class="empty-val">—</span>
            <span v-else>{{ row[col[0]] }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" :width="isBatches ? 200 : 150" fixed="right" align="center">
          <template #default="{ row }">
            <el-button v-if="isBatches" link type="success" size="small" @click="openBatchImport(row)">导入</el-button>
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="deleteOne(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && !items.length" class="empty">
        <el-empty :description="total === 0 ? '暂无数据，点击右上角「新增」添加' : '未找到匹配记录'">
          <el-button v-if="total === 0" type="primary" :icon="Plus" @click="openDialog()">新增记录</el-button>
        </el-empty>
      </div>

      <div class="table-footer" v-if="total > 0">
        <span class="count-info">共 <b>{{ total }}</b> 条记录</span>
        <el-pagination layout="sizes, prev, pager, next" :total="total" :current-page="page" :page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]" background @current-change="(p) => { page = p; load() }"
          @size-change="(s) => { pageSize = s; page = 1; load() }" />
      </div>
    </div>

    <!-- 编辑 / 新增弹窗 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑记录' : '新增记录'" width="680px" align-center destroy-on-close>
      <el-form :model="form" label-width="120px" class="form-grid">
        <el-form-item v-for="col in formColumns" :key="col[0]" :label="col[1]">
          <!-- 日期选择 -->
          <el-date-picker v-if="isDateField(col[0])" v-model="form[col[0]]" type="date" value-format="YYYY-MM-DD"
            placeholder="选择日期" clearable style="width: 100%" />
          <!-- 下拉选择 -->
          <template v-else-if="selectCfg(col[0])">
            <el-select v-model="form[col[0]]" clearable filterable :placeholder="selPlaceholder(col[0])"
              style="width: 100%" @change="(v) => onSelectChange(col[0], v)">
              <el-option v-for="opt in selOptions(col[0])" :key="opt.value" :label="opt.label" :value="opt.value">
                <span>{{ opt.label }}</span>
                <span v-if="opt.extra" class="opt-extra">{{ opt.extra }}</span>
              </el-option>
            </el-select>
          </template>
          <!-- 只读引用 -->
          <template v-else-if="isReadonly(col[0])">
            <el-input :model-value="form[col[0]] || '—'" disabled>
              <template #append>
                <span class="ref-tag">{{ readonlyHints[col[0]] || '自动引用' }}</span>
              </template>
            </el-input>
          </template>
          <!-- 普通输入 -->
          <el-input v-else v-model="form[col[0]]" clearable placeholder="（可留空）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :icon="Check" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批次批量导入弹窗 -->
    <el-dialog v-model="importDialogVisible" title="批量导入设备" width="520px" align-center>
      <el-form label-width="110px">
        <el-form-item label="批次 PN">
          <el-tag type="info" class="pn-tag">{{ importBatch?.pn }}</el-tag>
        </el-form-item>
        <el-form-item label="目标台账">
          <el-radio-group v-model="importTarget">
            <el-radio value="devices">设备台账</el-radio>
            <el-radio value="edge_boxes">边缘盒子台账</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Excel 文件">
          <el-upload :show-file-list="false" :http-request="doBatchImport" accept=".xlsx,.xls">
            <el-button :icon="Upload" type="primary" :loading="batchImporting">选择文件并导入</el-button>
          </el-upload>
          <div class="import-tip">文件表头需与所选目标台账一致（如 入库时间/设备SN/客户 等），导入后自动带上该批次 PN</div>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Plus, Delete, Download, Upload, Refresh, Check,
  Collection, CircleCheck, Clock, Location, Files, User,
} from '@element-plus/icons-vue'
import { api } from './api'

const props = defineProps({
  resource: { type: String, required: true },
  title: { type: String, required: true },
})

const columns = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const loading = ref(false)
const statsLoading = ref(false)
const saving = ref(false)
const selection = ref([])
const dialogVisible = ref(false)
const form = reactive({})
const allRows = ref([])

const selects = ref({})
const readonlyCols = ref([])
const readonlyHints = ref({})
const hiddenInTable = ref([])
const hiddenInForm = ref([])
const dateFields = ref([])
const colorBy = ref({})
const pools = ref({})

const isBatches = computed(() => props.resource === 'batches')
const importDialogVisible = ref(false)
const importBatch = ref(null)
const importTarget = ref('devices')
const batchImporting = ref(false)

const STATUS_COLORS = {
  激活: 'ok', 启用: 'ok', 正常: 'ok', 运行中: 'ok', 使用中: 'ok',
  未激活: 'info', 未启用: 'info', 待激活: 'info', 空闲中: 'idle',
  销户: 'bad', 注销: 'bad', 损坏: 'bad', 报废: 'bad', 故障: 'bad',
  短路损坏: 'bad', 停用: 'warn', 暂停: 'warn',
}

const STAT_CFG = {
  devices: {
    primary: 'device_status',
    activeStatuses: ['使用中'],
    pendingStatuses: [],
    activeLabel: '已部署',
    metric: { label: '已分配客户', icon: User, fn: (r) => new Set(r.map((x) => (x.customer || '').trim()).filter(Boolean)).size },
  },
  iot_cards: { primary: 'card_status', metric: { label: '已绑定设备', icon: Files, fn: (r) => r.filter((x) => x.device_sn).length } },
  edge_boxes: {
    primary: 'device_status',
    activeStatuses: ['使用中'],
    pendingStatuses: [],
    activeLabel: '已部署',
    metric: { label: '已分配客户', icon: User, fn: (r) => new Set(r.map((x) => (x.customer || '').trim()).filter(Boolean)).size },
  },
  customers: { primary: 'name', metric: { label: '被设备引用', icon: Location, fn: (r) => r.length }, forcePending: true },
  assets: { primary: 'asset_model', metric: { label: '型号总数', icon: Files, fn: (r) => r.length }, forcePending: true },
  batches: { primary: 'pn', metric: { label: '设备总数', icon: Files, fn: (r) => r.reduce((s, x) => s + (Number(x.count) || 0), 0) }, forcePending: true },
}

const tableColumns = computed(() => columns.value.filter((c) => !hiddenInTable.value.includes(c[0])))
const formColumns = computed(() => columns.value.filter((c) => !hiddenInForm.value.includes(c[0])))

const statCards = computed(() => {
  const rows = allRows.value
  const cfg = STAT_CFG[props.resource] || { primary: columns.value[0]?.[0], metric: { label: '记录数', icon: Files, fn: (r) => r.length } }
  const cards = [
    { label: '总记录', value: rows.length, icon: Collection, bg: 'linear-gradient(135deg,#6366f1,#8b5cf6)', color: '#fff' },
  ]
  if (!cfg.forcePending) {
    const deployed = rows.filter((r) => (cfg.activeStatuses || ['激活', '启用', '正常']).includes(r[cfg.primary])).length
    cards.push({
      label: cfg.activeLabel || '有效启用',
      value: deployed,
      icon: CircleCheck,
      bg: 'linear-gradient(135deg,#10b981,#34d399)',
      color: '#fff',
    })
    const pendStatuses = cfg.pendingStatuses || ['未激活', '未启用']
    if (pendStatuses.length) {
      cards.push({
        label: '待激活',
        value: rows.filter((r) => pendStatuses.includes(r[cfg.primary])).length,
        icon: Clock,
        bg: 'linear-gradient(135deg,#f59e0b,#fbbf24)',
        color: '#fff',
      })
    }
  }
  cards.push({
    label: cfg.metric.label,
    value: cfg.metric.fn(rows),
    icon: cfg.metric.icon,
    bg: 'linear-gradient(135deg,#06b6d4,#22d3ee)',
    color: '#fff',
  })
  return cards
})

const hasCustomerCol = computed(() => columns.value.some((c) => c[0] === 'customer'))
const customerFilter = ref('')
const customerOptions = ref([])

async function loadCustomerOptions() {
  try {
    const { data } = await api.all(props.resource)
    const set = new Set()
    data.items.forEach((r) => {
      const c = (r.customer || '').trim()
      if (c) set.add(c)
    })
    const opts = [...set].sort()
    if (data.items.some((r) => !(r.customer || '').trim())) opts.push('__none__')
    customerOptions.value = opts
  } catch {
    customerOptions.value = []
  }
}

function onCustomerFilter() {
  page.value = 1
  refresh()
}

function isEmpty(v) {
  return v === null || v === undefined || v === ''
}
function isStatusCol(col) {
  return col[1].includes('状态')
}
function isSnCol(col) {
  return ['设备SN', 'SN', 'iccid', 'SSID', 'ICCID1', 'ICCID2', 'PN'].includes(col[1])
}
function statusType(v) {
  return STATUS_COLORS[v] || 'info'
}
function chipType(v) {
  const t = statusType(v)
  return t === 'ok' ? 'chip-ok' : t === 'warn' ? 'chip-warn' : t === 'bad' ? 'chip-bad' : 'chip-info'
}
function isIccidCol(field) {
  return !!colorBy.value[field]
}
function isDateField(field) {
  return dateFields.value.includes(field)
}
function selectCfg(field) {
  return selects.value[field]
}
function isReadonly(field) {
  return readonlyCols.value.includes(field)
}
function selPlaceholder(field) {
  const cfg = selects.value[field]
  if (cfg && !Array.isArray(cfg)) return `从「${fromTitle(cfg.from)}」中选择`
  return '请选择'
}
function fromTitle(res) {
  return { iot_cards: '物联网卡台账', customers: '客户管理', assets: '型号管理', batches: '批次管理' }[res] || res
}
function poolOptions(field) {
  return pools.value[field] || []
}
function selOptions(field) {
  const cfg = selects.value[field]
  if (!cfg) return []
  if (Array.isArray(cfg)) return cfg.map((v) => ({ value: v, label: v }))
  return pools.value[field] || []
}

function newForm() {
  const f = {}
  formColumns.value.forEach(([key]) => (f[key] = ''))
  return f
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.list(props.resource, {
      keyword: keyword.value || undefined,
      customer: customerFilter.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    const { data } = await api.all(props.resource, { keyword: keyword.value || undefined })
    allRows.value = data.items
  } finally {
    statsLoading.value = false
  }
}

function refresh() {
  load()
  loadStats()
}

let debounceTimer = null
function debouncedSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    refresh()
  }, 350)
}

async function loadPools() {
  const froms = {}
  Object.entries(selects.value).forEach(([field, cfg]) => {
    if (cfg && !Array.isArray(cfg)) froms[field] = cfg
  })
  const byResource = {}
  for (const [field, cfg] of Object.entries(froms)) {
    byResource[cfg.from] = byResource[cfg.from] || { fields: [], value: cfg.value, linked: cfg.linked }
    byResource[cfg.from].fields.push(field)
  }
  for (const [res, info] of Object.entries(byResource)) {
    try {
      const { data } = await api.all(res)
      for (const field of info.fields) {
        pools.value[field] = data.items.map((row) => {
          const opt = {
            value: row[info.value],
            label: row[info.value],
            data: row,
          }
          if (res === 'iot_cards') opt.extra = `[${row.card_status || '未登记'}]`
          if (res === 'assets') opt.extra = `[${row.asset_type || ''}]`
          if (res === 'batches') opt.extra = `[${row.device_model || ''}]`
          if (res === 'iot_cards') opt.status = row.card_status
          return opt
        })
      }
    } catch {
      pools.value[field] = []
    }
  }
}

function onSelectChange(field, v) {
  const cfg = selects.value[field]
  if (!cfg || Array.isArray(cfg)) return
  if (cfg.linked) {
    const opt = (pools.value[field] || []).find((o) => o.value === v)
    const links = Array.isArray(cfg.linked) ? cfg.linked : [cfg.linked]
    links.forEach((l) => {
      form[l.target] = opt ? opt.data[l.source] || '' : ''
    })
  }
  if (cfg.from === 'iot_cards') {
    const opt = (pools.value[field] || []).find((o) => o.value === v)
    const statusKey = field === 'iccid1' ? 'card1_status' : 'card2_status'
    form[statusKey] = opt ? opt.status || '' : ''
  }
}

function ensurePoolValues() {
  Object.entries(selects.value).forEach(([field, cfg]) => {
    if (!cfg || Array.isArray(cfg)) return
    const v = form[field]
    if (v && !(pools.value[field] || []).some((o) => o.value === v)) {
      pools.value[field].unshift({ value: v, label: v, extra: '[原值]', data: {} })
    }
  })
}

function openDialog(row) {
  Object.keys(form).forEach((k) => delete form[k])
  Object.assign(form, newForm(), row || {})
  ensurePoolValues()
  dialogVisible.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {}
    formColumns.value.forEach(([key]) => {
      if (!readonlyCols.value.includes(key)) payload[key] = form[key] || null
    })
    if (form.id) {
      await api.update(props.resource, form.id, payload)
      ElMessage.success('记录已更新')
    } else {
      await api.create(props.resource, payload)
      ElMessage.success('记录已新增')
    }
    dialogVisible.value = false
    refresh()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteOne(row) {
  await ElMessageBox.confirm('确定删除这条记录？删除后不可恢复。', '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await api.remove(props.resource, row.id)
  ElMessage.success('已删除')
  refresh()
}

async function batchDelete() {
  await ElMessageBox.confirm(`确定删除选中的 ${selection.value.length} 条记录？删除后不可恢复。`, '批量删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  await api.removeMany(
    props.resource,
    selection.value.map((r) => r.id)
  )
  ElMessage.success('已删除')
  refresh()
}

function exportFile(format) {
  const url = api.exportUrl(props.resource, format, keyword.value)
  window.open(url, '_blank')
}

function downloadTemplate() {
  window.open(api.templateUrl(props.resource), '_blank')
}

async function doImport({ file }) {
  try {
    const { data } = await api.import(props.resource, file, true)
    ElMessage.success(`导入成功 ${data.imported} 条`)
    refresh()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  }
}

function openBatchImport(row) {
  importBatch.value = row
  importTarget.value = 'devices'
  importDialogVisible.value = true
}

async function doBatchImport({ file }) {
  batchImporting.value = true
  try {
    const { data } = await api.batchImport(importBatch.value.id, importTarget.value, file)
    ElMessage.success(`导入成功 ${data.imported} 条，PN=${data.batch_pn}`)
    importDialogVisible.value = false
    refresh()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    batchImporting.value = false
  }
}

onMounted(async () => {
  const { data } = await api.meta()
  columns.value = data[props.resource].columns
  selects.value = data[props.resource].selects || {}
  readonlyCols.value = data[props.resource].readonly || []
  readonlyHints.value = data[props.resource].readonly_hints || {}
  hiddenInTable.value = data[props.resource].hidden_in_table || []
  hiddenInForm.value = data[props.resource].hidden_in_form || []
  dateFields.value = data[props.resource].date_fields || []
  colorBy.value = data[props.resource].color_by || {}
  if (hasCustomerCol.value) await loadCustomerOptions()
  await loadPools()
  refresh()
})

onUnmounted(() => clearTimeout(debounceTimer))
</script>

<style scoped>
.lv {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ---------- 统计卡片 ---------- */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 16px;
}

.stat-card {
  background: var(--card);
  border-radius: var(--radius);
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--shadow);
  border: 1px solid rgba(226, 232, 240, 0.7);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  cursor: default;
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 22px;
  flex-shrink: 0;
}

.stat-value {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.5px;
  line-height: 1.1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 4px;
}

/* ---------- 面板 ---------- */
.panel {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  border: 1px solid rgba(226, 232, 240, 0.7);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  flex-wrap: wrap;
}

.search-box {
  width: 340px;
}

.spacer {
  flex: 1;
}

.ghost-btn {
  color: var(--text-2);
  border-color: var(--border);
}

.danger-btn {
  background: linear-gradient(135deg, #ef4444, #f97316);
  border: none;
}

.danger-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #dc2626, #ea580c);
  transform: translateY(-1px);
}

/* ---------- 表格 ---------- */
.table-panel {
  overflow: hidden;
  position: relative;
  min-height: 420px;
}

.table-panel :deep(.el-table) {
  --el-table-border-color: #eef2f7;
  --el-table-header-bg-color: #f8fafc;
  border-radius: var(--radius);
}

.table-panel :deep(.el-table__row:hover) {
  background: #f5f7ff !important;
}

.trow {
  transition: background 0.15s;
}

.mono {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12.5px;
  letter-spacing: 0.3px;
  color: #334155;
}

.empty-val {
  color: #cbd5e1;
}

/* ICCID 状态着色 */
.iccid-chip {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid transparent;
  white-space: nowrap;
  letter-spacing: 0.2px;
}

.chip-ok {
  color: #047857;
  background: rgba(16, 185, 129, 0.16);
  border-color: rgba(16, 185, 129, 0.3);
}

.chip-info {
  color: #475569;
  background: rgba(100, 116, 139, 0.14);
  border-color: rgba(100, 116, 139, 0.25);
}

.chip-warn {
  color: #b45309;
  background: rgba(245, 158, 11, 0.16);
  border-color: rgba(245, 158, 11, 0.3);
}

.chip-bad {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.14);
  border-color: rgba(239, 68, 68, 0.25);
}

/* 状态徽章 */
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-tag.ok {
  color: #047857;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.status-tag.info {
  color: #475569;
  background: rgba(100, 116, 139, 0.12);
  border: 1px solid rgba(100, 116, 139, 0.2);
}

.status-tag.idle {
  color: #0369a1;
  background: rgba(6, 182, 212, 0.12);
  border: 1px solid rgba(6, 182, 212, 0.25);
}

.status-tag.warn {
  color: #b45309;
  background: rgba(245, 158, 11, 0.14);
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.status-tag.bad {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

/* 空状态 */
.empty {
  padding: 40px 0;
}

/* 表格底部 */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-top: 1px solid #eef2f7;
}

.count-info {
  font-size: 13px;
  color: var(--text-2);
}

.count-info b {
  color: var(--primary);
  font-size: 15px;
}

/* 表单 */
.form-grid :deep(.el-form-item) {
  margin-bottom: 18px;
}

.opt-extra {
  float: right;
  color: var(--text-2);
  font-size: 12px;
  margin-left: 18px;
}

.ref-tag {
  font-size: 12px;
  color: var(--primary);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.12));
  padding: 0 10px;
  border-radius: 6px;
  white-space: nowrap;
}

.pn-tag {
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
}

.import-tip {
  font-size: 12px;
  color: var(--text-2);
  margin-top: 8px;
  line-height: 1.6;
}

@media (max-width: 1200px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>