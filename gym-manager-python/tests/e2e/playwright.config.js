const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: __dirname,
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
});
