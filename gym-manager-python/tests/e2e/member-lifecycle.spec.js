const { test, expect, request } = require("@playwright/test");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const BASE_URL = "http://127.0.0.1:18100";
const DB_PATH = path.resolve(".tmp", "member-lifecycle-e2e.sqlite3");
const ADMIN_PASSWORD = "E2ETestAdmin!2026";

let server;
let api;
let csrfToken;

async function waitForServer() {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/api/health/live`);
      if (response.ok) return;
    } catch {
      // keep polling
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Timed out waiting for e2e server");
}

async function apiContext() {
  const context = await request.newContext({
    baseURL: BASE_URL,
    extraHTTPHeaders: { Origin: BASE_URL },
  });
  const login = await context.post("/api/auth/login", {
    data: { username: "admin", password: ADMIN_PASSWORD },
  });
  expect(login.ok()).toBeTruthy();
  const state = await context.storageState();
  csrfToken = state.cookies.find((cookie) => cookie.name === "gym_csrf")?.value;
  expect(csrfToken).toBeTruthy();
  return context;
}

async function post(pathname, data) {
  const response = await api.post(pathname, {
    data,
    headers: { Origin: BASE_URL, "x-csrf-token": csrfToken },
  });
  return response;
}

async function postMultipart(pathname, multipart) {
  const response = await api.post(pathname, {
    multipart,
    headers: { Origin: BASE_URL, "x-csrf-token": csrfToken },
  });
  return response;
}

async function setToday(today) {
  const response = await post("/api/test-hooks/time", { today });
  expect(response.ok()).toBeTruthy();
}

async function createPlan(name) {
  const response = await post("/api/plans", {
    name,
    category: "Fitness",
    durationDays: 30,
    price: 100000,
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function createMember(name, phone) {
  const response = await post("/api/members", { name, phone });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function registerMembership(memberId, planId, overrides = {}) {
  const response = await postMultipart("/api/memberships", {
    memberId: String(memberId),
    planId: String(planId),
    startsAt: overrides.startsAt || "2026-08-01",
    activateNow: overrides.activateNow ?? "true",
    activationDate: overrides.activationDate || "",
    finalPrice: "100000",
    paidAmount: "0",
    paymentMethod: "cash",
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function memberState(code) {
  const response = await api.get(`/api/test-hooks/member-state?customerCode=${encodeURIComponent(code)}`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function waitForMember(code, predicate, label) {
  let last;
  await expect
    .poll(async () => {
      last = await memberState(code);
      return predicate(last);
    }, { timeout: 6000, intervals: [100, 150, 250, 500] })
    .toBe(true);
  return last;
}

async function expectError(response, text) {
  expect(response.status()).toBe(422);
  const body = await response.json();
  expect(body.detail).toContain(text);
}

test.beforeAll(async () => {
  fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  fs.rmSync(DB_PATH, { force: true });
  server = spawn("python", ["-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "18100"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      GYM_ENV: "test",
      GYM_DATABASE_PATH: DB_PATH,
      GYM_ADMIN_PASSWORD: ADMIN_PASSWORD,
      GYM_ALLOWED_HOSTS: "127.0.0.1,localhost",
      GYM_ALLOWED_ORIGINS: BASE_URL,
      GYM_TEST_JOB_INTERVAL_SECONDS: "0.2",
      GYM_LOGIN_RATE_LIMIT: "1000",
      GYM_API_RATE_LIMIT: "10000",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  server.stdout.on("data", (chunk) => process.stdout.write(`[e2e-server] ${chunk}`));
  server.stderr.on("data", (chunk) => process.stderr.write(`[e2e-server] ${chunk}`));
  await waitForServer();
  api = await apiContext();
  await setToday("2026-08-01");
});

test.afterAll(async () => {
  await api?.dispose();
  if (server) {
    server.kill();
    await new Promise((resolve) => server.once("exit", resolve));
  }
});

test("member without a regular membership stays lead and is only eligible as a lead check-in", async () => {
  await setToday("2026-08-01");
  const member = await createMember("E2E No Package", "0901000001");
  const state = await memberState(member.code);

  expect(state.status).toBe("lead");
  expect(state.memberships).toHaveLength(0);

  const candidates = await api.get(`/api/checkins/candidates?q=${member.phone}`);
  expect(candidates.ok()).toBeTruthy();
  const candidate = (await candidates.json())[0];
  expect(candidate.eligible).toBe(true);
  expect(candidate.membership).toBeNull();

  const checkin = await post("/api/checkins", { memberId: member.id });
  expect(checkin.ok()).toBeTruthy();
  const afterCheckin = await memberState(member.code);
  expect(afterCheckin.status).toBe("lead");
  expect(afterCheckin.memberships).toHaveLength(0);
});

test("pending membership without scheduled date activates manually from the actual activation day", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Manual Activation");
  const member = await createMember("E2E Pending Manual", "0901000002");
  const membership = await registerMembership(member.id, plan.id, { activateNow: "false" });

  expect(membership.status).toBe("pending");
  let state = await memberState(member.code);
  expect(state.status).toBe("lead");

  await setToday("2026-08-09");
  const activate = await post(`/api/memberships/${membership.id}/actions`, {
    action: "activate",
    activatedAt: "2026-08-09",
    reason: "E2E kích hoạt ngẫu nhiên",
  });
  expect(activate.ok()).toBeTruthy();

  state = await memberState(member.code);
  expect(state.status).toBe("active");
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-09",
    activatedAt: "2026-08-09",
    expiresAt: "2026-09-08",
  });
});

test("pending membership with scheduled activation is activated by the background job", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Scheduled Activation");
  const member = await createMember("E2E Pending Scheduled", "0901000003");
  await registerMembership(member.id, plan.id, {
    activateNow: "false",
    activationDate: "2026-08-10",
  });

  await setToday("2026-08-09");
  await new Promise((resolve) => setTimeout(resolve, 500));
  let state = await memberState(member.code);
  expect(state.status).toBe("lead");
  expect(state.memberships[0].status).toBe("pending");

  await setToday("2026-08-10");
  state = await waitForMember(
    member.code,
    (row) => row.status === "active" && row.memberships[0].status === "active",
    "scheduled activation",
  );
  expect(state.memberships[0]).toMatchObject({
    startsAt: "2026-08-10",
    activatedAt: "2026-08-10",
    expiresAt: "2026-09-09",
  });
});

test("scheduled pending membership activates on early first check-in with a full term", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Early Checkin Activation");
  const member = await createMember("E2E Pending Early Checkin", "0901000004");
  await registerMembership(member.id, plan.id, {
    activateNow: "false",
    activationDate: "2026-08-20",
  });

  await setToday("2026-08-05");
  const checkin = await post("/api/checkins", { memberId: member.id });
  expect(checkin.ok()).toBeTruthy();

  const state = await memberState(member.code);
  expect(state.status).toBe("active");
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-05",
    activatedAt: "2026-08-05",
    expiresAt: "2026-09-04",
  });
});

test("active membership starts with a full term and expires by the background job after expiry", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Active Expiry");
  const member = await createMember("E2E Active Member", "0901000005");
  await registerMembership(member.id, plan.id, { activateNow: "true" });

  let state = await memberState(member.code);
  expect(state.status).toBe("active");
  expect(state.memberships[0]).toMatchObject({
    startsAt: "2026-08-01",
    activatedAt: "2026-08-01",
    expiresAt: "2026-08-31",
  });

  await setToday("2026-08-31");
  await new Promise((resolve) => setTimeout(resolve, 500));
  state = await memberState(member.code);
  expect(state.status).toBe("active");
  expect(state.memberships[0].status).toBe("active");

  await setToday("2026-09-01");
  state = await waitForMember(
    member.code,
    (row) => row.status === "inactive" && row.memberships[0].status === "expired",
    "expiry job",
  );
  expect(state.memberships[0].expiresAt).toBe("2026-08-31");
});

test("freeze validates dates and compensates only actual frozen days", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Freeze");

  const invalid = await createMember("E2E Freeze Invalid", "0901000006");
  const invalidMembership = await registerMembership(invalid.id, plan.id, { activateNow: "true" });
  await setToday("2026-08-10");
  await expectError(
    await post(`/api/memberships/${invalidMembership.id}/freeze`, {
      startsAt: "2026-08-09",
      endsAt: "2026-08-12",
      reason: "Ngày quá khứ",
    }),
    "quá khứ",
  );
  await expectError(
    await post(`/api/memberships/${invalidMembership.id}/freeze`, {
      startsAt: "2026-08-10",
      endsAt: "2026-08-10",
      reason: "Ngày bằng nhau",
    }),
    "sau ngày bắt đầu",
  );

  const sameDay = await createMember("E2E Freeze Same Day", "0901000007");
  const sameDayMembership = await registerMembership(sameDay.id, plan.id, { startsAt: "2026-08-01", activateNow: "true" });
  let response = await post(`/api/memberships/${sameDayMembership.id}/freeze`, {
    startsAt: "2026-08-10",
    endsAt: "2026-08-20",
    reason: "Bảo lưu cùng ngày",
  });
  expect(response.ok()).toBeTruthy();
  response = await post(`/api/memberships/${sameDayMembership.id}/actions`, {
    action: "activate",
    activatedAt: "2026-08-10",
    reason: "Kích hoạt lại trong ngày",
  });
  expect(response.ok()).toBeTruthy();
  let state = await memberState(sameDay.code);
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-01",
    activatedAt: "2026-08-01",
    expiresAt: "2026-08-31",
  });
  expect(state.memberships[0].freezes[0]).toMatchObject({ endsAt: "2026-08-10", compensatedDays: 0 });

  const early = await createMember("E2E Freeze Early Return", "0901000008");
  const earlyMembership = await registerMembership(early.id, plan.id, { startsAt: "2026-08-01", activateNow: "true" });
  response = await post(`/api/memberships/${earlyMembership.id}/freeze`, {
    startsAt: "2026-08-10",
    endsAt: "2026-08-20",
    reason: "Bảo lưu",
  });
  expect(response.ok()).toBeTruthy();
  await setToday("2026-08-15");
  response = await post(`/api/memberships/${earlyMembership.id}/actions`, {
    action: "activate",
    activatedAt: "2026-08-15",
    reason: "Kích hoạt trước hạn",
  });
  expect(response.ok()).toBeTruthy();
  state = await memberState(early.code);
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-01",
    activatedAt: "2026-08-01",
    expiresAt: "2026-09-05",
  });
  expect(state.memberships[0].freezes[0]).toMatchObject({ endsAt: "2026-08-15", compensatedDays: 5 });

  const auto = await createMember("E2E Freeze Auto End", "0901000009");
  const autoMembership = await registerMembership(auto.id, plan.id, { startsAt: "2026-08-01", activateNow: "true" });
  await setToday("2026-08-10");
  response = await post(`/api/memberships/${autoMembership.id}/freeze`, {
    startsAt: "2026-08-10",
    endsAt: "2026-08-20",
    reason: "Bảo lưu tự hết",
  });
  expect(response.ok()).toBeTruthy();
  await setToday("2026-08-21");
  state = await waitForMember(
    auto.code,
    (row) => row.status === "active" && row.memberships[0].freezes[0]?.compensatedDays === 10,
    "freeze auto completion",
  );
  expect(state.memberships[0]).toMatchObject({
    startsAt: "2026-08-01",
    activatedAt: "2026-08-01",
    expiresAt: "2026-09-10",
  });
});

test("suspend validates dates and reactivation recalculates from the reactivation day", async () => {
  await setToday("2026-08-01");
  const plan = await createPlan("E2E Suspend");

  const invalid = await createMember("E2E Suspend Invalid", "0901000010");
  const invalidMembership = await registerMembership(invalid.id, plan.id, { activateNow: "true" });
  await setToday("2026-08-10");
  await expectError(
    await post(`/api/memberships/${invalidMembership.id}/actions`, {
      action: "suspend",
      suspendedAt: "2026-08-09",
      reason: "Ngày quá khứ",
    }),
    "quá khứ",
  );

  const sameDay = await createMember("E2E Suspend Same Day", "0901000011");
  const sameDayMembership = await registerMembership(sameDay.id, plan.id, { startsAt: "2026-08-01", activateNow: "true" });
  let response = await post(`/api/memberships/${sameDayMembership.id}/actions`, {
    action: "suspend",
    suspendedAt: "2026-08-10",
    reason: "Tạm dừng",
  });
  expect(response.ok()).toBeTruthy();
  response = await post(`/api/memberships/${sameDayMembership.id}/actions`, {
    action: "activate",
    activatedAt: "2026-08-10",
    reason: "Kích hoạt lại trong ngày",
  });
  expect(response.ok()).toBeTruthy();
  let state = await memberState(sameDay.code);
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-10",
    activatedAt: "2026-08-10",
    expiresAt: "2026-08-31",
  });

  const later = await createMember("E2E Suspend Later", "0901000012");
  const laterMembership = await registerMembership(later.id, plan.id, { startsAt: "2026-08-01", activateNow: "true" });
  response = await post(`/api/memberships/${laterMembership.id}/actions`, {
    action: "suspend",
    suspendedAt: "2026-08-10",
    reason: "Tạm dừng",
  });
  expect(response.ok()).toBeTruthy();
  await setToday("2026-08-15");
  response = await post(`/api/memberships/${laterMembership.id}/actions`, {
    action: "activate",
    activatedAt: "2026-08-15",
    reason: "Kích hoạt lại",
  });
  expect(response.ok()).toBeTruthy();
  state = await memberState(later.code);
  expect(state.memberships[0]).toMatchObject({
    status: "active",
    startsAt: "2026-08-15",
    activatedAt: "2026-08-15",
    expiresAt: "2026-09-05",
  });
});
