const { chromium } = require('@playwright/test');

const pages = [
  ['dashboard', '/'],
  ['customers', '/customers'],
  ['customer-detail', '/customers/1'],
  ['appointments', '/appointments'],
  ['appointment-process', '/appointments/1/process'],
  ['appointment-convert', '/appointments/1/convert'],
  ['pt-groups', '/pt-groups'],
  ['commissions', '/commissions'],
  ['revenue', '/reports/revenue'],
  ['debts', '/reports/debts'],
  ['bank', '/reports/bank-transactions'],
  ['cash', '/reports/cash'],
  ['devices', '/devices'],
];

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:8100';

const viewports = [
  ['desktop', { width: 1440, height: 1000 }],
  ['netbook', { width: 1024, height: 768 }],
];

(async () => {
  const browser = await chromium.launch();
  const failures = [];

  for (const [viewportName, viewport] of viewports) {
    const page = await browser.newPage({ viewport });
    page.on('console', (message) => {
      if (message.text().includes('cdn.tailwindcss.com should not be used in production')) {
        return;
      }
      if (['error', 'warning'].includes(message.type())) {
        failures.push(`${viewportName}: console ${message.type()} ${message.text()}`);
      }
    });
    page.on('pageerror', (error) => failures.push(`${viewportName}: pageerror ${error.message}`));

    for (const [name, path] of pages) {
      const response = await page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });
      if (!response || response.status() >= 400) {
        failures.push(`${viewportName}/${name}: HTTP ${response && response.status()}`);
      }
      await page.screenshot({ path: `screenshots/${viewportName}-${name}.png`, fullPage: true });

      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        return {
          width: doc.scrollWidth,
          client: doc.clientWidth,
          overflow: doc.scrollWidth > doc.clientWidth + 2,
        };
      });
      if (overflow.overflow) {
        failures.push(`${viewportName}/${name}: horizontal overflow ${overflow.width} > ${overflow.client}`);
      }
    }

    await page.close();
  }

  await browser.close();

  if (failures.length) {
    console.error(failures.join('\n'));
    process.exit(1);
  }

  console.log('UI debug passed');
})();
