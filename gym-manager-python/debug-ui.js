const { chromium } = require('@playwright/test');

const pages = [
  ['dashboard', '/dashboard'],
  ['members', '/members'],
  ['member-detail', '/members/1'],
  ['memberships', '/memberships'],
  ['plans', '/plans'],
  ['trainers', '/trainers'],
  ['training', '/training'],
  ['checkin', '/check-in'],
  ['payments', '/payments'],
  ['reports', '/reports'],
  ['settings', '/settings'],
];

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:8100';
const viewports = [
  ['desktop', { width: 1440, height: 1000 }],
  ['laptop', { width: 1280, height: 800 }],
  ['netbook', { width: 1024, height: 768 }],
  ['tablet', { width: 768, height: 900 }],
  ['mobile', { width: 390, height: 844 }],
];

(async () => {
  const browser = await chromium.launch();
  const failures = [];
  for (const [viewportName, viewport] of viewports) {
    const page = await browser.newPage({ viewport });
    page.on('pageerror', (error) => failures.push(`${viewportName}: pageerror ${error.message}`));
    page.on('console', (message) => { if (message.type() === 'error' && !message.text().includes('401 (Unauthorized)')) failures.push(`${viewportName}: console ${message.text()}`); });
    await page.goto(`${baseUrl}/dashboard`, { waitUntil: 'networkidle' });
    if (await page.locator('input[autocomplete="username"]').count()) {
      await Promise.all([
        page.waitForResponse((response) => response.url().includes('/api/auth/login') && response.status() === 200),
        page.locator('button[type="submit"]').click(),
      ]);
      await page.locator('nav').waitFor();
    }
    for (const [name, path] of pages) {
      const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
      if (!response || response.status() >= 400) failures.push(`${viewportName}/${name}: HTTP ${response && response.status()}`);
      await page.screenshot({ path: `screenshots/v2-${viewportName}-${name}.png`, fullPage: true });
      const overflow = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
      if (overflow.width > overflow.client + 2) failures.push(`${viewportName}/${name}: overflow ${overflow.width} > ${overflow.client}`);
      if (viewport.width >= 900) {
        const sidebar = await page.locator('.sidebar').boundingBox();
        if (!sidebar || sidebar.x < 0 || sidebar.width < 240) failures.push(`${viewportName}/${name}: desktop sidebar not visible`);
        const scrollbarWidth = await page.locator('.sidebar nav').evaluate((nav) => getComputedStyle(nav).scrollbarWidth);
        if (scrollbarWidth !== 'none') failures.push(`${viewportName}/${name}: sidebar scrollbar is visible`);
      }
    }
    await page.close();
  }
  const workflow = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await workflow.goto(`${baseUrl}/members?view=debt&status=active&sort=name`, { waitUntil: 'networkidle' });
  if (await workflow.locator('input[autocomplete="username"]').count()) {
    await workflow.locator('button[type="submit"]').click();
    await workflow.locator('nav').waitFor();
    await workflow.goto(`${baseUrl}/members?view=debt&status=active&sort=name`, { waitUntil: 'networkidle' });
  }
  const listSearch = workflow.locator('.members-search input');
  await listSearch.fill('Tuấn');
  await workflow.waitForResponse((response) => response.url().includes('/api/members?') && response.status() === 200);
  await workflow.locator('.data-table tbody .member-cell').first().click();
  await workflow.locator('.drawer').waitFor();
  const drawerBox = await workflow.locator('.drawer').boundingBox();
  if (!drawerBox || drawerBox.width < 480 || drawerBox.width > 600 || drawerBox.x < 800) failures.push(`workflow: desktop drawer width/position is invalid (${drawerBox && drawerBox.width})`);
  const openedUrl = new URL(workflow.url());
  if (openedUrl.searchParams.get('q') !== 'Tuấn' || openedUrl.searchParams.get('status') !== 'active' || !openedUrl.searchParams.get('member')) failures.push('workflow: member drawer did not preserve list context');
  await workflow.locator('.drawer-header .icon-button').click();
  await workflow.locator('.drawer').waitFor({ state: 'detached' });
  const closedUrl = new URL(workflow.url());
  if (closedUrl.searchParams.get('q') !== 'Tuấn' || closedUrl.searchParams.has('member')) failures.push('workflow: closing drawer changed list context');
  await listSearch.fill('');
  await workflow.waitForFunction(() => document.querySelectorAll('.data-table tbody tr').length > 1);
  await workflow.locator('.data-table tbody input[type="checkbox"]').first().check();
  if (!await workflow.locator('.bulk-bar').isVisible()) failures.push('workflow: bulk action bar did not appear');
  await workflow.keyboard.press('Control+K');
  await workflow.locator('.command-input input').fill('Tuấn');
  await workflow.locator('.command-results > button').first().waitFor();
  await workflow.locator('.command-input input').press('Enter');
  await workflow.locator('.drawer').waitFor();
  if (!workflow.url().includes('/members?member=')) failures.push('workflow: global search did not open quick detail');
  await workflow.locator('.drawer-header .icon-button').click();
  await workflow.goto(`${baseUrl}/payments`, { waitUntil: 'networkidle' });
  const paymentMember = workflow.locator('.data-table tbody a[href^="/members/"]').first();
  if (await paymentMember.count()) {
    await paymentMember.click();
    await workflow.locator('.drawer').waitFor();
    if (new URL(workflow.url()).pathname !== '/payments') failures.push('workflow: cross-module member preview lost payment context');
  }
  await workflow.close();
  await browser.close();
  if (failures.length) { console.error(failures.join('\n')); process.exit(1); }
  console.log('UI debug passed across 1440, 1280, 1024, 768 and mobile.');
})();
