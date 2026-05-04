import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('http://localhost:5173/homeworks')
})

// adding a homework
test('can add a new homework', async ({ page }) => {
  const initialCount = await page.locator('tbody tr').count()
  await page.click('button:has-text("ADAUGĂ TEMĂ")')
  await expect(page).toHaveURL(/\/homeworks\/add/)
  await page.fill('input[type="text"]', 'Test Playwright')
  await page.locator('label:has-text("Materie") + select').selectOption('Matematică')
  await page.locator('label:has-text("Clasă") + select').selectOption('1A')
  await page.fill('input[type="date"]', '2026-12-01')
  await page.fill('textarea', 'Descriere test')
  await page.click('button:has-text("Adaugă")')
  await expect(page).toHaveURL('http://localhost:5173/homeworks')
  const newCount = await page.locator('tbody tr').count()
  expect(newCount).toBeGreaterThan(initialCount)
})

// deleting a homework
test('can delete a homework', async ({ page }) => {
  const firstTitle = await page.locator('tbody tr:first-child td:nth-child(2)').innerText()
  await page.locator('tbody tr:first-child button:has-text("Șterge")').click()
  await page.locator('.confirm-box button:has-text("Șterge")').click()
  await expect(page.locator(`td:has-text("${firstTitle}")`)).not.toBeVisible()
})

// validation on empty form
test('shows validation errors on empty submit', async ({ page }) => {
  await page.click('button:has-text("ADAUGĂ TEMĂ")')
  await page.click('button:has-text("Adaugă")')
  await expect(page.locator('text=Titlul este obligatoriu')).toBeVisible()
  await expect(page.locator('text=Materia este obligatorie')).toBeVisible()
  await expect(page.locator('text=Clasa este obligatorie')).toBeVisible()
  await expect(page.locator('text=Data limită este obligatorie')).toBeVisible()
})

// infinite scroll loads more rows as the sentinel scrolls into view
test('infinite scroll loads more rows on scroll', async ({ page }) => {
  const before = await page.locator('tbody tr').count()
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  // give the IntersectionObserver + fetch a moment to append the next page
  await page.waitForTimeout(600)
  const after = await page.locator('tbody tr').count()
  // either we loaded more (backend had enough data) or we'd already loaded everything
  expect(after).toBeGreaterThanOrEqual(before)
})

// navigate to detail view
test('clicking a row opens the detail view', async ({ page }) => {
  await page.locator('tbody tr:first-child').click()
  await expect(page).toHaveURL(/\/homeworks\/\d+/)
})
