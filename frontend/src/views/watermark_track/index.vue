<template>
  <section class="page" data-module="watermark_track">
    <header class="page-head">
      <div>
        <h2>水位追踪管理</h2>
        <p class="page-desc">维护流处理事件时间与处理时间的双水位追踪，为水位追踪提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记水位标记</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出水位追踪清单</button>
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
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无水位追踪数据，可先登记水位标记</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记水位标记</h3>
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

    <footer class="page-foot">
      <span>共 {{ total }} 条水位追踪记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { useCrudList } from '@/composables/useCrudList'

const ENDPOINT = '/api/watermark_track'
const columns = ["标记编号", "数据主题", "分区编号", "事件时间水位", "处理时间水位", "延迟记录数", "消费偏移", "检查时间"]
const actions = ["标记正常", "标记滞后", "停用追踪"]
const statuses = ["草稿", "正常", "滞后", "已停用"]
const metricNames = ["水位标记总数", "正常水位", "滞后水位"]


const {
  rows, total, errorMessage, filters, filterFields, showCreate, creating, createValues, stats,
  resetFilters, exportRows, openCreate, submitCreate, runAction, reload,
} = useCrudList({
  endpoint: ENDPOINT,
  columns,
  actions,
  statuses,
  metricNames,
  filename: 'watermark_track.csv',
})
</script>
