<template>
  <section class="page" data-module="compact_policy">
    <header class="page-head">
      <div>
        <h2>合并清理管理</h2>
        <p class="page-desc">维护湖表小文件合并、过期快照清理与元数据优化策略，为合并清理提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记清理策略</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出合并清理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button
              class="link"
              type="button"
              :data-testid="`plan-${row.id}`"
              @click="planSchedule(row)"
            >
              生成排程
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无合并清理数据，可先登记清理策略</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记清理策略</h3>
        <label v-for="field in columns" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <section class="schedule-panel" data-testid="merge-schedule">
      <header class="schedule-head">
        <div>
          <h3>合并排程数据结果</h3>
          <p class="page-desc">补数高峰纳入排程：优先文件集与延后分区会一起保存，刷新页面后仍是同一份。</p>
        </div>
        <div class="page-actions">
          <label class="filter-item">
            <span>冲突处置</span>
            <select v-model="resolution" data-testid="resolution">
              <option v-for="item in resolutions" :key="item" :value="item">{{ item }}</option>
            </select>
          </label>
          <button class="btn primary" type="button" data-testid="plan-schedule" @click="planSchedule()">生成合并排程</button>
        </div>
      </header>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">优先文件集</span>
          <strong class="stat-value" data-testid="preferred-count">{{ preferredFiles.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">延后分区</span>
          <strong class="stat-value" data-testid="deferred-count">{{ deferredPartitions.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">已合并文件（不重复启动）</span>
          <strong class="stat-value" data-testid="completed-count">{{ completedFiles.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">排程状态</span>
          <strong class="stat-value" data-testid="schedule-status">{{ schedule?.status ?? '未生成' }}</strong>
        </article>
      </div>

      <p v-if="schedule" class="schedule-meta">
        目标表 {{ schedule.target_table }} · 执行窗口 {{ schedule.execution_window }} ·
        {{ schedule.resolution }} · 来源版本 {{ schedule.source_version }} · 批次 {{ schedule.batch_no }}
        <span v-if="schedule.conflict_detail">· 补数高峰冲突：{{ (schedule.conflict_detail.overlap_partitions ?? []).join('、') }}</span>
      </p>

      <div class="schedule-grid">
        <div class="schedule-col">
          <h4>优先文件集</h4>
          <table class="data-table">
            <thead><tr><th>文件</th><th>分区</th><th>大小(MB)</th><th>来源版本</th></tr></thead>
            <tbody>
              <tr v-for="file in preferredFiles" :key="file.file" :data-testid="`preferred-file-${file.file}`">
                <td>{{ file.file }}</td><td>{{ file.partition }}</td><td>{{ file.size_mb }}</td><td>{{ file.source_version }}</td>
              </tr>
              <tr v-if="!preferredFiles.length"><td colspan="4" class="empty-state">当前批次没有可执行的合并文件</td></tr>
            </tbody>
          </table>
        </div>
        <div class="schedule-col">
          <h4>延后分区</h4>
          <table class="data-table">
            <thead><tr><th>分区</th><th>状态</th><th>文件数</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="item in deferredPartitions" :key="item.partition" :data-testid="`deferred-${item.partition}`">
                <td>{{ item.partition }}</td><td>{{ item.state }}</td><td>{{ item.file_count }}</td><td>{{ item.reason }}</td>
              </tr>
              <tr v-if="!deferredPartitions.length"><td colspan="4" class="empty-state">没有延后分区</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="schedule" class="page-actions schedule-actions">
        <button
          v-for="action in scheduleActions"
          :key="action"
          class="btn"
          type="button"
          :data-testid="`schedule-${action}`"
          @click="runScheduleAction(action)"
        >
          {{ action }}
        </button>
      </div>

      <ol v-if="events.length" class="schedule-events" data-testid="schedule-events">
        <li v-for="event in events" :key="`${event.at}-${event.event}`">
          {{ event.at }} · {{ event.event }} · {{ event.detail }}
        </li>
      </ol>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条合并清理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { request } from '@/api/client'
import { useCrudList, type Row } from '@/composables/useCrudList'

const ENDPOINT = '/api/compact_policy'
const columns = ["策略编号", "目标表名", "触发条件", "合并并发", "目标文件大小", "最小文件数", "保留快照数", "执行时间窗口"]
const actions = ["提交校验", "标记生效", "停用策略"]
const statuses = ["草稿", "待校验", "已生效", "已停用"]
const metricNames = ["清理策略总数", "待校验策略", "已生效策略"]

const resolutions = ['优先补数', '优先合并']
const scheduleActions = ['执行合并', '模拟中断', '断点恢复']
const resolution = ref(resolutions[0])
const schedule = ref<any>(null)

const {
  rows, total, errorMessage, filters, filterFields, showCreate, creating, createValues, stats,
  resetFilters, exportRows, openCreate, submitCreate, runAction, reload: reloadRows,
} = useCrudList({
  endpoint: ENDPOINT,
  columns,
  actions,
  statuses,
  metricNames,
  filename: 'compact_policy.csv',
  labels: {
    exportError: '导出失败，请稍后重试',
    actionError: '合并清理动作未生效，请稍后重试',
    createError: '登记失败',
    listError: '清理策略列表读取失败',
  },
})

const preferredFiles = computed<any[]>(() => schedule.value?.preferred_file_set ?? [])
const deferredPartitions = computed<any[]>(() => schedule.value?.deferred_partitions ?? [])
const completedFiles = computed<string[]>(() => schedule.value?.completed_file_set ?? [])
const events = computed<any[]>(() => [...(schedule.value?.events ?? [])].reverse())

// 排程结果是后端持久化产物：刷新页面直接读回，不在前端重算。
async function loadSchedule() {
  const response = await request(`${ENDPOINT}/schedules`)
  if (!response.ok) throw new Error('合并排程读取失败')
  const payload = await response.json()
  const visibleTables = new Set(rows.value.map((row) => String(row['目标表名'] ?? '')))
  const items = (payload.items ?? []).filter((item: any) => visibleTables.has(item.target_table))
  const pool = items.length ? items : payload.items ?? []
  const latest = pool[pool.length - 1] ?? null
  schedule.value = latest
  if (latest?.resolution) resolution.value = latest.resolution
}

async function reload() {
  await reloadRows()
  await loadSchedule()
}

async function applyScheduleResponse(response: Response, fallback: string) {
  const payload = await response.json()
  if (!response.ok || !payload.ok) throw new Error(payload.message || fallback)
  await reload()
}

async function planSchedule(row?: Row) {
  const policy = row ?? rows.value.find((item) => item.status === '已生效') ?? rows.value[0]
  if (!policy) {
    errorMessage.value = '没有可生成排程的清理策略'
    return
  }
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${policy.id}/schedule`, {
      method: 'POST', body: JSON.stringify({ resolution: resolution.value }),
    })
    await applyScheduleResponse(response, '合并排程生成失败')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '合并排程生成失败'
  }
}

async function runScheduleAction(action: string) {
  if (!schedule.value) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/schedules/${schedule.value.id}/actions`, {
      method: 'POST', body: JSON.stringify({ action }),
    })
    await applyScheduleResponse(response, '合并排程动作未生效')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '合并排程操作失败'
  }
}

void reload()
</script>
