"""Seed data — the same records the React mock ships with.

IDs are copied verbatim (`c-401`, `nova`, `vip`, `t-1`, …). That is deliberate:
when the client is repointed at this API, anything that was hard-coded against
a mock id keeps working, and the two data sources can be diffed record by
record while the migration is in flight.

Seeding is idempotent. `seed()` does nothing if a workspace already exists, so
restarting the server never duplicates or resets real data; `seed(force=True)`
is what the test-suite and `--reseed` use.
"""

from __future__ import annotations

import math
import random

from . import db, deployment
from .config import settings
from .domain import ago_iso, iso, log, seeded_series
from .security import hash_api_key, hash_password, new_id

# ---------------------------------------------------------------- people

FIRST = ["Ava", "Noah", "Mia", "Liam", "Zara", "Omid", "Sara", "Kian", "Elena", "Reza",
         "Nina", "Arash", "Leyla", "Marco", "Yasmin", "Daniel"]
FIRST_FA = ["آوا", "نوح", "میا", "لیام", "زارا", "امید", "سارا", "کیان", "الینا", "رضا",
            "نینا", "آرش", "لیلا", "مارکو", "یاسمین", "دانیال"]
LAST = ["Reed", "Karimi", "Vance", "Torres", "Haddad", "Novak", "Ahmadi", "Blake",
        "Rossi", "Sadeghi", "Lund", "Farhadi"]
LAST_FA = ["رید", "کریمی", "ونس", "تورس", "حداد", "نواک", "احمدی", "بلیک",
           "روسی", "صادقی", "لوند", "فرهادی"]
SOURCES = [
    ("signup", "Website signup", "ثبت‌نام سایت"),
    ("import", "CSV import", "ورود از CSV"),
    ("shopify", "Shopify", "شاپیفای"),
    ("api", "API", "API"),
    ("form", "Landing form", "فرم لندینگ"),
]
TAGS = ["vip", "newsletter", "trial", "beta", "enterprise", "apac", "emea"]


def _agents() -> list[dict]:
    return [
        dict(id="nova", name_en="NOVA", name_fa="نووا",
             role_en="Copywriter & send-time optimiser", role_fa="کپی‌رایتر و بهینه‌ساز زمان ارسال",
             emoji="🪄", tint="linear-gradient(140deg,#ff9d5c,#c2410c)", model="claude-opus-5",
             autonomy="approve", status="active", runs=1284, success=96.4, actions_today=42,
             budget=120, temperature=0.7, last_run_at=ago_iso(minutes=14),
             skills=["copywriting", "subject-lines", "send-time", "personalisation"],
             tools=["contacts.read", "campaigns.write", "analytics.read", "brand.read"],
             instructions="You are the senior copywriter at Acme. Always write in second person, "
                          "one primary CTA per email, and never use exclamation marks.",
             memory=["VIP contacts respond better to subject lines under 45 characters.",
                     "Tuesday morning sends outperform Thursday by 12%.",
                     "The word \"free\" raises the spam rate on this list."],
             sparkline=seeded_series(14, base=30, trend=0.9, seed=11)),
        dict(id="atlas", name_en="ATLAS", name_fa="اطلس",
             role_en="Deliverability & warm-up engineer", role_fa="مهندس تحویل‌پذیری و گرم‌کردن آی‌پی",
             emoji="🛰️", tint="linear-gradient(140deg,#57c7ff,#0b5c8f)", model="claude-sonnet-5",
             autonomy="full", status="active", runs=3106, success=99.1, actions_today=118,
             budget=400, temperature=0.2, last_run_at=ago_iso(minutes=3),
             skills=["warm-up", "bounce-triage", "dns", "throttling"],
             tools=["domains.write", "suppression.write", "analytics.read"],
             instructions="Protect sender reputation above all else. Throttle before a provider "
                          "starts filtering, not after.",
             memory=["Yahoo tightens filtering above 40k/hour on a shared pool."],
             sparkline=seeded_series(14, base=90, trend=0.2, seed=23)),
        dict(id="echo", name_en="ECHO", name_fa="اکو",
             role_en="Reply triage & conversation", role_fa="دسته‌بندی و پاسخ به گفت‌وگوها",
             emoji="🎧", tint="linear-gradient(140deg,#b98cff,#5b21b6)", model="claude-sonnet-5",
             autonomy="approve", status="active", runs=872, success=93.8, actions_today=61,
             budget=200, temperature=0.5, last_run_at=ago_iso(minutes=7),
             skills=["intent-detection", "reply-drafting", "escalation", "sentiment"],
             tools=["inbox.read", "inbox.write", "crm.write"],
             instructions="Answer in the language the customer wrote in. Escalate anything about "
                          "refunds or legal to a human.",
             memory=["Opt-out requests must be actioned before replying."],
             sparkline=seeded_series(14, base=45, trend=0.6, seed=31)),
        dict(id="vega", name_en="VEGA", name_fa="وگا",
             role_en="Segmentation & audience analyst", role_fa="تحلیلگر بخش‌بندی و مخاطب",
             emoji="🔭", tint="linear-gradient(140deg,#4ad07d,#0f7a45)", model="claude-opus-5",
             autonomy="suggest", status="paused", runs=412, success=91.2, actions_today=0,
             budget=80, temperature=0.4, last_run_at=ago_iso(minutes=600),
             skills=["segmentation", "churn-prediction", "lookalikes"],
             tools=["contacts.read", "segments.write", "analytics.read"],
             instructions="Never build a segment smaller than 500 contacts without flagging it.",
             memory=["Engagement below 20 for 120 days predicts churn at 78% precision."],
             sparkline=seeded_series(14, base=20, trend=-0.5, seed=41)),
        dict(id="orion", name_en="ORION", name_fa="اوریون",
             role_en="Experiment designer & referee", role_fa="طراح و داور آزمایش‌ها",
             emoji="⚗️", tint="linear-gradient(140deg,#5b8cff,#1b3fae)",
             model="claude-haiku-4-5-20251001",
             autonomy="full", status="active", runs=640, success=97.7, actions_today=9,
             budget=60, temperature=0.3, last_run_at=ago_iso(minutes=52),
             skills=["ab-testing", "stats", "auto-promote"],
             tools=["experiments.write", "analytics.read"],
             instructions="Never call a test below 95% confidence or 1,000 samples per arm.",
             memory=["Subject-line tests need ~4h to reach significance on this list."],
             sparkline=seeded_series(14, base=12, trend=1.2, seed=53)),
    ]


def _segments() -> list[dict]:
    return [
        dict(id="vip", name_en="VIP Customers", name_fa="مشتریان ویژه", emoji="👑", size=25000,
             growth=4.2, open_rate=62.6, tint="linear-gradient(140deg,#4ad07d,#0f7a45)", live=1,
             rules=[{"field": "orders", "op": "gte", "value": "3"},
                    {"field": "ltv", "op": "gte", "value": "500"}]),
        dict(id="trial", name_en="Trial Signups", name_fa="ثبت‌نام آزمایشی", emoji="🧪", size=12400,
             growth=11.8, open_rate=48.1, tint="linear-gradient(140deg,#5b8cff,#1b3fae)", live=1,
             rules=[{"field": "plan", "op": "eq", "value": "trial"}]),
        dict(id="churn", name_en="Win-back", name_fa="بازگرداندنی‌ها", emoji="🎯", size=8600,
             growth=-2.4, open_rate=21.3, tint="linear-gradient(140deg,#ff8a5b,#b8380f)", live=1,
             rules=[{"field": "lastOpen", "op": "before", "value": "90d"}]),
        dict(id="newsletter", name_en="Newsletter", name_fa="خبرنامه", emoji="📰", size=34100,
             growth=6.9, open_rate=39.4, tint="linear-gradient(140deg,#b98cff,#5b21b6)", live=0,
             rules=[{"field": "tag", "op": "has", "value": "newsletter"}]),
        dict(id="all", name_en="All Contacts", name_fa="همهٔ مخاطبان", emoji="🌐", size=48200,
             growth=5.1, open_rate=34.8, tint="linear-gradient(140deg,#9b6bff,#4a1fae)", live=1,
             rules=[]),
    ]


def _campaign(cid, en, fa, ctype, status, *, agent, segment, recipients, sent=None,
              open_r=0.4, click=0.08, reply=0.012, unsub=0.0021, bounce=0.011, deliv=0.973,
              revenue=0.0, updated_min=0, scheduled=None, subj_en="", subj_fa="", seed=7):
    sent = recipients if sent is None else sent
    return dict(
        id=cid, name_en=en, name_fa=fa, subject_en=subj_en, subject_fa=subj_fa,
        type=ctype, status=status, agent_id=agent, segment_id=segment,
        recipients=recipients, sent=sent,
        delivered=round(sent * deliv), opens=round(sent * open_r), clicks=round(sent * click),
        replies=round(sent * reply), unsubs=round(sent * unsub), bounces=round(sent * bounce),
        revenue=revenue, scheduled_for=scheduled,
        trend=seeded_series(14, base=max(recipients / 40, 1), trend=0.5, seed=seed),
        created_at=ago_iso(minutes=updated_min + 4000), updated_at=ago_iso(minutes=updated_min),
    )


def _campaigns() -> list[dict]:
    return [
        _campaign("c-401", "Summer Drop — VIP Early Access", "حراج تابستان — دسترسی زودهنگام ویژه",
                  "broadcast", "sent", agent="nova", segment="vip", recipients=25000,
                  open_r=0.626, click=0.184, reply=0.021, revenue=84200, updated_min=190, seed=3,
                  subj_en="Your early access starts now", subj_fa="دسترسی زودهنگام شما از همین حالا"),
        _campaign("c-398", "Weekly Digest #42", "خلاصهٔ هفتگی #۴۲", "broadcast", "sent",
                  agent="nova", segment="newsletter", recipients=34100, open_r=0.394, click=0.061,
                  revenue=9800, updated_min=1500, seed=5,
                  subj_en="Five things worth your Tuesday", subj_fa="پنج چیز که ارزش سه‌شنبه‌تان را دارد"),
        _campaign("c-402", "Trial Day 3 — Activation Nudge", "روز سوم آزمایشی — یادآوری فعال‌سازی",
                  "drip", "running", agent="nova", segment="trial", recipients=12400, sent=8210,
                  open_r=0.481, click=0.142, reply=0.034, revenue=21400, updated_min=22, seed=9,
                  subj_en="Two clicks from your first campaign", subj_fa="دو کلیک تا اولین کمپین شما"),
        _campaign("c-405", "Win-back — We miss you", "بازگرداندن — دلمان برایتان تنگ شده",
                  "agent", "running", agent="vega", segment="churn", recipients=8600, sent=3120,
                  open_r=0.213, click=0.044, revenue=6400, updated_min=48, seed=13,
                  subj_en="A quiet 20% while you decide", subj_fa="یک ۲۰٪ بی‌سروصدا تا تصمیم بگیرید"),
        _campaign("c-407", "Subject Line Test — Launch", "تست موضوع — معرفی محصول", "abtest",
                  "running", agent="orion", segment="all", recipients=48200, sent=9600,
                  open_r=0.442, click=0.101, revenue=12900, updated_min=9, seed=17,
                  subj_en="Variant A vs B", subj_fa="نسخهٔ الف در برابر ب"),
        _campaign("c-409", "Black Friday Warm-up", "گرم‌کردن بلک‌فرایدی", "broadcast", "scheduled",
                  agent="nova", segment="vip", recipients=25000, sent=0, open_r=0, click=0,
                  reply=0, unsub=0, bounce=0, deliv=0, updated_min=180,
                  scheduled=ago_iso(days=-3), seed=19,
                  subj_en="Something is coming on Friday", subj_fa="جمعه یک اتفاقی می‌افتد"),
        _campaign("c-410", "Onboarding Sequence v3", "مسیر آشناسازی نسخهٔ ۳", "drip", "draft",
                  agent="nova", segment="trial", recipients=12400, sent=0, open_r=0, click=0,
                  reply=0, unsub=0, bounce=0, deliv=0, updated_min=70, seed=23,
                  subj_en="Welcome aboard", subj_fa="به جمع ما خوش آمدید"),
        _campaign("c-393", "Receipt & Shipping", "رسید و ارسال", "transactional", "running",
                  agent="atlas", segment="all", recipients=48200, sent=14820, open_r=0.712,
                  click=0.221, deliv=0.994, bounce=0.004, revenue=0, updated_min=2, seed=29,
                  subj_en="Your order is on the way", subj_fa="سفارش شما در راه است"),
        _campaign("c-388", "Re-engagement Q2", "بازفعال‌سازی فصل دوم", "agent", "paused",
                  agent="vega", segment="churn", recipients=8600, sent=2400, open_r=0.188,
                  click=0.031, updated_min=4000, seed=31,
                  subj_en="Still interested?", subj_fa="هنوز علاقه‌مندید؟"),
    ]


def _contacts() -> list[dict]:
    rng = random.Random(99)
    out = []
    for i in range(64):
        fi = int(rng.random() * len(FIRST))
        li = int(rng.random() * len(LAST))
        score = round(rng.random() * 100)
        roll = rng.random()
        status = "subscribed"
        if score <= 25:
            if roll > 0.9:
                status = "bounced"
            elif roll > 0.75:
                status = "unsubscribed"
        src = SOURCES[int(rng.random() * len(SOURCES))]
        domain = ["acme.io", "mail.com", "northwind.co", "lumen.dev"][int(rng.random() * 4)]
        out.append(dict(
            id=f"p-{100 + i}",
            name_en=f"{FIRST[fi]} {LAST[li]}", name_fa=f"{FIRST_FA[fi]} {LAST_FA[li]}",
            email=f"{FIRST[fi].lower()}.{LAST[li].lower()}{i}@{domain}",
            status=status, score=score, ltv=round(rng.random() * 4200, 2),
            orders=int(rng.random() * 9),
            tags=[t for t in TAGS if rng.random() > 0.72][:3],
            source_id=src[0], source_en=src[1], source_fa=src[2],
            country=["US", "IR", "DE", "FR", "AE", "UK"][int(rng.random() * 6)],
            device="mobile" if rng.random() > 0.55 else "desktop",
            last_open_at=ago_iso(minutes=int(rng.random() * 40000)),
            created_at=ago_iso(minutes=int(rng.random() * 400000)),
        ))
    return out


def _threads() -> list[dict]:
    return [
        dict(id="t-1", from_en="Elena Rossi", from_fa="الینا روسی", email="elena.rossi@northwind.co",
             subject_en="Re: Your early access starts now", subject_fa="پاسخ: دسترسی زودهنگام شما از همین حالا",
             preview_en="This looks great — can you tell me whether the enterprise tier includes the audit log?",
             preview_fa="خیلی خوب به نظر می‌رسد — می‌شود بگویید پلن سازمانی گزارش ممیزی دارد یا نه؟",
             draft_en="Hi Elena — yes, the audit log ships with every Enterprise workspace and retains "
                      "24 months of events by default. Happy to walk you through it on a call this week.",
             draft_fa="سلام الینا — بله، گزارش ممیزی روی همهٔ فضاهای کاری سازمانی فعال است و به‌صورت "
                      "پیش‌فرض ۲۴ ماه رویداد را نگه می‌دارد. اگر بخواهید همین هفته در یک تماس نشانتان می‌دهم.",
             intent="question", sentiment=0.62, handled=0, agent_id="echo", received_at=ago_iso(minutes=18)),
        dict(id="t-2", from_en="Marco Lund", from_fa="مارکو لوند", email="marco@lumen.dev",
             subject_en="Re: Two clicks from your first campaign", subject_fa="پاسخ: دو کلیک تا اولین کمپین شما",
             preview_en="Interested. What does onboarding look like for a team of 20?",
             preview_fa="علاقه‌مندم. آشناسازی برای تیم ۲۰ نفره چطور است؟",
             draft_en="Hi Marco — for a team of 20 we run a 45-minute setup session, migrate your "
                      "existing lists, and leave you with two agents already configured. Would Thursday suit?",
             draft_fa="سلام مارکو — برای تیم ۲۰ نفره یک جلسهٔ ۴۵ دقیقه‌ای راه‌اندازی داریم، لیست‌های "
                      "فعلی‌تان را منتقل می‌کنیم و دو ایجنت آماده تحویلتان می‌دهیم. پنج‌شنبه مناسب است؟",
             intent="interested", sentiment=0.81, handled=0, agent_id="echo", received_at=ago_iso(minutes=52)),
        dict(id="t-3", from_en="Reza Sadeghi", from_fa="رضا صادقی", email="reza.sadeghi@acme.io",
             subject_en="Re: A quiet 20% while you decide", subject_fa="پاسخ: یک ۲۰٪ بی‌سروصدا تا تصمیم بگیرید",
             preview_en="Please remove me from this list.", preview_fa="لطفاً من را از این لیست حذف کنید.",
             draft_en="Done — you have been removed and will not receive further campaigns. Sorry for the noise.",
             draft_fa="انجام شد — حذف شدید و دیگر کمپینی دریافت نمی‌کنید. بابت مزاحمت پوزش می‌خواهیم.",
             intent="unsubscribe", sentiment=0.18, handled=1, agent_id="echo", received_at=ago_iso(minutes=96)),
        dict(id="t-4", from_en="Yasmin Haddad", from_fa="یاسمین حداد", email="yasmin.haddad@mail.com",
             subject_en="Re: Five things worth your Tuesday", subject_fa="پاسخ: پنج چیز که ارزش سه‌شنبه‌تان را دارد",
             preview_en="The pricing page 404s on mobile.", preview_fa="صفحهٔ قیمت‌ها روی موبایل ۴۰۴ می‌دهد.",
             draft_en="Thank you for flagging it — the mobile pricing route is fixed and live. Here is the working link.",
             draft_fa="ممنون که گفتید — مسیر موبایل صفحهٔ قیمت‌ها اصلاح شد و بالا آمد. این هم لینک سالم.",
             intent="objection", sentiment=0.34, handled=0, agent_id="echo", received_at=ago_iso(minutes=140)),
        dict(id="t-5", from_en="Daniel Blake", from_fa="دانیال بلیک", email="daniel.blake@acme.io",
             subject_en="Automatic reply: Out of office", subject_fa="پاسخ خودکار: خارج از دفتر",
             preview_en="I am away until the 14th with limited access to email.",
             preview_fa="تا چهاردهم نیستم و دسترسی محدودی به ایمیل دارم.",
             draft_en="Suppressed until the 14th, then re-enrolled automatically.",
             draft_fa="تا چهاردهم متوقف شد و بعد خودکار دوباره وارد مسیر می‌شود.",
             intent="ooo", sentiment=0.5, handled=1, agent_id="echo", received_at=ago_iso(minutes=220)),
    ]


# Every integration the panel can offer. Which of them are actually CONNECTED is
# per-installation data; this list is not.
_INTEGRATION_CATALOG = [
    ("shopify", "Shopify", "ecommerce", 1, "🛍️", "Orders, carts and customers", "سفارش‌ها، سبدها و مشتریان"),
    ("woo", "WooCommerce", "ecommerce", 0, "🧺", "Sync your WordPress store", "همگام‌سازی فروشگاه وردپرسی"),
    ("stripe", "Stripe", "ecommerce", 1, "💳", "Revenue and subscription events", "رویدادهای درآمد و اشتراک"),
    ("hubspot", "HubSpot", "crm", 1, "🧲", "Two-way contact sync", "همگام‌سازی دوطرفهٔ مخاطبان"),
    ("salesforce", "Salesforce", "crm", 0, "☁️", "Leads and opportunities", "سرنخ‌ها و فرصت‌ها"),
    ("segment", "Segment", "data", 1, "🔀", "Event pipeline in", "خط لولهٔ رویداد ورودی"),
    ("bigquery", "BigQuery", "data", 0, "🗄️", "Warehouse export", "خروجی به انبار داده"),
    ("snowflake", "Snowflake", "data", 0, "❄️", "Reverse ETL audiences", "مخاطبان از طریق ETL معکوس"),
    ("slack", "Slack", "messaging", 1, "💬", "Alerts and approvals", "هشدارها و تأییدها"),
    ("telegram", "Telegram", "messaging", 0, "✈️", "Agent notifications", "اعلان‌های ایجنت"),
    ("meta", "Meta Ads", "ads", 0, "📣", "Custom audience sync", "همگام‌سازی مخاطب سفارشی"),
    ("google", "Google Ads", "ads", 1, "🎯", "Customer match lists", "لیست‌های تطبیق مشتری"),
    ("anthropic", "Anthropic", "ai", 1, "🧠", "Claude models for every agent", "مدل‌های کلاد برای همهٔ ایجنت‌ها"),
    ("openai", "OpenAI", "ai", 0, "🌀", "Alternate model provider", "ارائه‌دهندهٔ جایگزین مدل"),
]


def _seed_rows() -> None:
    now = iso()

    # ---- workspace ----
    db.insert("workspaces", dict(
        id="ws-acme", name="Acme Inc", plan="scale", timezone="Asia/Tehran", default_lang="en",
        from_name="Acme", from_email="hello@mail.acme.io", reply_to="replies@mail.acme.io",
        footer="Acme Inc · 12 Main Street · Unsubscribe",
        throttle_per_hour=40000, quiet_hours=1, quiet_from="21:00", quiet_to="08:00",
        default_model="claude-opus-5", creativity=60, auto_approve=0, gdpr=1, retention_months=24,
        notif=db.dumps({"digest": True, "alerts": True, "agent": True, "billing": False}),
        created_at=now,
    ))

    # ---- users ----
    team = [
        ("u-1", "pouya@acme.io", "Pouya A.", "پویا الف.", "owner", "active", ago_iso(minutes=4)),
        ("u-2", "sara@acme.io", "Sara Ahmadi", "سارا احمدی", "admin", "active", ago_iso(minutes=90)),
        ("u-3", "noah@acme.io", "Noah Vance", "نوح ونس", "editor", "active", ago_iso(minutes=1400)),
        ("u-4", "mia@acme.io", "Mia Torres", "میا تورس", "analyst", "active", ago_iso(minutes=300)),
        ("u-5", "kian@acme.io", "Kian Farhadi", "کیان فرهادی", "viewer", "pending", None),
    ]
    demo_hash = hash_password(settings.demo_password)
    for uid, email, en, fa, role, status, active in team:
        db.insert("users", dict(
            id=uid, email=email, name_en=en, name_fa=fa, role=role,
            # every seeded account shares the demo password so any role can be
            # tried without creating users by hand
            password_hash=demo_hash if status == "active" else "",
            status=status, last_active_at=active, created_at=now,
        ))

    for a in _agents():
        a = dict(a)
        a["skills"] = db.dumps(a["skills"])
        a["tools"] = db.dumps(a["tools"])
        a["memory"] = db.dumps(a["memory"])
        a["sparkline"] = db.dumps(a["sparkline"])
        a["created_at"] = now
        db.insert("agents", a)

    for s in _segments():
        s = dict(s)
        s["rules"] = db.dumps(s["rules"])
        s["match_mode"] = "all"
        s["created_at"] = now
        db.insert("segments", s)

    for c in _campaigns():
        c = dict(c)
        c["trend"] = db.dumps(c["trend"])
        db.insert("campaigns", c)

    for c in _contacts():
        c = dict(c)
        c["tags"] = db.dumps(c["tags"])
        db.insert("contacts", c)

    templates = [
        ("tp-1", "Product Launch", "معرفی محصول", "promo", 42, "#7ba3cd"),
        ("tp-2", "Weekly Digest", "خلاصهٔ هفتگی", "newsletter", 118, "#8fd3a8"),
        ("tp-3", "Abandoned Cart", "سبد رهاشده", "lifecycle", 67, "#e2b872"),
        ("tp-4", "Welcome Series", "مجموعهٔ خوش‌آمد", "lifecycle", 91, "#b98cff"),
        ("tp-5", "Receipt", "رسید خرید", "transactional", 2400, "#57c7ff"),
        ("tp-6", "Event Invite", "دعوت به رویداد", "promo", 23, "#ff9d5c"),
        ("tp-7", "Win-back Offer", "پیشنهاد بازگشت", "lifecycle", 38, "#d68f9f"),
        ("tp-8", "Plain Announcement", "اعلان ساده", "newsletter", 14, "#9fd68f"),
    ]
    for tid, en, fa, cat, used, accent in templates:
        db.insert("templates", dict(id=tid, name_en=en, name_fa=fa, category=cat,
                                    used=used, accent=accent, created_at=now))

    journeys = [
        ("j-1", "Welcome & Activation", "خوش‌آمد و فعال‌سازی", "Contact created", "ساخته‌شدن مخاطب",
         "active", 12480, 8210, 31.4, "nova",
         [("email", "Welcome email", "ایمیل خوش‌آمد"), ("wait", "Wait 2 days", "۲ روز صبر"),
          ("branch", "Opened?", "باز کرد؟"), ("agent", "Agent picks follow-up", "ایجنت پیگیری را انتخاب کند"),
          ("email", "Activation nudge", "یادآوری فعال‌سازی"), ("goal", "First campaign sent", "اولین کمپین ارسال شد")]),
        ("j-2", "Abandoned Cart Recovery", "بازیابی سبد رهاشده", "Cart abandoned 1h", "رهاشدن سبد پس از ۱ ساعت",
         "active", 6420, 2180, 18.9, "nova",
         [("wait", "Wait 1 hour", "۱ ساعت صبر"), ("email", "Left something behind", "چیزی جا گذاشتید"),
          ("branch", "Purchased?", "خرید کرد؟"), ("email", "Offer 10%", "پیشنهاد ۱۰٪"),
          ("goal", "Order placed", "سفارش ثبت شد")]),
        ("j-3", "Churn Rescue", "نجات از ریزش", "Engagement score < 20", "امتیاز تعامل زیر ۲۰",
         "paused", 3110, 640, 9.2, "vega",
         [("agent", "Diagnose why", "تشخیص علت"), ("email", "Personal check-in", "پیگیری شخصی"),
          ("wait", "Wait 5 days", "۵ روز صبر"), ("branch", "Replied?", "پاسخ داد؟"),
          ("tag", "Move to dormant", "انتقال به خاموش")]),
        ("j-4", "Post-purchase Delight", "لذت پس از خرید", "Order completed", "تکمیل سفارش",
         "active", 21400, 19800, 44.1, "echo",
         [("email", "Thank you", "سپاسگزاریم"), ("wait", "Wait 7 days", "۷ روز صبر"),
          ("email", "How did we do?", "چطور بودیم؟"), ("webhook", "Push review to CRM", "ارسال نظر به CRM")]),
    ]
    for jid, en, fa, ten, tfa, status, enrolled, completed, conv, agent, steps in journeys:
        db.insert("journeys", dict(id=jid, name_en=en, name_fa=fa, trigger_en=ten, trigger_fa=tfa,
                                    status=status, enrolled=enrolled, completed=completed,
                                    conversion=conv, agent_id=agent, created_at=now))
        for idx, (stype, sen, sfa) in enumerate(steps):
            db.insert("journey_steps", dict(id=f"{jid}-s{idx+1}", journey_id=jid, position=idx,
                                             type=stype, label_en=sen, label_fa=sfa))

    for t in _threads():
        db.insert("threads", t)

    experiments = [
        ("x-1", "Subject: curiosity vs benefit", "موضوع: کنجکاوی در برابر منفعت", "running", "openRate", 87.4,
         [("a", "A", "Something is coming on Friday", "جمعه یک اتفاقی می‌افتد", 50, 4800, 44.2, 0),
          ("b", "B", "Save 30% this Friday", "جمعه ۳۰٪ صرفه‌جویی کنید", 50, 4800, 48.9, 1)]),
        ("x-2", "CTA colour & copy", "رنگ و متن دکمه", "called", "clickRate", 99.1,
         [("a", "A", "Shop the drop", "دیدن محصولات", 33, 8200, 8.1, 0),
          ("b", "B", "See what is new", "ببینید چه خبر است", 33, 8200, 11.4, 1),
          ("c", "C", "Take me there", "ببر آنجا", 34, 8400, 9.2, 0)]),
        ("x-3", "Send time: 9am vs agent-picked", "زمان ارسال: ۹ صبح در برابر انتخاب ایجنت", "running", "openRate", 64.2,
         [("a", "A", "Fixed 09:00 local", "ثابت ۰۹:۰۰ محلی", 50, 3100, 37.8, 0),
          ("b", "B", "Agent-optimised", "بهینه‌شده توسط ایجنت", 50, 3100, 41.1, 1)]),
    ]
    for xid, en, fa, status, metric, conf, variants in experiments:
        db.insert("experiments", dict(id=xid, name_en=en, name_fa=fa, status=status, metric=metric,
                                       confidence=conf, auto_promote=1, created_at=now))
        for vid, label, ven, vfa, split, sent, rate, winner in variants:
            db.insert("experiment_variants", dict(id=f"{xid}-{vid}", experiment_id=xid, label=label,
                                                   text_en=ven, text_fa=vfa, split=split, sent=sent,
                                                   rate=rate, winner=winner))

    rng = random.Random(2024)
    reasons = ["unsub", "bounce", "complaint", "manual"]
    for i in range(22):
        local = ["old", "test", "noreply", "info", "admin", "hello"][int(rng.random() * 6)]
        host = ["mail.com", "acme.io", "example.org"][int(rng.random() * 3)]
        db.insert("suppression", dict(id=f"s-{i}", email=f"{local}{int(rng.random()*900)}-{i}@{host}",
                                       reason=reasons[int(rng.random() * 4)],
                                       created_at=ago_iso(minutes=int(rng.random() * 200000))))

    domains = [
        ("d-1", "mail.acme.io", "verified", 1, 1, 1, 0, "198.51.100.24", 1, 94, [
            ("TXT", "mail.acme.io", "v=spf1 include:mailpilot.net ~all", 1),
            ("CNAME", "mp1._domainkey.mail.acme.io", "mp1.dkim.mailpilot.net", 1),
            ("TXT", "_dmarc.mail.acme.io", "v=DMARC1; p=quarantine; rua=mailto:dmarc@acme.io", 1)]),
        ("d-2", "news.acme.io", "unverified", 1, 0, 0, 0, "shared", 0, 71, [
            ("TXT", "news.acme.io", "v=spf1 include:mailpilot.net ~all", 1),
            ("CNAME", "mp1._domainkey.news.acme.io", "mp1.dkim.mailpilot.net", 0),
            ("TXT", "_dmarc.news.acme.io", "v=DMARC1; p=none", 0)]),
    ]
    for did, dom, status, spf, dkim, dmarc, bimi, ip, ded, rep, records in domains:
        db.insert("domains", dict(id=did, domain=dom, status=status, spf=spf, dkim=dkim,
                                   dmarc=dmarc, bimi=bimi, ip=ip, dedicated=ded,
                                   reputation=rep, created_at=now))
        for i, (rtype, host, value, ok) in enumerate(records):
            db.insert("dns_records", dict(id=f"{did}-r{i}", domain_id=did, type=rtype,
                                           host=host, value=value, ok=ok))

    for iid, name, cat, on, emoji, den, dfa in _INTEGRATION_CATALOG:
        db.insert("integrations", dict(id=iid, name=name, category=cat, enabled=on,
                                        emoji=emoji, desc_en=den, desc_fa=dfa))

    kb = [
        ("kb-1", "acme.io — full site", "acme.io — کل سایت", "web", 1840, "indexed", 2400),
        ("kb-2", "Product catalogue.csv", "کاتالوگ محصولات.csv", "file", 620, "indexed", 6000),
        ("kb-3", "Brand guidelines.pdf", "راهنمای برند.pdf", "file", 88, "indexed", 9000),
        ("kb-4", "Support macros (Zendesk)", "ماکروهای پشتیبانی (زندسک)", "app", 240, "indexing", 12),
        ("kb-5", "Past campaigns (2023–2025)", "کمپین‌های گذشته (۲۰۲۳–۲۰۲۵)", "internal", 3120, "indexed", 40000),
    ]
    for kid, en, fa, ktype, chunks, status, mins in kb:
        db.insert("kb_sources", dict(id=kid, name_en=en, name_fa=fa, type=ktype, chunks=chunks,
                                      status=status, created_at=ago_iso(minutes=mins)))

    db.insert("brand_voice", dict(
        id=1,
        axes=db.dumps([{"id": "formal", "value": 38}, {"id": "warm", "value": 72},
                       {"id": "brief", "value": 64}, {"id": "bold", "value": 45}]),
        banned=db.dumps(["free!!!", "act now", "limited time only", "dear customer"]),
        notes="We always write in second person, avoid jargon, and never pressure the reader.",
    ))

    keys = [
        ("k-1", "Production server", "سرور تولید", "mp_live_9f2a", ["campaigns:write", "contacts:rw"], 12),
        ("k-2", "Analytics reader", "خوانندهٔ تحلیل", "mp_live_41cd", ["analytics:read"], 2400),
        ("k-3", "Staging", "محیط آزمایشی", "mp_test_77be", ["*"], 60 * 24 * 12),
    ]
    for kid, en, fa, prefix, scopes, mins in keys:
        # A seeded key has a deterministic plaintext so the docs and the test
        # suite can use it; a real one is generated and shown once.
        plaintext = f"{prefix}_seeded_demo_key"
        db.insert("api_keys", dict(id=kid, name_en=en, name_fa=fa, prefix=prefix,
                                    token_hash=hash_api_key(plaintext), scopes=db.dumps(scopes),
                                    last_used_at=ago_iso(minutes=mins), created_at=now))

    hooks = [
        ("w-1", "https://api.acme.io/hooks/mailpilot",
         ["email.delivered", "email.opened", "email.clicked"], 1, 99.8),
        ("w-2", "https://ops.acme.io/agent-events", ["agent.action", "agent.escalation"], 1, 100.0),
        ("w-3", "https://legacy.acme.io/mail", ["email.bounced"], 0, 42.1),
    ]
    for wid, url, events, on, ok in hooks:
        db.insert("webhooks", dict(id=wid, url=url, events=db.dumps(events), enabled=on,
                                    ok_rate=ok, created_at=now))

    activity = [
        ("agent", "nova", "rewrote 1,240 subject lines", "۱٬۲۴۰ موضوع را بازنویسی کرد", "c-402", "info", 4),
        ("agent", "atlas", "throttled sending to Yahoo", "سرعت ارسال به یاهو را کم کرد", "news.acme.io", "warn", 11),
        ("human", "u-2", "approved the win-back draft", "پیش‌نویس بازگرداندن را تأیید کرد", "c-405", "good", 26),
        ("agent", "orion", "called variant B the winner", "نسخهٔ ب را برنده اعلام کرد", "x-2", "good", 41),
        ("agent", "echo", "answered 18 replies autonomously", "۱۸ پاسخ را خودکار جواب داد", "inbox", "info", 58),
        ("system", "system", "DKIM verified", "DKIM تأیید شد", "mail.acme.io", "good", 120),
        ("agent", "vega", "flagged 640 contacts as churn risk", "۶۴۰ مخاطب را در خطر ریزش علامت زد", "churn", "warn", 190),
        ("human", "u-1", "rotated the production API key", "کلید API تولید را چرخاند", "k-1", "info", 320),
        ("system", "system", "nightly list hygiene removed 84 addresses",
         "پاک‌سازی شبانه ۸۴ آدرس را حذف کرد", "suppression", "info", 500),
        ("agent", "nova", "scheduled Black Friday warm-up", "گرم‌کردن بلک‌فرایدی را زمان‌بندی کرد", "c-409", "info", 700),
    ]
    for i, (kind, actor, en, fa, target, tone, mins) in enumerate(activity):
        db.insert("activity", dict(id=f"a-{i+1}", kind=kind, actor=actor, action_en=en,
                                    action_fa=fa, target=target, tone=tone, ip="",
                                    created_at=ago_iso(minutes=mins)))

    notifs = [
        ("n-1", "warn", "ATLAS wants approval", "اطلس منتظر تأیید است",
         "Reduce Yahoo volume by 40% for 24h", "کاهش ۴۰٪ حجم یاهو برای ۲۴ ساعت", 1, 9),
        ("n-2", "good", "Experiment called", "آزمایش داوری شد",
         "CTA colour & copy — variant B wins", "رنگ و متن دکمه — نسخهٔ ب برنده شد", 1, 41),
        ("n-3", "info", "Summer Drop finished sending", "ارسال حراج تابستان تمام شد",
         "25,000 delivered · 62.6% open", "۲۵٬۰۰۰ تحویل · ۶۲٫۶٪ بازشدن", 0, 190),
        ("n-4", "bad", "DKIM missing", "DKIM ناقص است",
         "news.acme.io is sending unsigned", "news.acme.io بدون امضا ارسال می‌کند", 0, 600),
    ]
    for nid, tone, ten, tfa, ben, bfa, unread, mins in notifs:
        db.insert("notifications", dict(id=nid, tone=tone, title_en=ten, title_fa=tfa,
                                         body_en=ben, body_fa=bfa, unread=unread,
                                         created_at=ago_iso(minutes=mins)))

    recos = [
        ("r-1", "nova", 12.4, "low", "Move the VIP send to 08:40 local", "ارسال ویژه را به ۰۸:۴۰ محلی ببرید",
         "Opens for this segment peak 40 minutes earlier than the fixed 09:20 slot you are using.",
         "اوج بازشدن این بخش ۴۰ دقیقه زودتر از ساعت ثابت ۰۹:۲۰ فعلی است."),
        ("r-2", "atlas", 8.1, "low", "Finish DKIM on news.acme.io", "DKIM دامنهٔ news.acme.io را کامل کنید",
         "One CNAME is missing. Until it resolves, Outlook is filing 6% of that domain in Promotions.",
         "یک رکورد CNAME کم است. تا وقتی حل نشود، اوت‌لوک ۶٪ از این دامنه را در تبلیغات می‌گذارد."),
        ("r-3", "vega", 6.8, "medium", "Split \"All Contacts\" by engagement",
         "«همهٔ مخاطبان» را بر اساس تعامل تقسیم کنید",
         "18,400 addresses have not opened in 120 days and are dragging the whole domain reputation down.",
         "۱۸٬۴۰۰ آدرس ۱۲۰ روز است چیزی باز نکرده‌اند و اعتبار کل دامنه را پایین می‌کشند."),
        ("r-4", "orion", 4.2, "low", "Promote variant B on the launch test",
         "نسخهٔ ب را در تست معرفی ارتقا دهید",
         "Confidence crossed 95% two hours ago. The remaining 38,600 recipients should get B.",
         "اطمینان دو ساعت پیش از ۹۵٪ رد شد. ۳۸٬۶۰۰ گیرندهٔ باقی‌مانده باید نسخهٔ ب را بگیرند."),
    ]
    for rid, agent, lift, effort, ten, tfa, ben, bfa in recos:
        db.insert("recommendations", dict(id=rid, agent_id=agent, lift=lift, effort=effort,
                                           title_en=ten, title_fa=tfa, body_en=ben, body_fa=bfa,
                                           state="open", created_at=now))

    live = [
        ("opened", "ava.reed@acme.io", 0.2), ("clicked", "marco@lumen.dev", 0.6),
        ("delivered", "nina.rossi@mail.com", 1.1), ("replied", "elena.rossi@northwind.co", 1.8),
        ("opened", "kian.sadeghi@acme.io", 2.4), ("bounced", "old441@example.org", 3.2),
        ("converted", "yasmin.haddad@mail.com", 4.0), ("unsubscribed", "test902@mail.com", 5.1),
    ]
    for i, (etype, email, mins) in enumerate(live):
        db.insert("events", dict(id=f"e-{i+1}", type=etype, email=email, campaign_id="c-401",
                                  created_at=ago_iso(minutes=mins)))

    for i, (amount, mins) in enumerate([(890, 3), (890, 33), (640, 63), (640, 94)]):
        db.insert("invoices", dict(id=f"in-{2044 - i * 33}", amount=amount, status="paid",
                                    created_at=ago_iso(days=mins)))

    db.insert("usage_counters", dict(id=1, emails_used=184200, emails_limit=500000,
                                      credits_used=41200, credits_limit=120000,
                                      contacts_limit=100000, renews_at=ago_iso(days=-12)))


def ensure_default_segment() -> bool:
    """Guarantee there is at least one audience to send to.

    A group is a rule, so the first one cannot be derived from the data — but
    "everyone" is always correct, and without at least one group the product
    cannot send at all. An install that reached this state kept refusing every
    send with "give the campaign an audience", which is true and useless when
    there is no audience to give it.

    Only ever creates when there are NO groups. A deployment that has built its
    own is left alone.
    """
    if db.scalar("SELECT COUNT(*) FROM segments", default=0):
        return False

    lang = (deployment.get().get("default_lang") or "en")
    with db.transaction():
        db.insert("segments", {
            "id": "seg-everyone",
            "name_en": "Everyone", "name_fa": "همه",
            "emoji": "🌍", "tint": "linear-gradient(140deg,#7ba3cd,#274563)",
            "size": 0, "growth": 0, "open_rate": 0, "live": 1,
            # the explicit form: no rules AND a match mode that says so, which
            # is what stops an unfinished group meaning the same thing
            "match_mode": "everyone", "rules": db.dumps([]),
            "created_at": iso(),
        })
        log(kind="system", actor="system",
            action_en="created the Everyone group so the panel can send",
            action_fa="گروه «همه» ساخته شد تا پنل بتواند بفرستد",
            target="seg-everyone", tone="info")
    return True


def bootstrap(owner_email: str = "", owner_password: str = "") -> bool:
    """The minimum a usable, EMPTY installation needs.

    No campaigns, no contacts, no invented history — the customer's first
    screen is their own empty panel, not a showroom. Returns True if it wrote.
    """
    db.init_db()
    if db.scalar("SELECT COUNT(*) FROM workspaces", default=0):
        return False

    now = iso()
    email = (owner_email or settings.demo_email or "owner@example.com").strip().lower()
    secret = owner_password or settings.demo_password

    with db.transaction():
        db.insert("workspaces", dict(
            id="ws-1", name="", plan="scale", timezone="UTC", default_lang="en",
            from_name="", from_email="", reply_to="", footer="",
            throttle_per_hour=40000, quiet_hours=1, quiet_from="21:00", quiet_to="08:00",
            default_model="gpt-4o-mini", creativity=60, auto_approve=0, gdpr=1,
            retention_months=24,
            notif=db.dumps({"digest": True, "alerts": True, "agent": True, "billing": False}),
            created_at=now,
        ))
        db.insert("users", dict(
            id="u-1", email=email, name_en="Owner", name_fa="مالک", role="owner",
            password_hash=hash_password(secret), status="active",
            last_active_at=now, created_at=now,
        ))
        # The catalogue is structure, not data: it is the list of things that
        # CAN be connected, and every one of them starts disconnected.
        for iid, name, cat, _on, emoji, den, dfa in _INTEGRATION_CATALOG:
            db.insert("integrations", dict(id=iid, name=name, category=cat, enabled=0,
                                            emoji=emoji, desc_en=den, desc_fa=dfa))
        db.insert("brand_voice", dict(
            id=1,
            axes=db.dumps([{"id": "formal", "value": 50}, {"id": "warm", "value": 50},
                           {"id": "brief", "value": 50}, {"id": "bold", "value": 50}]),
            banned=db.dumps([]),
            notes="",
        ))
        db.insert("usage_counters", dict(id=1, emails_used=0, emails_limit=500000,
                                          credits_used=0, credits_limit=120000,
                                          contacts_limit=100000, renews_at=ago_iso(days=-30)))
    return True


def seed(force: bool = False) -> bool:
    """Populate an empty database. Returns True if it actually wrote anything."""
    db.init_db()
    already = db.scalar("SELECT COUNT(*) FROM workspaces", default=0)
    if already and not force:
        return False
    # reset_db() drops every table and calls init_db() again, both of which
    # commit — so it cannot run INSIDE a transaction. Nesting it here raised
    # "cannot commit - no transaction is active" the moment seed(force=True)
    # was called on a database that already had rows in it.
    if force and already:
        db.reset_db()
    with db.transaction():
        _seed_rows()
    return True
