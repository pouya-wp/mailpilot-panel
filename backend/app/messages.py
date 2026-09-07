"""Server messages in the reader's language.

Every refusal this API makes was written as an English sentence at the
`raise` site, and the panel puts that sentence straight in front of the
customer. In a panel that is otherwise entirely Persian, a customer who
tried to add a domain twice was told "Domain already added" — the only
English on the screen, at the one moment they needed to understand
something.

WHY THE ENGLISH IS THE KEY. The alternative is a machine code at each of
the 147 raise sites, which is a large, mechanical, error-prone edit for
no gain the reader can see. Keying on the sentence means nothing at the
raise sites changes, and the sentences are the stable part: they are
written once and read by people.

The fragility of that — someone edits a message and the translation
silently stops matching — is answered by a test rather than by hope.
`test_messages.py` parses every `detail=` literal out of this package
and fails if one of them is missing here. A new message cannot ship
untranslated.

Anything not in the table falls through to English, which is exactly
what happened before, so a gap degrades rather than breaks.
"""

from __future__ import annotations

#: English sentence -> Persian. Keys must match the `detail=` literals
#: exactly; the test enforces that they all do.
FA: dict[str, str] = {
    # ---------------------------------------------------------- not found
    "Agent not found": "ایجنت پیدا نشد",
    "Campaign not found": "کمپین پیدا نشد",
    "Contact not found": "مخاطب پیدا نشد",
    "Domain not found": "دامنه پیدا نشد",
    "Experiment not found": "آزمایش پیدا نشد",
    "Integration not found": "یکپارچه‌سازی پیدا نشد",
    "Journey not found": "مسیر پیدا نشد",
    "Key not found": "کلید پیدا نشد",
    "Member not found": "کاربر پیدا نشد",
    "Notification not found": "اعلان پیدا نشد",
    "Recommendation not found": "پیشنهاد پیدا نشد",
    "Segment not found": "گروه پیدا نشد",
    "Source not found": "منبع پیدا نشد",
    "Step not found": "مرحله پیدا نشد",
    "Template not found": "قالب پیدا نشد",
    "Thread not found": "گفت‌وگو پیدا نشد",
    "User not found": "کاربر پیدا نشد",
    "Webhook not found": "وب‌هوک پیدا نشد",
    "Not found": "پیدا نشد",
    "No such conversation": "چنین گفت‌وگویی وجود ندارد",
    "No such endpoint": "چنین مقصدی وجود ندارد",
    "No such image": "چنین تصویری وجود ندارد",
    "No such template": "چنین قالبی وجود ندارد",
    # ------------------------------------------------------ already exists
    "A contact with that address already exists": "مخاطبی با این آدرس از قبل وجود دارد",
    "Domain already added": "این دامنه قبلاً اضافه شده",
    "Already suppressed": "قبلاً در فهرست تماس‌ممنوع است",
    "That address is already on the team": "این آدرس از قبل در تیم هست",
    # --------------------------------------------------------- sending
    "Give the campaign an audience before sending": "پیش از ارسال، برای کمپین یک گروه مخاطب انتخاب کنید",
    "Connect a Gmail account in Settings before sending": "پیش از ارسال، در تنظیمات یک حساب جیمیل وصل کنید",
    "No mailbox is connected": "هیچ صندوق ایمیلی وصل نیست",
    "There is nothing written to send yet": "هنوز چیزی برای ارسال نوشته نشده",
    "No Gmail account is connected": "هیچ حساب جیمیلی وصل نیست",
    "Google refused to renew access; reconnect the account":
        "گوگل دسترسی را تمدید نکرد؛ حساب را دوباره وصل کنید",
    "Google did not return a refresh token. Remove this app at "
    "myaccount.google.com/permissions and connect again.":
        "گوگل توکن تمدید نداد. این برنامه را در myaccount.google.com/permissions "
        "حذف کنید و دوباره وصل شوید.",
    "This campaign has no message in it yet. Write the email before sending it.":
        "این کمپین هنوز متنی ندارد. پیش از ارسال، ایمیل را بنویسید.",
    "This campaign has no subject line. An email without one is filtered as spam.":
        "این کمپین موضوع ندارد. ایمیل بدون موضوع به‌عنوان هرزنامه فیلتر می‌شود.",
    "A campaign that has finished sending cannot be edited":
        "کمپینی که ارسالش تمام شده دیگر قابل ویرایش نیست",
    "Only a paused campaign can be resumed": "فقط کمپین متوقف‌شده را می‌توان از سر گرفت",
    "Only a running campaign can be paused": "فقط کمپین در حال ارسال را می‌توان متوقف کرد",
    "Stop the campaign before deleting it": "پیش از حذف، کمپین را متوقف کنید",
    "Say when it should go out.": "بگویید چه زمانی ارسال شود.",
    "That address is on the suppression list": "این آدرس در فهرست تماس‌ممنوع است",
    "asked to be removed": "درخواست حذف داده است",
    # ----------------------------------------------------------- the agent
    "That agent is paused": "این ایجنت متوقف است",
    "Agent has used its daily action budget": "ایجنت سهم اقدام روزانه‌اش را مصرف کرده",
    "Tell the agent what you want": "به ایجنت بگویید چه می‌خواهید",
    "Describe the email you want": "ایمیلی که می‌خواهید را توصیف کنید",
    "Describe the audience you want": "مخاطبانی که می‌خواهید را توصیف کنید",
    "Ask a question to research": "پرسشی برای تحقیق بنویسید",
    "Give a place to look and a kind of business to look for.":
        "منطقه‌ای برای جست‌وجو و دسته‌ای از کسب‌وکار را مشخص کنید.",
    "No leads were chosen": "هیچ سرنخی انتخاب نشده",
    "That action does not match what was proposed. Ask again.":
        "این اقدام با آنچه پیشنهاد شده بود یکی نیست. دوباره بپرسید.",
    "A journey needs at least one step before it can run":
        "یک مسیر برای اجرا حداقل به یک مرحله نیاز دارد",
    "Experiment has no variants": "این آزمایش هیچ نسخه‌ای ندارد",
    # -------------------------------------------------------------- the AI
    "This installation has no AI key yet": "برای این نصب هنوز کلید هوش مصنوعی ثبت نشده",
    "No API key to check": "کلیدی برای بررسی وجود ندارد",
    "AI credit limit reached for this cycle. Top up or wait for the renewal.":
        "سقف اعتبار هوش مصنوعی این دوره پر شده. اعتبار اضافه کنید یا تا تمدید صبر کنید.",
    "The model returned no usable HTML": "مدل خروجی HTML قابل استفاده‌ای برنگرداند",
    "That template has no content yet": "این قالب هنوز محتوایی ندارد",
    # ------------------------------------------------------------ contacts
    "CSV must have an 'email' column": "فایل CSV باید ستونی به نام email داشته باشد",
    "No column headers found": "سرستونی پیدا نشد",
    "Say which column holds the email address": "مشخص کنید کدام ستون آدرس ایمیل است",
    "No contacts were selected": "هیچ مخاطبی انتخاب نشده",
    "Give a tag to add or remove": "برچسبی برای افزودن یا حذف مشخص کنید",
    "That is not an email address": "این یک آدرس ایمیل نیست",
    "That file could not be decoded": "این فایل قابل خواندن نبود",
    # -------------------------------------------------------------- images
    "That image could not be decoded": "این تصویر قابل خواندن نبود",
    "That image is empty": "این تصویر خالی است",
    "That image is used by a template. Remove it there first.":
        "این تصویر در یک قالب استفاده شده. اول آن را از قالب بردارید.",
    # ------------------------------------------------------------- domains
    "That does not look like a domain name": "این شبیه یک نام دامنه نیست",
    "Webhook endpoints must be HTTPS": "مقصد وب‌هوک باید HTTPS باشد",
    # -------------------------------------------------- accounts and access
    "Incorrect email or password": "ایمیل یا رمز عبور درست نیست",
    "Current password is incorrect": "رمز عبور فعلی درست نیست",
    "Refresh token is no longer valid": "این نشست دیگر معتبر نیست",
    "User no longer active": "این کاربر دیگر فعال نیست",
    "This endpoint requires a signed-in user, not an API key":
        "این مسیر به کاربر واردشده نیاز دارد، نه کلید API",
    "A workspace must keep at least one owner": "هر فضای کاری باید دست‌کم یک مالک داشته باشد",
    "Only an owner can promote someone to owner": "فقط مالک می‌تواند کسی را به مالک ارتقا دهد",
    "You cannot remove yourself": "خودتان را نمی‌توانید حذف کنید",
    # ------------------------------------------------------ brand information
    "Add a website address first": "اول نشانی وب‌سایت را وارد کنید",
    "Nothing to apply": "چیزی برای اعمال کردن نیست",
    "That is not a call to action this product offers":
        "این گزینه جزو اقدام‌هایی نیست که این محصول ارائه می‌دهد",
    "Reading your website needs web search, which is switched off for this "
    "installation. Turn it on in Setup — without it there is nothing to read "
    "and the answers would be invented.":
        "خواندن وب‌سایت شما به جست‌وجوی وب نیاز دارد و این قابلیت برای این نصب "
        "خاموش است. در بخش راه‌اندازی روشنش کنید — بدون آن چیزی برای خواندن "
        "نیست و پاسخ‌ها ساختگی می‌شوند.",
    # ----------------------------------------------------------- deployment
    "Add the Google OAuth client id and secret first":
        "اول شناسه و کلید OAuth گوگل را وارد کنید",
    "Workspace missing — run the seeder": "فضای کاری وجود ندارد — سیدر را اجرا کنید",
    "Nothing to save": "چیزی برای ذخیره نیست",
    # --------------------------------------- the long ones, which matter most
    # These are the messages that explain a refusal rather than just naming
    # it, so they are exactly the ones a reader most needs in their own
    # language.
    "I could not turn that into a rule. Try naming a field — how much they "
    "have spent, when they last opened something, a tag they carry.":
        "نتوانستم این را به یک قاعده تبدیل کنم. یک ویژگی را نام ببرید — مثلاً چقدر "
        "خرید کرده‌اند، آخرین بار کی چیزی باز کرده‌اند، یا چه برچسبی دارند.",
    "Research needs web search, which is switched off for this installation. "
    "Turn it on in Setup — without it the agent would be answering from "
    "memory, which for a question about real businesses means inventing them.":
        "تحقیق به جست‌وجوی وب نیاز دارد و این قابلیت برای این نصب خاموش است. در "
        "بخش راه‌اندازی روشنش کنید — بدون آن، ایجنت از حافظه‌اش جواب می‌دهد، که "
        "برای پرسشی دربارهٔ کسب‌وکارهای واقعی یعنی از خودش می‌سازد.",
    "That time has already passed, so the campaign would go out immediately "
    "rather than later. Pick a time in the future, or send it now on purpose.":
        "این زمان گذشته است، پس کمپین به‌جای بعداً همین حالا ارسال می‌شود. زمانی "
        "در آینده انتخاب کنید، یا اگر می‌خواهید همین حالا برود، عمداً ارسال فوری بزنید.",
    "There is no way for a reader to unsubscribe. Set the panel's public "
    "address, or a reply-to address, in Setup — bulk email without a working "
    "opt-out gets the sending account closed.":
        "هیچ راهی برای لغو اشتراک خواننده وجود ندارد. در بخش راه‌اندازی، آدرس عمومی "
        "پنل یا یک آدرس پاسخ تعیین کنید — ارسال انبوه بدون راه لغو اشتراک، به بسته "
        "شدن حساب ارسال‌کننده منجر می‌شود.",
    # ------------------------------------------------------------ requests
    "The request body did not validate": "اطلاعات ارسالی معتبر نبود",
    "action must be 'apply' or 'dismiss'": "مقدار action باید apply یا dismiss باشد",
    "role must be 'user' or 'agent'": "مقدار role باید user یا agent باشد",
}


def wants_persian(accept_language: str | None) -> bool:
    """Does this request want Persian?

    The panel sends its own chosen language, which is the language the
    reader picked in the interface — not a guess from the browser. Falls
    back to English for anything unrecognised, so an unusual header can
    never leave a reader with no message at all.
    """
    if not accept_language:
        return False
    # `fa`, `fa-IR`, `fa-IR,en;q=0.8` — only the first tag decides
    first = accept_language.split(",")[0].strip().lower()
    return first == "fa" or first.startswith("fa-")


def translate(detail: str, accept_language: str | None) -> str:
    """The message the reader should see."""
    if not isinstance(detail, str) or not wants_persian(accept_language):
        return detail
    return FA.get(detail, detail)
