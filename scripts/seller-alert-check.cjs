const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const base = "http://127.0.0.1:8001";
  const ctx = await browser.newContext();
  await ctx.addCookies([
    {
      name: "sessionid",
      value: JSON.parse(fs.readFileSync(".local/browser-session.json"))
        .sessionid,
      url: base,
    },
  ]);
  const owner = await ctx.newPage();
  await owner.goto(base + "/cafes");
  await owner
    .getByRole("button", { name: "메뉴 보기 · 카페 선택 →" })
    .waitFor();
  const cafe = (await owner.evaluate(() => api("/api/cafes"))).cafes[0];
  const participant = await browser.newContext();
  const pp = await participant.newPage();
  const ids = [];
  for (let n = 0; n < 2; n++) {
    const { id } = await owner.evaluate(
      (cid) => api("/api/orders", { cafe: cid }),
      cafe.id,
    );
    const o = (await owner.evaluate((id) => api("/api/orders/" + id), id))
      .order;
    await pp.goto(base + o.join_url);
    await pp.locator("[data-add]").first().waitFor();
    const m = cafe.menus[0],
      groups = [
        ...new Set(m.options.filter((x) => x.group).map((x) => x.group)),
      ],
      options = groups.map((g) => m.options.find((x) => x.group === g).id);
    await pp.evaluate((d) => api("/api/join/" + joinToken, d), {
      name: "다중 알림 시험 " + (n + 1),
      items: [{ menu: m.id, options, quantity: 1 }],
    });
    for (const action of ["close", "send"])
      await owner.evaluate(
        async ({ id, action }) => {
          const o = (await api("/api/orders/" + id)).order;
          return api("/api/orders/" + id, { action, version: o.version });
        },
        { id, action },
      );
    ids.push(id);
  }
  const seller = await browser.newContext();
  const sp = await seller.newPage();
  const creds = JSON.parse(fs.readFileSync(".local/demo-accounts.json")).seller;
  await sp.goto(base + "/seller/login");
  await sp.getByLabel("계정명").fill(creds.username);
  await sp.getByLabel("비밀번호").fill(creds.password);
  await sp.getByRole("button", { name: "로그인", exact: true }).click();
  await sp.waitForURL("**/seller/orders");
  await sp.getByRole("button", { name: "알림 소리 켜기 · 시험 재생" }).click();
  await sp.locator(`#pending-alert a[href="/seller/orders/${ids[0]}"]`).click();
  await sp.getByPlaceholder("준비 시간(분)").fill("1");
  await sp.getByRole("button", { name: "수락", exact: true }).click();
  await sp.getByRole("button", { name: "준비 완료", exact: true }).waitFor();
  await sp
    .locator(`#pending-alert a[href="/seller/orders/${ids[1]}"]`)
    .waitFor();
  if (!(await sp.locator("#sound-status").innerText()).includes("소리 켜짐"))
    throw Error("Sound activation lost while selecting orders");
  await sp.locator(`#pending-alert a[href="/seller/orders/${ids[1]}"]`).click();
  await sp
    .getByPlaceholder("거절 사유 10~50자")
    .fill("시험 주문으로 접수를 거절합니다");
  await sp.getByRole("button", { name: "거절", exact: true }).click();
  await sp.locator(".badge").filter({ hasText: "판매자 거절" }).waitFor();
  await sp.waitForFunction(
    () => document.querySelector("#pending-alert").textContent.trim() === "",
  );
  await sp.getByRole("button", { name: "← 주문 목록" }).click();
  await sp.getByRole("link").filter({ hasText: "준비 중" }).first().click();
  await sp.getByRole("button", { name: "준비 완료", exact: true }).click();
  await sp.locator(".badge").filter({ hasText: "준비 완료" }).waitFor();
  await sp.getByRole("button", { name: "내정보", exact: true }).click();
  await sp
    .locator("#profile-modal")
    .getByRole("button", { name: "로그아웃", exact: true })
    .click();
  await sp.goto(base + "/seller/login");
  await sp.getByLabel("계정명").fill(creds.username);
  await sp.getByLabel("비밀번호").fill(creds.password);
  await sp.getByRole("button", { name: "로그인", exact: true }).click();
  await sp.waitForURL("**/seller/orders");
  await sp
    .locator(".badge")
    .filter({ hasText: "판매자 거절" })
    .first()
    .waitFor();
  console.log(
    JSON.stringify({
      twoPendingOrders: true,
      firstHandledSecondStillNotified: true,
      soundActivationPreserved: true,
      rejectionEndsAlert: true,
      logoutReloginHistory: true,
      actualSpeakerDevice: "not tested",
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
