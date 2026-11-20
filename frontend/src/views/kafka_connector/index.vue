<template>
  <section class="page" data-module="kafka_connector">
    <header class="page-head">
      <div>
        <h2>消息接入管理</h2>
        <p class="page-desc">维护Kafka消费端的连接、偏移与反序列化配置，为消息接入提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记接入配置</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出消息接入清单</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无消息接入数据，可先登记接入配置</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记接入配置</h3>
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
      <span>共 {{ total }} 条消息接入记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { useCrudList } from '@/composables/useCrudList'

const ENDPOINT = '/api/kafka_connector'
const columns = ["配置编号", "集群地址", "消费组名", "偏移策略", "反序列化器", "批量大小", "超时时间", "死信队列"]
const actions = ["提交校验", "标记生效", "停用配置"]
const statuses = ["草稿", "待校验", "已生效", "已停用"]
const metricNames = ["接入配置总数", "待校验配置", "已生效配置"]


const {
  rows, total, errorMessage, filters, filterFields, showCreate, creating, createValues, stats,
  resetFilters, exportRows, openCreate, submitCreate, runAction, reload,
} = useCrudList({
  endpoint: ENDPOINT,
  columns,
  actions,
  statuses,
  metricNames,
  filename: 'kafka_connector.csv',
})
</script>
