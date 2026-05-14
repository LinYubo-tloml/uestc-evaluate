# UESTC Course Evaluation (电子科技大学自动化评教)

Automatically complete course evaluations on the UESTC eams system using Playwright. Bypasses both the anti-bot JS challenge and the campus-network IP restriction.

## Usage

```bash
# On campus network / VPN → direct eams access
python evaluate.py

# Off campus → via online.uestc.edu.cn portal
python evaluate.py --portal
```

The script prompts for student ID and password if not set via environment variables.

## Prerequisites

- **Python 3.8+** with Playwright (`pip install playwright && playwright install chromium`)
- **Microsoft Edge** (installed by default on Windows 10/11)
- **Logged into eams at least once in Edge** — the script reuses Edge's cookies to avoid SMS re-auth
- **Edge must be closed** before running — the script uses Edge's user profile exclusively

## How It Works (Two Obstacles)

### 1. Anti-bot JS Challenge (`$_ts` system)

The eams site returns HTTP 202 with an empty `<body>`. A `<script src="adecd85.js">` runs a browser-fingerprinting challenge that blocks headless Chrome.

**Bypass:** The script launches Edge in visible mode with the user's real profile via `launch_persistent_context`. Edge's profile carries login cookies and a trusted browser fingerprint — the JS challenge passes because it sees a real user browser, not an automation tool.

### 2. Campus-network IP Restriction

When accessed from an off-campus IP, the evaluation page returns a stripped-down version: only `<span>评教未开放</span>`, no semester selector, no course table, no forms.

**Bypass (`--portal` mode):** Instead of hitting eams directly, the script navigates through the university portal:

```
online.uestc.edu.cn/page/ → 常用服务 → 教务系统 → 课程管理 → 评教
```

This 5-step click-through reaches eams via an internal routing path that the server treats as trusted.

**Critical detail:** After reaching the evaluation page, the script must NOT call `page.goto()` to re-navigate the URL — this would lose the portal session context and trigger the IP restriction again. The semester is changed via the "切换学期" button (full-page POST), not via the AJAX calendar widget callback.

## Semester Auto-Selection

The script calculates the current academic year and term from the system date:

| Months | Academic Year | Term |
|--------|--------------|------|
| Aug – Jan | `YYYY-YYYY+1` | 第1学期 |
| Feb – Jul | `YYYY-1-YYYY` | 第2学期 |

It opens the semesterCalendar widget, clicks the matching year tile, clicks the term tile, then clicks "切换学期" to submit. No manual input needed.

If the evaluation period is not yet open, the script logs a warning and exits — run it again when evaluations open.

## Configuration

Credentials in priority order:

1. **Environment variables** (`~/.claude/settings.local.json` or shell):
   ```json
   { "env": { "UESTC_STUDENT_ID": "...", "UESTC_PASSWORD": "..." } }
   ```
2. **`.env` file** in this directory (copy `.env.example`)
3. **Interactive prompt** — the script asks on each run

## Options

| Flag | Description |
|------|-------------|
| `--portal` | Off-campus: navigate via `online.uestc.edu.cn` portal |
| `--headless` | Run headless (**will fail** — JS challenge blocks it) |
| `--no-headless` | Show browser window (**default**) |
| `--debug` | Debug logging + screenshots on error |
| `--dry-run` | Preview without submitting |
| `--no-edge` | Use bundled Chromium instead of Edge |
| `--no-profile` | Fresh browser context (triggers SMS re-auth) |

## Evaluation Rules

- **Course evaluation:** 3–6 random courses get 5 stars, rest get 4 stars
- **Textbook evaluation (教材评测):** skipped (school's Backbone.js is broken)
- **Teacher evaluation (教师评测):** all maximum + unique Chinese comment per course
- **Comments:** auto-generated, deterministic per course (MD5-seeded), every sentence unique

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TargetClosedError` on launch | Edge is already running | Close all Edge windows first |
| SMS verification prompt | Fresh browser context (no cookies) | Use `--profile` (default) after logging in manually once |
| "评教未开放" on direct mode | Off-campus IP | Use `--portal` flag |
| "评教未开放" on portal mode | AJAX semester switch didn't take | Fixed: uses "切换学期" button now |
| 0 courses found | Wrong semester selected | Check system date — semester auto-calc may need adjustment |
| `RuntimeError: Could not find 教务系统` | Portal page structure changed | Run with `--debug`, check saved HTML, update selectors |
| CAPTCHA appears | Unusual login pattern | Run with `--no-headless` to solve manually |

## Cross-Device Notes

- **Windows only** — uses `taskkill`, Edge user profile path (`%LOCALAPPDATA%\Microsoft\Edge\User Data`), and Edge channel
- **First-time setup on a new device:** open Edge, log into eams manually once, close Edge, then run the script
- **Password changes:** update `.env` file or environment variables
- The script kills all Edge processes before launching — save any Edge work first
