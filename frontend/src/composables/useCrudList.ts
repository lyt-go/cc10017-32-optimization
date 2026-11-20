/** 列表型模块的共用逻辑：筛选、导出、登记、动作与统计只保留这一份实现。
 *
 * 12 个 CRUD 页面原先各抄了一遍同样的请求与状态处理，这里统一收口；
 * 页面只需要声明接口地址、列与动作文案即可。
 */
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

export type Row = Record<string, string | number | null>

export type CrudListConfig = {
  endpoint: string
  columns: string[]
  actions: string[]
  statuses: string[]
  metricNames: string[]
  filename: string
  labels?: {
    exportError?: string
    createError?: string
    actionError?: string
    listError?: string
  }
}

export function useCrudList(config: CrudListConfig) {
  const { endpoint, columns, actions, statuses, metricNames, filename } = config
  const labels = config.labels ?? {}

  const rows = ref<Row[]>([])
  const total = ref(0)
  const errorMessage = ref('')
  const filters = ref<Record<string, string>>({})
  const filterFields = columns.slice(0, 3)
  const showCreate = ref(false)
  const creating = ref(false)
  const createValues = ref<Record<string, string>>({})
  const stats = computed(() => [
    { label: metricNames[0], value: total.value },
    { label: metricNames[1], value: rows.value.filter((row) => row.status === statuses[1]).length },
    { label: metricNames[2], value: rows.value.filter((row) => row.status === statuses[statuses.length - 1]).length },
  ])

  function resetFilters() {
    filters.value = {}
    void reload()
  }

  async function exportRows() {
    errorMessage.value = ''
    const query = new URLSearchParams(filters.value).toString()
    try {
      const response = await request(`${endpoint}/export?${query}`)
      if (!response.ok) throw new Error(labels.exportError ?? '导出失败，请稍后重试')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '导出失败'
    }
  }

  function openCreate() {
    createValues.value = Object.fromEntries(columns.map((field) => [field, '']))
    errorMessage.value = ''
    showCreate.value = true
  }

  async function submitCreate() {
    creating.value = true
    errorMessage.value = ''
    try {
      const response = await request(endpoint, {
        method: 'POST', body: JSON.stringify(createValues.value),
      })
      const payload = await response.json()
      if (!response.ok || !payload.ok) throw new Error(payload.message || labels.createError || '登记失败')
      showCreate.value = false
      await reload()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '登记失败'
    } finally {
      creating.value = false
    }
  }

  async function runAction(action: string, row: Row) {
    errorMessage.value = ''
    try {
      const response = await request(`${endpoint}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      if (!response.ok) throw new Error(labels.actionError ?? '动作未生效，请稍后重试')
      await reload()
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '操作失败'
    }
  }

  async function reload() {
    errorMessage.value = ''
    const query = new URLSearchParams(filters.value as Record<string, string>).toString()
    try {
      const response = await request(`${endpoint}?${query}`)
      if (!response.ok) throw new Error(labels.listError ?? '列表读取失败')
      const payload = await response.json()
      rows.value = payload.items ?? []
      total.value = payload.total ?? rows.value.length
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '列表读取失败'
    }
  }

  onMounted(reload)

  return {
    columns, actions, statuses,
    rows, total, errorMessage, filters, filterFields,
    showCreate, creating, createValues, stats,
    resetFilters, exportRows, openCreate, submitCreate, runAction, reload,
  }
}
