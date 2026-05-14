#!/usr/bin/env python3
"""Diagnose login failure - dump page content after login attempt."""
import asyncio, os, sys
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
load_dotenv(Path(__file__).parent / ".env")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge", headless=False, slow_mo=200,
            args=["--disable-blink-features=AutomationControlled",
                  "--disable-features=IsolateOrigins,site-per-process"],
        )
        page = await browser.new_page(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        )
        page.on("dialog", lambda d: print(f"  DIALOG: {d.message}") or d.dismiss())

        await page.goto("https://eams.uestc.edu.cn/eams/evaluate!search.action?language=zh",
                        wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        print(f"URL: {page.url}")

        if "login" in page.url.lower() or "idas" in page.url.lower():
            # Check CAPTCHA status before login
            captcha_div = await page.query_selector("#captchaDiv")
            if captcha_div:
                style = await captcha_div.get_attribute("style") or ""
                display = await page.evaluate("el => window.getComputedStyle(el).display", captcha_div)
                print(f"Captcha div: style='{style}', computed display='{display}'")

            # Fill and submit
            await page.fill("input#username", os.getenv("UESTC_STUDENT_ID"))
            await page.fill("input#password", os.getenv("UESTC_PASSWORD"))
            print(f"Filled: {os.getenv('UESTC_STUDENT_ID')} / {'*' * len(os.getenv('UESTC_PASSWORD', ''))}")
            await page.click("a#login_submit")
            print("Clicked login...")
            await asyncio.sleep(5)

            # Check what happened
            print(f"\nURL after: {page.url}")
            body = await page.inner_text("body")
            print(f"Body:\n{body[:2000]}")

            # Check for error messages
            for sel in ["#showErrorTip", "#formErrorTip", "#pwdErrorTip", "#nameErrorTip",
                        "#captchaErrorTip", ".form-error", ".error", ".alert-danger"]:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text()).strip()
                    display = await page.evaluate("el => window.getComputedStyle(el).display", el)
                    print(f"  {sel}: text='{text}' display={display}")

            # Check captcha after
            captcha_div = await page.query_selector("#captchaDiv")
            if captcha_div:
                display = await page.evaluate("el => window.getComputedStyle(el).display", captcha_div)
                print(f"  Captcha after login: display={display}")

            await page.screenshot(path=str(Path(__file__).parent / "login_check.png"))
            print("\nScreenshot saved to login_check.png")

        await browser.close()

asyncio.run(main())
