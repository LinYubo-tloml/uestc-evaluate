#!/usr/bin/env python3
"""
UESTC Automated Course Evaluation Script
电子科技大学自动化评教脚本

Uses Playwright to handle the JS challenge on the eams system.
"""

import os
import sys
import asyncio
import logging
import random
import hashlib
import argparse
import getpass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright


def get_current_semester():
    """Calculate academic year and term from current date.
    Returns (academic_year_str, term_number).
    Aug-Jan = 第1学期 (e.g., "2025-2026", 1)
    Feb-Jul = 第2学期 (e.g., "2025-2026", 2)
    """
    now = datetime.now()
    year = now.year
    month = now.month
    if month >= 8:
        return f"{year}-{year+1}", 1
    else:
        return f"{year-1}-{year}", 2


def prompt_credentials():
    """Prompt for student ID and password if not set via environment."""
    student_id = os.getenv("UESTC_STUDENT_ID")
    password = os.getenv("UESTC_PASSWORD")

    if not student_id:
        print("请输入电子科技大学统一身份认证信息：")
        student_id = input("学号: ").strip()
    if not password:
        password = getpass.getpass("密码: ")

    if not student_id or not password:
        print("错误：学号和密码不能为空", file=sys.stderr)
        sys.exit(1)

    return student_id, password

# ─── Comment Generation Templates ───────────────────────────────────────────

OPENINGS = [
    "通过本课程的学习，",
    "这门课程让我受益匪浅，",
    "经过一学期的学习，",
    "本学期的课程学习让我收获颇丰，",
    "该课程整体安排合理，",
    "这门课的学习体验非常好，",
    "回顾整个学期的学习历程，",
    "该课程的教学让我印象深刻，",
]

CONTENT_POSITIVES = [
    "对相关专业知识有了更深入的理解和掌握。",
    "不仅学到了理论知识，还培养了独立思考和解决问题的能力。",
    "老师的讲解深入浅出，让我能够轻松理解复杂的知识点。",
    "课程内容充实，涵盖了理论与实践的各个方面，非常全面。",
    "教学方式新颖有趣，极大地激发了我的学习兴趣和主动性。",
    "课程作业和实验环节设计得当，有效巩固了课堂所学内容。",
    "课程进度安排合理，重点突出，难点讲解透彻。",
    "课堂氛围活跃，师生互动频繁，学习效果显著。",
    "课程资料准备充分，课件制作精良，便于课后复习。",
    "通过案例分析加深了对理论知识的理解和应用能力。",
]

TEACHER_PRAISES = [
    "老师教学态度认真负责，备课充分，课堂节奏把控得当。",
    "授课教师专业知识扎实，教学经验丰富，讲解条理清晰。",
    "教师能够耐心解答学生疑问，课后辅导及时有效。",
    "老师注重启发式教学，善于引导学生主动思考和探索。",
    "教师治学严谨，对学生要求严格但不失亲和力。",
    "老师善于将理论知识与实际应用相结合，教学效果显著。",
]

SUGGESTIONS = [
    "建议可以适当增加一些实际案例的分析和讨论。",
    "希望今后能够提供更多的动手实践机会。",
    "如果能有更多的课堂互动环节会更好。",
    "建议课程可以适当引入一些前沿技术和行业动态。",
    "期待课程能够增加一些小组合作的项目任务。",
    "建议实验环节可以更加贴近工程实际应用。",
    "希望课后能够提供更多的拓展阅读材料。",
]

CLOSINGS = [
    "总的来说，这是一门非常优秀的课程，值得推荐给学弟学妹。",
    "整体教学效果令人满意，感谢老师的辛勤付出。",
    "对课程总体评价很高，收获满满。",
    "感谢老师一学期以来的认真教学和悉心指导。",
    "课程体验很好，希望以后还有机会选修该老师的课程。",
    "非常满意本课程的教学质量，期待更多类似的优质课程。",
]


def generate_comment(course_name: str) -> str:
    """Generate a unique Chinese evaluation comment per course using course name hash as seed."""
    seed = int(hashlib.md5(course_name.encode()).hexdigest(), 16) % (2**31)
    rng = random.Random(seed)

    parts = [
        rng.choice(OPENINGS),
        rng.choice(CONTENT_POSITIVES),
    ]
    if rng.random() > 0.4:
        pool = [p for p in CONTENT_POSITIVES if p != parts[-1]]
        parts.append(rng.choice(pool))
    parts.append(rng.choice(TEACHER_PRAISES))
    if rng.random() > 0.3:
        parts.append(rng.choice(SUGGESTIONS))
    parts.append(rng.choice(CLOSINGS))

    comment = "".join(parts)
    if len(comment) < 30:
        extra = [p for p in CONTENT_POSITIVES if p not in comment]
        comment += rng.choice(extra) if extra else rng.choice(CONTENT_POSITIVES)
    return comment


# ─── Main Bot Class ─────────────────────────────────────────────────────────

EVAL_LOGIN_URL = "https://eams.uestc.edu.cn/eams/evaluate!search.action?language=zh"
PORTAL_URL = "https://online.uestc.edu.cn/page/"


class UESTCEvaluateBot:
    """Automated course evaluation bot for UESTC eams system."""

    def __init__(self, headless=False, debug=False, slow_mo=100, dry_run=False,
                 use_edge=True, edge_profile=False, portal=False):
        self.headless = headless
        self.debug = debug
        self.slow_mo = slow_mo
        self.dry_run = dry_run
        self.use_edge = use_edge
        self.edge_profile = edge_profile
        self.portal = portal

        self.student_id, self.password = prompt_credentials()

        self.logger = logging.getLogger("UESTCEvalBot")
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    # ── Portal Navigation (off-campus fallback) ──────────────────────────

    async def _navigate_via_portal(self):
        """Navigate to eams via portal: 首页 → 常用服务 → 教务系统 → 课程管理 → 评教."""
        page = self.page
        self.logger.info("Step 1: Opening portal %s", PORTAL_URL)
        await page.goto(PORTAL_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        # Step 2: Find "常用服务" then click "教务系统" within it
        self.logger.info("Step 2: Finding 常用服务 → 教务系统...")
        jw_link = None
        # Try to find "教务系统" link that's near "常用服务"
        for sel in [
            "a:has-text('教务系统')",
            "text=教务系统",
            "[title*='教务系统']",
            "[title*='教务']",
        ]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    jw_link = el
                    self.logger.info(f"Found 教务系统 via: {sel}")
                    break
            except Exception:
                continue

        if not jw_link:
            html = await page.content()
            (Path(__file__).parent / "debug_portal_no_jw.html").write_text(html, encoding="utf-8")
            raise RuntimeError("Could not find 教务系统 on portal. Saved debug_portal_no_jw.html")

        # Click 教务系统 (expect popup to eams)
        async with page.expect_popup() as popup_info:
            await jw_link.click()
        new_page = await popup_info.value
        self.page = new_page
        await new_page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)
        self.logger.info(f"Step 3: Entered eams: {self.page.url}")

        # Handle duplicate-login interstitial that may appear
        await self._handle_duplicate_login_page()

        # Step 4: In eams, click "课程管理" menu
        self.logger.info("Step 4: Finding 课程管理...")
        kc_link = None
        for sel in [
            "a:has-text('课程管理')",
            "text=课程管理",
            "li:has-text('课程管理') a",
            "span:has-text('课程管理')",
        ]:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    kc_link = el
                    self.logger.info(f"Found 课程管理 via: {sel}")
                    break
            except Exception:
                continue

        if not kc_link:
            html = await self.page.content()
            (Path(__file__).parent / "debug_eams_no_kc.html").write_text(html, encoding="utf-8")
            raise RuntimeError("Could not find 课程管理 in eams. Saved debug_eams_no_kc.html")

        await kc_link.click()
        await asyncio.sleep(1.5)

        # Step 5: Click "评教" or "课程问卷评教"
        self.logger.info("Step 5: Finding 评教...")
        for sel in [
            "a:has-text('课程问卷评教')",
            "a:has-text('评教')",
            "a[href*='evaluate']",
            "text=评教",
        ]:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    self.logger.info(f"Found 评教 via: {sel}")
                    await el.click()
                    await self.page.wait_for_load_state("networkidle", timeout=30000)
                    await asyncio.sleep(2)
                    self.logger.info(f"Reached: {self.page.url}")
                    if "evaluate" in self.page.url.lower():
                        self.logger.info("Successfully reached evaluation page via portal!")
                        return
            except Exception:
                continue

        # Fallback: try direct URL if menu nav failed
        self.logger.info("Menu nav incomplete, trying direct URL...")
        await self.page.goto(EVAL_LOGIN_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

    # ── Login ────────────────────────────────────────────────────────────

    async def login(self):
        """Navigate to evaluation page, handle JS challenge and login."""
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

        if self.edge_profile:
            user_data_dir = str(Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data")
            self.logger.info(f"Launching persistent Edge: {user_data_dir}")
            # Persistent context fails if Edge is running — kill first
            os.system("taskkill /F /IM msedge.exe >nul 2>&1")
            await asyncio.sleep(1)
            self.context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="msedge",
                headless=self.headless,
                slow_mo=self.slow_mo,
                viewport={"width": 1280, "height": 800},
                args=launch_args,
            )
            self.browser = None
            self.page = await self.context.new_page()
        else:
            if self.use_edge:
                self.browser = await self._playwright.chromium.launch(
                    channel="msedge",
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=launch_args,
                )
            else:
                self.browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=launch_args,
                )
            ctx = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/132.0.0.0 Safari/537.36"
                ),
            )
            self.context = ctx
            self.page = await ctx.new_page()

        # Auto-dismiss any alert dialogs (validation warnings, etc.)
        self.page.on("dialog", lambda d: d.dismiss())

        # Navigate to evaluation page (triggers JS challenge + login redirect)
        if self.portal:
            await self._navigate_via_portal()
        else:
            self.logger.info("Navigating to evaluation page...")
            await self.page.goto(EVAL_LOGIN_URL, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)

        if "login" in self.page.url.lower() or "idas" in self.page.url.lower():
            self.logger.info("Redirected to IDAS login, filling credentials...")
            await self._fill_login_form()
        elif "evaluate" in self.page.url.lower():
            self.logger.info("Already logged in")
            # Stay on search.action — it has semester selector + course list
            await self._handle_duplicate_login_page()
        else:
            self.logger.warning(f"Unexpected page: {self.page.url}")

        # Handle duplicate-login interstitial
        await self._handle_duplicate_login_page()

    async def _fill_login_form(self):
        """Fill and submit the IDAS unified auth login form."""
        page = self.page
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        # Switch to username/password tab if needed
        pwd_tab = await page.query_selector("#pwdLoginSpan")
        if pwd_tab:
            await pwd_tab.click()
            await asyncio.sleep(0.3)

        # Username field
        username_el = await page.query_selector("input#username")
        if not username_el or not await username_el.is_visible():
            raise RuntimeError("Could not find username input (#username)")

        # Password field (visible plaintext input, JS encrypts before submit)
        password_el = await page.query_selector("input#password[type='password']")
        if not password_el or not await password_el.is_visible():
            raise RuntimeError("Could not find password input (#password)")

        # Check for visible CAPTCHA
        captcha_div = await page.query_selector("#captchaDiv")
        has_captcha = captcha_div and await captcha_div.is_visible()

        if has_captcha and self.headless:
            await self._save_debug_screenshot("captcha_detected")
            raise RuntimeError("CAPTCHA blocked in headless mode. Re-run with --no-headless.")
        if has_captcha and not self.headless:
            await self._handle_captcha_interactive()

        await username_el.fill(self.student_id)
        await password_el.fill(self.password)
        self.logger.info("Credentials filled")

        # Login button triggers startLogin() which encrypts the password & submits
        login_btn = await page.query_selector("a#login_submit")
        if not login_btn:
            raise RuntimeError("Could not find login button (#login_submit)")

        await login_btn.click()
        self.logger.info("Login submitted, waiting for redirect...")

        try:
            await page.wait_for_url("**/evaluate!**", timeout=10000)
            self.logger.info("Successfully logged in")
        except Exception:
            # Check for SMS 2FA (reAuthLoginView)
            if "reAuthLoginView" in page.url or "isMultifactor=true" in page.url:
                self.logger.info("SMS verification required (非可信浏览器)")
                await self._handle_sms_verification()
                return

            await self._save_debug_screenshot("login_redirect_failed")

            # Check for error messages
            for sel in ["#showErrorTip", "#formErrorTip", ".form-error",
                        ".error", ".alert-danger", "#pwdErrorTip", "#nameErrorTip"]:
                error_el = await page.query_selector(sel)
                if error_el:
                    text = (await error_el.inner_text()).strip()
                    if text and len(text) > 0:
                        raise RuntimeError(f"Login error: {text}")

            # Check if CAPTCHA appeared after login attempt
            captcha_div = await page.query_selector("#captchaDiv")
            if captcha_div and await captcha_div.is_visible():
                if self.headless:
                    raise RuntimeError("CAPTCHA required — re-run with --no-headless")
                await self._handle_captcha_interactive()
                # Retry: re-fill password and re-click login
                pwd = await page.query_selector("input#password[type='password']")
                if pwd:
                    await pwd.fill(self.password)
                await page.click("a#login_submit")
                await page.wait_for_url("**/evaluate!**", timeout=30000)
                self.logger.info("Successfully logged in (after CAPTCHA)")
                return

            raise RuntimeError("Login redirect timed out — check debug screenshot")

    async def _handle_duplicate_login_page(self):
        """Handle the 'duplicate login kicked out' interstitial."""
        for _ in range(3):
            body = await self.page.inner_text("body")
            if "重复登录" in body or "点击此处" in body:
                self.logger.info("Duplicate-login page detected, continuing...")
                link = await self.page.query_selector("a[href*='evaluate'], a:has-text('点击此处')")
                if link:
                    await link.click()
                    await self.page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)
            else:
                break

    async def _detect_captcha(self) -> bool:
        """Check if CAPTCHA is visible on the login page."""
        page = self.page
        for sel in [
            "img[src*='captcha']", "img[src*='verify']",
            "img[src*='code']", "img[src*='rand']",
        ]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return True
        return False

    async def _handle_captcha_interactive(self):
        """Save CAPTCHA image and ask user to solve it."""
        page = self.page
        captcha_img = None
        for sel in [
            "img[src*='captcha']", "img[src*='verifyCode']",
            "img[src*='code']", "img[src*='rand']",
        ]:
            captcha_img = await page.query_selector(sel)
            if captcha_img:
                break

        captcha_path = Path(__file__).parent / "captcha.png"
        if captcha_img:
            await captcha_img.screenshot(path=str(captcha_path))
        else:
            await page.screenshot(path=str(captcha_path))

        print(f"\n{'='*50}")
        print(f"[!] CAPTCHA detected! Screenshot saved to: {captcha_path}")
        code = input("CAPTCHA code: ").strip()

        for sel in [
            "input[name='captcha']", "input[name='verifyCode']",
            "input[name='RANDOMCODE']", "input[name*='code' i]",
        ]:
            inp = await page.query_selector(sel)
            if inp and await inp.is_visible():
                await inp.fill(code)
                self.logger.info("CAPTCHA code entered")
                return
        self.logger.warning("Could not find CAPTCHA input field")

    async def _handle_sms_verification(self):
        """Handle IDAS SMS two-factor authentication page."""
        page = self.page
        self.logger.info("Handling SMS verification...")

        # Wait for the reAuth page to load
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        # Click "获取验证码" to request SMS code
        get_code_btn = await page.query_selector(
            "a:has-text('获取验证码'), button:has-text('获取验证码'), "
            "input[value*='获取验证码'], #getVerificationCode, "
            "#getSmsCode, .get-code-btn"
        )
        if get_code_btn:
            await get_code_btn.click()
            self.logger.info("Requested SMS code — check your phone")
        else:
            self.logger.warning("Could not find '获取验证码' button, proceeding anyway")

        if self.headless:
            raise RuntimeError(
                "SMS verification required in headless mode.\n"
                "Re-run with: python evaluate.py --no-headless"
            )

        print(f"\n{'='*50}")
        print("[!] 需要短信二次认证")
        print("[!] 已点击「获取验证码」，请查看手机短信")
        sms_code = input("短信验证码: ").strip()

        if not sms_code:
            raise RuntimeError("No SMS code entered — aborting")

        # Fill SMS code input
        sms_input = None
        for sel in [
            "input#verificationCode", "input#smsCode", "input#code",
            "input[name='verificationCode']", "input[name='smsCode']",
            "input[name='code']", "input[type='text']:not(#username)",
        ]:
            sms_input = await page.query_selector(sel)
            if sms_input and await sms_input.is_visible():
                break
            sms_input = None

        if not sms_input:
            await self._save_debug_screenshot("no_sms_input")
            raise RuntimeError("Could not find SMS code input field")

        await sms_input.fill(sms_code)
        self.logger.info("SMS code entered")

        # Click login/confirm button
        login_btn = await page.query_selector(
            "a:has-text('登录'), button:has-text('登录'), "
            "input[value='登录'], #login_submit, .login-btn"
        )
        if login_btn:
            await login_btn.click()
            self.logger.info("SMS verification submitted, waiting for redirect...")
        else:
            raise RuntimeError("Could not find submit button on SMS page")

        try:
            await page.wait_for_url("**/evaluate!**", timeout=30000)
            self.logger.info("Successfully logged in (via SMS)")
        except Exception:
            await self._save_debug_screenshot("sms_login_redirect_failed")
            raise RuntimeError("Login redirect after SMS verification timed out")

    # ── Semester Selection ─────────────────────────────────────────────────

    async def _select_semester(self):
        """Auto-select the correct academic year and term via JS or widget click."""
        page = self.page
        academic_year, term = get_current_semester()
        self.logger.info(f"Target semester: {academic_year} 第{term}学期")

        # Read current semester id from hidden input
        current_id = await page.evaluate(
            "document.querySelector('#semesterCalendar_target')?.value || ''"
        )
        self.logger.info(f"Current semester.id: {current_id}")

        # Build a map of term text → semester.id from the term table
        term_map = {}
        term_tds = await page.query_selector_all("#semesterCalendar_termTb td[val]")
        for td in term_tds:
            t = (await td.inner_text()).strip()
            v = await td.get_attribute("val")
            term_map[t] = v

        target_term_text = f"{term}学期"
        target_id = None
        for t, v in term_map.items():
            if str(term) in t:
                target_id = v
                break

        self.logger.info(f"Term map: {term_map}, target: {target_term_text} → id={target_id}")

        if not target_id:
            self.logger.warning("Could not find target semester ID, skipping")
            html = await page.content()
            (Path(__file__).parent / "debug_no_semester.html").write_text(html, encoding="utf-8")
            self.logger.info(f"Page saved to debug_no_semester.html, URL: {page.url}")
            return

        if current_id == target_id:
            self.logger.info("Semester already correct")
            return

        # Open the calendar widget by clicking the semester input
        cal_input = await page.query_selector("input.calendar-text")
        if cal_input:
            self.logger.info("Opening semester calendar widget...")
            await cal_input.click()
            await asyncio.sleep(0.5)

        # Click the correct year in the now-visible year table
        year_tds = await page.query_selector_all("#semesterCalendar_yearTb td[index]")
        for td in year_tds:
            text = (await td.inner_text()).strip()
            if text == academic_year:
                cls = await td.get_attribute("class") or ""
                if "selected" not in cls:
                    self.logger.info(f"Clicking year: {academic_year}")
                    await td.click()
                    await asyncio.sleep(0.5)
                else:
                    self.logger.info(f"Year already selected: {academic_year}")
                break

        # Click the correct term
        for td in term_tds:
            text = (await td.inner_text()).strip()
            if str(term) in text:
                self.logger.info(f"Clicking term: {text} (id={target_id})")
                await td.click()
                await asyncio.sleep(1)
                break

        # Click "切换学期" button for a full page submit (more reliable than AJAX callback)
        submit_btn = await page.query_selector("input[value='切换学期']")
        if submit_btn:
            self.logger.info("Clicking 切换学期 for full page submit...")
            await submit_btn.click()
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(3)
        else:
            # Fallback: JS call
            self.logger.info(f"Calling changeSemester({target_id}) via JS...")
            await page.evaluate(f"changeSemester('{target_id}')")
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle")

        self.logger.info(f"Page URL after semester change: {page.url}")

        # Check for courses
        body = await page.inner_text("body")
        if "评教未开放" in body:
            self.logger.warning(f"Semester {academic_year} 第{term}学期: evaluation not yet open!")
            html = await page.content()
            (Path(__file__).parent / "debug_semester_page.html").write_text(html, encoding="utf-8")
        else:
            self.logger.info(f"Semester set: {academic_year} 第{term}学期")

    # ── Course Star Rating ─────────────────────────────────────────────────

    async def rate_courses(self):
        """Rate all courses on the evaluation page."""
        page = self.page
        if "evaluate" not in page.url.lower():
            await page.goto(EVAL_LOGIN_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            await self._handle_duplicate_login_page()

        # Auto-select correct semester
        await self._select_semester()

        self.logger.info("Reading course list...")
        rows = await page.query_selector_all("table.gridtable tbody tr.griddata-even, table.gridtable tbody tr.griddata-odd")
        courses = []
        for i, row in enumerate(rows):
            cells = await row.query_selector_all("td")
            if len(cells) >= 4:
                code = (await cells[0].inner_text()).strip()
                name = (await cells[1].inner_text()).strip()
                dept = (await cells[2].inner_text()).strip()
                teacher = (await cells[3].inner_text()).strip()
                courses.append({
                    "code": code,
                    "name": name,
                    "dept": dept,
                    "teacher": teacher,
                    "star_td_id": f"starTd_{i}",
                })

        self.logger.info(f"Found {len(courses)} courses:")
        for c in courses:
            self.logger.info(f"  {c['code']} {c['name']} — {c['teacher']}")

        if not courses:
            self.logger.info("No courses to evaluate (all done or evaluation not open)")
            return courses
        num_five = random.randint(3, min(6, len(courses)))
        indices = list(range(len(courses)))
        five_indices = set(random.sample(indices, num_five))

        self.logger.info(f"Rating: {num_five} courses at 5★, {len(courses) - num_five} at 4★")

        if self.dry_run:
            for i, c in enumerate(courses):
                stars = 5 if i in five_indices else 4
                self.logger.info(f"  [DRY RUN] {c['name']}: {stars}★")
            return courses

        # Click <li> elements to set stars via the page's onclick handlers
        for i, c in enumerate(courses):
            stars = 5 if i in five_indices else 4
            td = await page.query_selector(f"td#starTd_{i}")
            if td:
                lis = await td.query_selector_all("li")
                if len(lis) >= stars:
                    await lis[stars - 1].click()
                    await asyncio.sleep(0.15)
                else:
                    self.logger.warning(f"  Not enough <li> in starTd_{i} for {c['name']}")
            else:
                self.logger.warning(f"  starTd_{i} not found for {c['name']}")

        self.logger.info(f"Stars set for {len(courses)} courses")
        return courses

    async def click_next_button(self):
        """Click the '下一步' button on the index page."""
        if self.dry_run:
            self.logger.info("[DRY RUN] Would click '下一步'")
            return
        btn = await self.page.query_selector("input[value='下一步']")
        if btn:
            await btn.click()
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await self._handle_duplicate_login_page()
        else:
            raise RuntimeError("'下一步' button not found")

    # ── Textbook Evaluation ───────────────────────────────────────────────

    async def textbook_eval(self):
        """Handle the textbook evaluation page.

        The textbook evaluation form uses Backbone.js which is broken on the
        school's site (require is not defined). We skip individual textbook
        evaluation and go directly to teacher evaluation.
        """
        page = self.page
        self.logger.info("Textbook evaluation page (skipping — JS broken on school site)...")

        body = await page.inner_text("body")
        if "教材评价" not in body and "教材" not in body:
            self.logger.warning("Not on textbook evaluation page, trying to proceed")
            return

        if self.dry_run:
            self.logger.info("[DRY RUN] Would click '提交，进入教师评教'")
            return

        # Click "提交，进入教师评教" to skip to teacher evaluation
        btn = await page.query_selector("input[value='提交，进入教师评教']")
        if btn:
            await btn.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await self._handle_duplicate_login_page()
            self.logger.info("Proceeding to teacher evaluation...")
        else:
            raise RuntimeError("'提交，进入教师评教' button not found")

    # ── Teacher Evaluation (per course) ───────────────────────────────────

    async def teacher_eval_all(self, courses: list):
        """
        Evaluate each teacher. The page navigates through courses one by one
        using '上一步'/'下一步' buttons that trigger JS validation and form submission.
        """
        page = self.page
        total = len(courses)
        self.logger.info(f"Teacher evaluation: {total} courses")

        for idx in range(total):
            course = courses[idx]
            self.logger.info(f"[{idx+1}/{total}] {course['name']} — {course['teacher']}")

            # Verify we're on teacher eval page
            body = await page.inner_text("body")
            if "文字评价" not in body and "评教指标" not in body:
                self.logger.warning("Not on teacher eval page, trying to proceed")
                await self._save_debug_screenshot(f"teacher_eval_unexpected_{idx}")

            if self.dry_run:
                self.logger.info(f"  [DRY RUN] Would evaluate teacher for {course['name']}")
                continue

            await self._do_single_teacher_eval(course)

            # Click "下一步" to go to next course; on last course this submits
            next_btn = await page.query_selector("input[value='下一步']")
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await self._handle_duplicate_login_page()

                # Check if we're still on teacher eval (next course) or done
                new_body = await page.inner_text("body")
                if "文字评价" not in new_body and "评教指标" not in new_body:
                    self.logger.info("Teacher evaluation completed (no more courses)")
                    break
            else:
                self.logger.error("'下一步' button not found!")
                await self._save_debug_screenshot(f"no_next_teacher_{idx}")
                break

    async def _do_single_teacher_eval(self, course: dict):
        """Fill teacher evaluation form for the current course."""
        page = self.page

        # 1. Star rating — click 5th star
        star_td = await page.query_selector("td[id^='starTd_']")
        if star_td:
            lis = await star_td.query_selector_all("li")
            if len(lis) >= 5:
                await lis[4].click()
                await asyncio.sleep(0.1)
        else:
            self.logger.debug("  No star td found (may not be required)")

        # 2. AI questions — answer "否" (false) to all
        for name in ["aiContent", "aiAuxiliary", "aiAgent"]:
            radio_no = await page.query_selector(
                f"input[name='{name}'][value='false']"
            )
            if radio_no:
                try:
                    await radio_no.click()
                except Exception:
                    pass  # radio might be hidden or already selected
                await asyncio.sleep(0.05)

        # 3. Evaluation indicators — select 3-5 random checkboxes (min 3 required)
        checkboxes = await page.query_selector_all("input[name='evaIndex']")
        if checkboxes:
            num_select = random.randint(3, min(5, len(checkboxes)))
            selected = random.sample(range(len(checkboxes)), num_select)
            for i in selected:
                try:
                    await checkboxes[i].click()
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            self.logger.debug(f"  Selected {num_select}/{len(checkboxes)} indicators")
        else:
            self.logger.debug("  No checkboxes found")

        # 4. Text comment (required)
        comment = generate_comment(f"{course['name']}_{course['teacher']}")
        textarea = await page.query_selector("textarea#evaText")
        if textarea:
            await textarea.fill(comment)
            self.logger.debug(f"  Comment: {comment[:50]}...")
        else:
            self.logger.warning("  No comment textarea found")

    # ── Main Flow ────────────────────────────────────────────────────────

    async def run(self):
        """Main execution flow."""
        try:
            await self.login()

            if self.dry_run:
                self.logger.info("=" * 50)
                self.logger.info("DRY RUN MODE — no evaluations will be submitted")
                self.logger.info("=" * 50)

            # Step 1: Rate all courses on index page
            courses = await self.rate_courses()
            if not courses:
                self.logger.info("No courses to evaluate (all done!)")
                return

            # Step 2: Click "下一步" → textbook evaluation
            await self.click_next_button()

            # Step 3: Textbook evaluation → click through
            await self.textbook_eval()

            # Step 4: Teacher evaluation (one page per course)
            await self.teacher_eval_all(courses)

            self.logger.info("=" * 50)
            self.logger.info("Done!")
            self.logger.info("=" * 50)

        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            await self._save_debug_screenshot("fatal_error")
            raise
        finally:
            if self.edge_profile:
                if self.context:
                    await self.context.close()
                    self.logger.info("Edge profile closed")
            elif self.browser:
                await self.browser.close()
                self.logger.info("Browser closed")
            if self._playwright:
                await self._playwright.stop()

    # ── Navigation Helpers ───────────────────────────────────────────────

    async def _click_next_or_submit(self):
        """Try to find and click a next/submit button."""
        page = self.page
        for val in ["下一步", "提交", "确认", "保存", "提交，进入教师评教"]:
            btn = await page.query_selector(f"input[value='{val}']")
            if btn and await btn.is_visible():
                if not self.dry_run:
                    await btn.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(1)
                return True
        return False

    # ── Debug Helpers ────────────────────────────────────────────────────

    async def _save_debug_screenshot(self, name: str):
        """Save a debug screenshot."""
        if not self.debug:
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(__file__).parent / f"debug_{name}_{timestamp}.png"
            await self.page.screenshot(path=str(path))
            self.logger.debug(f"Screenshot saved: {path}")
        except Exception as e:
            self.logger.debug(f"Failed to save screenshot: {e}")


# ─── CLI Entry Point ────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="UESTC Automated Course Evaluation (电子科技大学自动化评教)"
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run browser in headless mode (default: False, site JS challenge blocks headless)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging and screenshots"
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=100,
        help="Delay between actions in ms (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be evaluated without submitting",
    )
    parser.add_argument(
        "--edge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use Microsoft Edge (default: True, uses system-installed Edge)",
    )
    parser.add_argument(
        "--profile",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use Edge user profile to avoid SMS re-auth (default: True)",
    )
    parser.add_argument(
        "--portal",
        action="store_true",
        help="Navigate via online.uestc.edu.cn portal (off-campus fallback)",
    )

    args = parser.parse_args()

    # Load .env file if present
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    bot = UESTCEvaluateBot(
        headless=args.headless,
        debug=args.debug,
        slow_mo=args.slow_mo,
        dry_run=args.dry_run,
        use_edge=args.edge,
        edge_profile=args.profile,
        portal=args.portal,
    )

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
