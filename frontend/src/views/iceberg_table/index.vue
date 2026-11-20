<template>
  <section class="page" data-module="iceberg_table">
    <header class="page-head">
      <div>
        <h2>Iceberg管理管理</h2>
        <p class="page-desc">维护Iceberg湖表的元数据、快照与文件清理策略，为Iceberg管理提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记表元数据</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出Iceberg管理清单</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无Iceberg管理数据，可先登记表元数据</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记表元数据</h3>
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
      <span>共 {{ total }} 条Iceberg管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { useCrudList } from '@/composables/useCrudList'

const ENDPOINT = '/api/iceberg_table'
const columns = ["表编号", "表名称", "存储格式", "分区策略", "排序字段", "快照过期", "孤立文件清理", "元数据版本"]
const actions = ["提交校验", "确认就绪", "标记下线"]
const statuses = ["草稿", "待校验", "已就绪", "已下线"]
const metricNames = ["表元数据总数", "待校验表", "已就绪表"]


const {
  rows, total, errorMessage, filters, filterFields, showCreate, creating, createValues, stats,
  resetFilters, exportRows, openCreate, submitCreate, runAction, reload,
} = useCrudList({
  endpoint: ENDPOINT,
  columns,
  actions,
  statuses,
  metricNames,
  filename: 'iceberg_table.csv',
})
</script>
