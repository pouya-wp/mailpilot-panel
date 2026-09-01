"""Making model-written HTML safe to preview and safe to send.

Two different problems live here, and they are not the same problem.

SAFETY. The HTML in a template comes from a language model, and later it goes
into an iframe in the operator's browser. A model that has been talked into
emitting `<script>` or an `onerror=` attribute would be running code inside the
panel. The preview iframe is sandboxed as well, but a sandbox is the second
line, not the first: anything that could execute is removed here, before it is
ever stored.

DELIVERABILITY. Email clients are not browsers. Gmail strips `<style>` blocks,
Outlook renders through Word, and almost nothing supports flexbox or grid. So
the generator is told to write table-based layout with inline styles, and this
module checks that it did — an operator should be told their template will
break in Outlook before they send it to their whole list, not after.

Written against the stdlib `html.parser` rather than a sanitiser dependency,
matching the rest of this backend.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

#: Tags that survive. Everything an email template legitimately needs, and
#: nothing that can execute or fetch.
ALLOWED_TAGS = {
    "html", "head", "body", "title", "meta", "style",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "div", "span", "p", "a", "img", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "small", "center",
    "ul", "ol", "li", "blockquote", "font",
}

#: Tags whose CONTENT is dropped as well as the tag.
VOID_CONTENT = {"script", "iframe", "object", "embed", "applet", "form", "svg", "math"}

ALLOWED_ATTRS = {
    "href", "src", "alt", "title", "width", "height", "align", "valign",
    "style", "class", "id", "border", "cellpadding", "cellspacing", "bgcolor",
    "colspan", "rowspan", "role", "target", "dir", "lang", "charset", "content",
    "name", "type",
}

SELF_CLOSING = {"img", "br", "hr", "meta"}

#: `javascript:` and friends, however they have been spelled.
_BAD_URL = re.compile(r"^\s*(javascript|vbscript|data:text/html|file)\s*:", re.I)
_EXPRESSION = re.compile(r"expression\s*\(|url\s*\(\s*['\"]?\s*javascript:", re.I)


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0

    # ---- tags
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_CONTENT:
            self._skip_depth += 1
            return
        if self._skip_depth or tag not in ALLOWED_TAGS:
            return
        self.out.append(f"<{tag}{self._attrs(attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth or tag in VOID_CONTENT or tag not in ALLOWED_TAGS:
            return
        self.out.append(f"<{tag}{self._attrs(attrs)} />")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or tag not in ALLOWED_TAGS or tag in SELF_CLOSING:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.out.append(data)

    # ---- attributes
    def _attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        kept: list[str] = []
        for name, value in attrs:
            name = (name or "").lower()
            # every `on*` handler, in one rule
            if name.startswith("on") or name not in ALLOWED_ATTRS:
                continue
            value = value or ""
            if name in {"href", "src"} and _BAD_URL.match(value):
                continue
            if name == "style" and _EXPRESSION.search(value):
                continue
            kept.append(f' {name}="{_quote(value)}"')
        return "".join(kept)


def _quote(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def sanitize(html: str) -> str:
    """Strip anything that could execute. Always run before storing."""
    cleaner = _Cleaner()
    cleaner.feed(html or "")
    cleaner.close()
    return "".join(cleaner.out).strip()


#: What breaks in real mail clients, checked after the model has written.
def lint(html: str) -> list[dict[str, str]]:
    """Warnings an operator should see BEFORE sending to their whole list.

    Not errors — a template that trips all of these still sends. But "this will
    collapse in Outlook" is worth knowing while it is still a draft.
    """
    issues: list[dict[str, str]] = []
    low = (html or "").lower()

    def add(key: str, en: str, fa: str, tone: str = "warn") -> None:
        issues.append({"id": key, "tone": tone, "en": en, "fa": fa})

    if "display:flex" in low.replace(" ", "") or "display:grid" in low.replace(" ", ""):
        add("layout", "Uses flexbox or grid, which Outlook ignores — the layout will collapse.",
            "از flexbox یا grid استفاده شده که اوت‌لوک آن را نادیده می‌گیرد و چیدمان به‌هم می‌ریزد.", "bad")
    if "<table" not in low:
        add("no-table", "No table layout. Most clients need tables for reliable columns.",
            "چیدمان جدولی ندارد. بیشتر کلاینت‌ها برای ستون‌بندی مطمئن به جدول نیاز دارند.")
    # A <style> block is not itself a fault — dark mode, a mobile media query
    # and a font import can only live there. It is a fault when the layout
    # DEPENDS on it, which shows up as markup with almost no inline styles.
    # Warning on every well-built template taught operators to ignore the list.
    if "<style" in low and low.count("style=") < 8:
        add("style-block",
            "Layout looks like it depends on the <style> block. Gmail strips these — "
            "put the layout in inline styles and keep the block for dark mode and "
            "the mobile media query.",
            "به‌نظر می‌رسد چیدمان به بلوک <style> وابسته است. جی‌میل آن را حذف می‌کند — "
            "چیدمان را درون‌خطی بگذارید و بلوک را برای حالت تیره و مدیا‌کوئری موبایل نگه دارید.")
    if re.search(r"<img(?![^>]*\balt=)", low):
        add("alt", "An image has no alt text, so it is blank when images are blocked.",
            "یکی از تصاویر متن جایگزین ندارد و با مسدود بودن تصاویر خالی دیده می‌شود.")
    if "{{unsubscribe}}" not in low and "unsubscribe" not in low and "لغو اشتراک" not in (html or ""):
        add("unsubscribe", "No unsubscribe link. Bulk mail needs one, legally and for reputation.",
            "لینک لغو اشتراک ندارد. ایمیل انبوه از نظر قانونی و اعتبار به آن نیاز دارد.", "bad")
    if len(html or "") > 102_400:
        add("size", "Over 100KB — Gmail clips messages this large.",
            "بیش از ۱۰۰ کیلوبایت است؛ جی‌میل پیام‌های این‌قدر بزرگ را می‌بُرد.")
    return issues


def used_assets(html: str) -> list[str]:
    """Asset ids this template references, so nothing in use is deleted."""
    return re.findall(r"/api/assets/([0-9a-zA-Z_-]{6,})", html or "")


#: Where a template makes room for the message the agent writes. A template
#: without this slot is a complete email in its own right and is used whole.
CONTENT_SLOT = "{{content}}"


def wrap_for_send(db_module, body_html: str, *, subject: str = "", cta: str = "") -> str:
    """Dress a written message in whatever house template is current.

    Called at SEND time, by every path that puts mail on the wire. That timing
    is the whole point: applying the template when a campaign was CREATED meant
    marking one "use for all" changed nothing that already existed, and nothing
    the agent made through its own tools.

    An already-complete document is returned untouched. Someone who pasted a
    finished email, or a template with no `{{content}}` slot, has said what they
    want and does not need it nested inside another one.
    """
    house = default_template(db_module)
    if house is None or not house["html"]:
        return body_html
    if CONTENT_SLOT not in house["html"]:
        return body_html
    if _is_whole_document(body_html):
        return body_html
    return house["html"].replace(CONTENT_SLOT, body_html).replace(
        "{{subject}}", _escape(subject)
    )


def _is_whole_document(html: str) -> bool:
    """Is this already an email rather than a message to put inside one?"""
    head = (html or "")[:400].lower()
    return "<html" in head or "<!doctype" in head or "<table" in head


def render(template_html: str, *, subject: str, body: list[str], cta: str = "") -> str:
    """Put a written message inside the house template.

    This is what makes "use for all" mean something. Before it, a template
    could be marked as the default and nothing ever read the flag — the agent
    wrote plain paragraphs and the branding the operator designed was never
    applied to anything.

    A template that contains `{{content}}` is a WRAPPER: header, footer, colours
    and unsubscribe line, with a hole where the message goes. One that does not
    is a finished email, and is returned unchanged rather than being mangled by
    a substitution it was not written for.
    """
    if not template_html or CONTENT_SLOT not in template_html:
        return template_html or ""

    paragraphs = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.7">{_escape(p)}</p>'
        for p in body
        if p and p.strip()
    )
    if cta:
        paragraphs += (
            '<p style="margin:24px 0 0">'
            f'<a href="{{{{cta_url}}}}" style="display:inline-block;padding:12px 24px;'
            f'text-decoration:none;border-radius:6px">{_escape(cta)}</a></p>'
        )

    out = template_html.replace(CONTENT_SLOT, paragraphs)
    # a template may also want the subject in a preheader or a heading
    return out.replace("{{subject}}", _escape(subject))


def _escape(text: str) -> str:
    """The agent's prose is TEXT going into HTML.

    It is model output, so it can contain an angle bracket or an ampersand that
    would otherwise change the document's structure — and the merge tags have
    to survive, since they are substituted per recipient much later.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def default_template(db_module) -> dict | None:
    """The template marked for every campaign, if there is one."""
    row = db_module.one("SELECT * FROM templates WHERE is_default = 1 LIMIT 1")
    if row is None:
        return None
    return {"id": row["id"], "name": row["name_en"], "html": row["html"] or ""}
