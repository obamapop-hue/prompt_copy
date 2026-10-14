const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const errors = [];
  const base = "http://127.0.0.1:8001";
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const home = await desktop.newPage();
  home.on("pageerror", (e) => errors.push(e.message));
  await home.goto(base);
  await home.getByRole("button", { name: "로그인", exact: true }).waitFor();
  await home
    .getByRole("heading", { name: "먹고 싶은거 다 골라!", exact: true })
    .waitFor();
  const mainActions = await home
    .locator("main")
    .locator("a,button")
    .allTextContents();
  if (JSON.stringify(mainActions) !== JSON.stringify(["주문하기"]))
    throw Error("Only order action belongs in the homepage body");
  if (
    await home.getByRole("link", { name: "내 주문 내역", exact: true }).count()
  )
    throw Error("Order history exposed before login");
  const loginBounds = await home
    .getByRole("button", { name: "로그인", exact: true })
    .boundingBox();
  if (loginBounds.y > 100 || loginBounds.x < 1000)
    throw Error("Login is not in the upper-right header");
  await home.getByRole("button", { name: "로그인", exact: true }).click();
  await home
    .locator("#login-modal")
    .getByRole("button", { name: "카카오톡 로그인", exact: true })
    .waitFor();
  await home.keyboard.press("Escape");
  await home.locator("#login-modal").waitFor({ state: "hidden" });
  await home.screenshot({ path: ".local/home-desktop.png", fullPage: true });
  const organizer = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  await organizer.addCookies([
    {
      name: "sessionid",
      value: JSON.parse(fs.readFileSync(".local/browser-session.json"))
        .sessionid,
      url: base,
    },
  ]);
  const op = await organizer.newPage();
  op.on("pageerror", (e) => errors.push(e.message));
  await op.goto(base);
  await op.getByRole("button", { name: "내정보", exact: true }).waitFor();
  if (await op.getByRole("button", { name: "로그인", exact: true }).count())
    throw Error("Login should be replaced by account info");
  await op.getByRole("button", { name: "내정보", exact: true }).click();
  await op
    .locator("#profile-modal")
    .getByText("시연총무", { exact: true })
    .waitFor();
  await op
    .locator("#profile-modal")
    .getByText("연결된 계정 없음", { exact: true })
    .waitFor();
  await op
    .locator("#profile-modal")
    .getByRole("link", { name: "내 주문 내역", exact: true })
    .waitFor();
  await op.screenshot({
    path: ".local/youngcha-profile-mobile.png",
    fullPage: true,
  });
  await op.keyboard.press("Escape");
  await op.screenshot({
    path: ".local/youngcha-home-mobile.png",
    fullPage: true,
  });
  await op.goto(base + "/cafes");
  await op.getByRole("button", { name: "메뉴 보기 · 카페 선택 →" }).click();
  await op.getByRole("button", { name: "이 카페로 주문방 만들기" }).click();
  await op.waitForURL("**/my/orders/*");
  await op.getByRole("button", { name: "참여 링크 복사" }).waitFor();
  const joinUrl = await op.locator("input[readonly]").inputValue();
  const participant = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const pp = await participant.newPage();
  pp.on("pageerror", (e) => errors.push(e.message));
  await pp.goto(joinUrl);
  await pp
    .locator("article")
    .first()
    .getByLabel("ICE", { exact: true })
    .check();
  await pp.locator("article").first().getByLabel("샷 추가 +500원").check();
  await pp
    .locator("article")
    .first()
    .getByRole("button", { name: "담기 +" })
    .click();
  await pp.getByLabel("총무가 알아볼 수 있는 이름").fill("브라우저시험");
  let lost = false;
  await pp.route("**/api/join/*", async (route) => {
    if (route.request().method() === "POST" && !lost) {
      lost = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await pp.getByRole("button", { name: "선택 내역 제출" }).click();
  await pp.locator("#error").filter({ hasText: "Failed" }).waitFor();
  await pp.reload();
  await pp.getByRole("button", { name: "이전 요청 결과 확인·재시도" }).click();
  await pp.getByText("브라우저시험님, 잘 담아뒀어요!").waitFor();
  await pp.reload();
  await pp.getByText("브라우저시험님, 잘 담아뒀어요!").waitFor();
  await op.getByText("브라우저시험 · 아메리카노", { exact: true }).waitFor();
  await op.locator('[id^="edit-"]').fill("2");
  await op.getByRole("button", { name: "적용", exact: true }).click();
  await op
    .getByText("총무 수량 변경", { exact: false })
    .waitFor({ state: "attached" });
  op.on("dialog", (d) => d.accept());
  await op.getByRole("button", { name: "모집 마감하기" }).click();
  await op.getByRole("button", { name: "최종 주문서 전송" }).click();
  await op.getByText("접수 대기", { exact: true }).waitFor();
  const creds = JSON.parse(fs.readFileSync(".local/demo-accounts.json"));
  const seller = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const sp = await seller.newPage();
  sp.on("pageerror", (e) => errors.push(e.message));
  await sp.goto(base + "/seller/login");
  await sp.getByLabel("계정명").fill(creds.seller.username);
  await sp.getByLabel("비밀번호").fill(creds.seller.password);
  await sp.getByRole("button", { name: "로그인", exact: true }).click();
  await sp.waitForURL("**/seller/orders");
  await sp.getByRole("button", { name: "알림 소리 켜기 · 시험 재생" }).click();
  await sp.getByText("소리 켜짐 · 화면을 열어두세요.").waitFor();
  await sp.locator("#pending-alert a").first().click();
  await sp.getByPlaceholder("준비 시간(분)").fill("10");
  await sp.getByRole("button", { name: "수락", exact: true }).click();
  await sp.getByRole("button", { name: "준비 완료", exact: true }).waitFor();
  await op.getByText("준비 중", { exact: true }).waitFor();
  await sp.getByRole("button", { name: "준비 완료", exact: true }).click();
  await op.locator(".badge").filter({ hasText: "준비 완료" }).waitFor();
  await op.screenshot({ path: ".local/order-mobile.png", fullPage: true });
  await organizer.setOffline(true);
  await op
    .getByText("연결 끊김 · 최신 상태를 확인하지 못했습니다.", { exact: false })
    .waitFor();
  await organizer.setOffline(false);
  await op
    .getByText("● 연결됨 · 서버 상태 자동 갱신", { exact: false })
    .waitFor();
  if (
    await op.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("Mobile horizontal overflow");
  const admin = await browser.newContext();
  const ap = await admin.newPage();
  ap.on("pageerror", (e) => errors.push(e.message));
  await ap.goto(base + "/admin/login");
  await ap.getByLabel("계정명").fill(creds.admin.username);
  await ap.getByLabel("비밀번호").fill(creds.admin.password);
  await ap.getByRole("button", { name: "로그인", exact: true }).click();
  await ap.waitForURL("**/admin");
  await ap.getByRole("link", { name: "전체 주문 기록" }).click();
  await ap.locator(".badge").filter({ hasText: "준비 완료" }).first().waitFor();
  if (errors.length) throw Error(errors.join("\n"));
  console.log(
    JSON.stringify({
      homepage: true,
      separateContexts: 4,
      participantAnonymous: true,
      submitPersisted: true,
      organizerEdit: true,
      sellerPasswordLogin: true,
      sellerSoundActivated: true,
      acceptReadyPolling: true,
      adminHistory: true,
      responseLossRetryRecovered: true,
      reconnection: true,
      mobileOverflow: false,
      pageErrors: 0,
      organizerAuth: "test session; actual Kakao not tested",
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
