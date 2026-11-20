import { expect, test } from '@playwright/test'

// 合并排程数据结果：补数高峰纳入排程、冲突两种处置、断点恢复不重复启动已完成文件。
test('合并排程：优先文件集、延后分区与断点恢复', async ({ page }) => {
  test.setTimeout(120_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) browserErrors.push(`${r.status()} ${r.url()}`) })

  // 先让 orders 的补数处于运行中，制造补数高峰
  await page.request.post('/api/backfill_stream/1/actions', { data: { action: '启动补数' } })

  await page.goto('/compact_policy')
  await expect(page.getByTestId('merge-schedule')).toBeVisible()

  await page.getByTestId('resolution').selectOption('优先合并')
  await page.getByTestId('plan-schedule').click()
  await expect(page.getByTestId('schedule-status')).not.toHaveText('未生成')

  const preferred = page.locator('[data-testid^="preferred-file-"]')
  const deferred = page.locator('[data-testid^="deferred-"]')
  expect(await preferred.count()).toBeGreaterThan(0)
  expect(await deferred.count()).toBeGreaterThan(0)

  // 执行合并 -> 已合并文件计数增加
  await page.getByTestId('schedule-执行合并').click()
  await expect(async () => {
    expect(Number(await page.getByTestId('completed-count').innerText())).toBeGreaterThan(0)
  }).toPass()

  // 中断 -> 恢复：已完成文件计数不回退，优先文件集也不重复包含它们
  const completedAfterExecute = await page.getByTestId('completed-count').innerText()
  await page.getByTestId('schedule-模拟中断').click()
  await expect(page.getByTestId('schedule-status')).toHaveText('已中断')
  await page.getByTestId('schedule-断点恢复').click()
  await expect(page.getByTestId('schedule-status')).not.toHaveText('已中断')
  expect(await page.getByTestId('completed-count').innerText()).toBe(completedAfterExecute)

  // 刷新页面后，排程结果与关联业务记录仍然读回
  await page.reload()
  await expect(page.getByTestId('merge-schedule')).toBeVisible()
  expect(await page.getByTestId('completed-count').innerText()).toBe(completedAfterExecute)
  await expect(page.locator('tbody tr[data-testid^="row-"]').first()).toBeVisible()

  // 流式补数页标记补数高峰分区
  await page.goto('/backfill_stream')
  await expect(page.getByTestId('peak-panel')).toBeVisible()
  expect(await page.locator('[data-testid^="peak-"]').count()).toBeGreaterThan(0)

  // 补偿：结束补数，避免影响其它用例
  await page.request.post('/api/backfill_stream/1/actions', { data: { action: '确认完成' } })
  expect(browserErrors).toEqual([])
})
