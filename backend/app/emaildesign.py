"""How a generated email is allowed to look.

Split out of the route because it is a design brief, not routing, and because
"make it much more attractive" is a real instruction that needs a real answer
rather than three more sentences bolted onto a prompt.

The brief is opinionated on purpose. A model told "design a nice email" returns
the same centred 600px box with a blue button every time. Told what the type
scale is, how much air a section gets, that there is exactly one accent colour
and where it may appear, it produces something that looks designed — because
the decisions that make it look designed have been made.

TWO CONSTRAINTS THAT SHAPE EVERYTHING.

Email HTML is not web HTML. Outlook renders through Word, Gmail strips
`<style>`, and nothing supports flexbox or grid reliably. So: tables, inline
styles, and a VML fallback on the one button that matters. This is not
old-fashioned, it is the only thing that arrives intact.

Web fonts mostly do not load. Apple Mail and iOS honour them; Gmail and
Outlook do not, and fall back to whatever is next in the stack. Estedad is
therefore requested properly AND followed by a stack that looks right without
it — the design has to hold up in the client that ignores the font, because
that client is most of the audience.
"""

from __future__ import annotations

#: The face this product's mail is set in. Persian-first, and a Latin fallback
#: chain that keeps the metrics close where Estedad does not load.
FONT_STACK = (
    "Estedad, Vazirmatn, 'IRANSans', 'Segoe UI', Tahoma, "
    "-apple-system, BlinkMacSystemFont, Arial, sans-serif"
)

#: Both are needed. `<link>` is honoured by Apple Mail and iOS; the @font-face
#: inside a <style> block covers a few others. Gmail drops both and lands on
#: the fallback stack, which is why the stack is not an afterthought.
FONT_HEAD = (
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Estedad:wght@400;500;600;700&display=swap" rel="stylesheet">'
)


def brief(*, lang: str, palette: str = "", images: list[dict] | None = None,
          reference_note: str = "", has_reference_images: bool = False) -> str:
    """The system prompt for a generated template."""
    persian = lang == "fa"
    lines = [
        "You are a senior email designer. You are producing a template that a real "
        "business will send to real customers, and it has to look like it came from "
        "a studio, not from a form builder.",
        "",
        "== THE MEDIUM ==",
        "Tables for layout. Inline styles on every element. No flexbox, no grid, no "
        "position, no external CSS, no JavaScript, no <form>.",
        "One <style> block in <head> is allowed and should hold ONLY: the @font-face "
        "import, a `@media (max-width:600px)` block, and `@media (prefers-color-scheme:dark)`. "
        "Every rule in it must be a progressive enhancement — the email must be "
        "complete and correct with the whole block stripped, because Gmail strips it.",
        "Outer table width 100%, inner table width 600px, centred, "
        "`style=\"max-width:600px\"` and `width=\"600\"` both present.",
        "",
        "== TYPE ==",
        f"font-family on EVERY text element: {FONT_STACK}",
        f'Include this in <head>: {FONT_HEAD}',
        "Type scale, and do not invent others: 32px/700 for the hero line, 22px/600 "
        "for a section heading, 16px/400 with line-height 1.7 for body, 13px/400 for "
        "the footer. Letter-spacing -0.02em on the hero line only.",
        "",
        "== SPACE ==",
        "Air is what separates a designed email from a generated one. 40px of padding "
        "inside the content column on desktop, 24px on mobile. 32px between sections. "
        "Never let text touch an edge.",
        "",
        "== COLOUR ==",
        "One accent colour, used for at most three things: the button, one rule or "
        "underline, and one small piece of emphasis. Everything else is a neutral "
        "scale — near-black text (#16181d), a mid grey for secondary text (#6b7280), "
        "a very light background (#f6f7f9) behind a white content card.",
        "The content card sits on the background with 16px rounded corners and a "
        "1px border in #e8eaee. That single move is most of what makes it look "
        "current rather than like a 2012 newsletter.",
        "",
        "== THE BUTTON ==",
        "One primary call to action, and only one. Padding 14px 32px, border-radius "
        "10px, 16px/600 text, accent background, white text, no border.",
        "Wrap it in the Outlook VML fallback (`<!--[if mso]><v:roundrect ...>`), "
        "because in Outlook a styled <a> renders as a bare blue link.",
        "Its href is the literal placeholder {{cta_url}}.",
        "",
        "== STRUCTURE ==",
        "In order: a hidden preheader line (the inbox preview text, 40-90 characters, "
        "in a div with display:none;max-height:0;overflow:hidden), a header band with "
        "the brand name, a hero, the content slot, one call to action, a footer with "
        "the unsubscribe link.",
        "",
        "== SLOTS, EXACTLY AS WRITTEN ==",
        "{{content}} — on its own, where the message body goes. Write the frame "
        "around it, never the message itself. This is what makes the template "
        "reusable for every campaign rather than being one email.",
        "{{unsubscribe}} — the href of the unsubscribe link in the footer. Required.",
        "{{first_name}} — where a first name belongs, if anywhere.",
        "{{cta_url}} — the href of the button.",
        "",
        "== DARK MODE ==",
        "Add a prefers-color-scheme:dark block that swaps the card to #1b1d22 and the "
        "text to #e8eaee. Set `color-scheme: light dark` on a meta tag. An email that "
        "renders as black text on a black card is the most common modern failure.",
        "",
        "== WHAT NOT TO DO ==",
        "No stock-photo placeholder URLs. No lorem ipsum. No emoji in headings. "
        "No more than one exclamation mark in the whole document. No drop shadows "
        "(Outlook ignores them and the result looks flat and wrong next to a border). "
        "No full-width background images.",
        "Keep the whole document under 90KB.",
    ]

    if persian:
        lines += [
            "",
            "== PERSIAN ==",
            'dir="rtl" on <html> and on the body table. All visible text in Persian.',
            "text-align:right on body copy. Numbers stay Latin digits unless the "
            "brief says otherwise.",
            "Estedad is a Persian face and is the reason the font stack starts with "
            "it; keep the fallbacks in place for clients that will not load it.",
        ]
    else:
        lines += ["", "All visible text in English. dir=\"ltr\"."]

    if palette:
        lines += ["", f"Accent colour: {palette}. Derive nothing else from it — the "
                      "neutrals stay neutral."]

    if images:
        lines += ["", "== IMAGES YOU MAY USE =="]
        lines += [f"{a['url']} — {a['describes']}" for a in images]
        lines += [
            "Use each at most once, with a real alt attribute describing what it "
            "shows. Never invent a URL that is not in this list.",
            "Give every image `width` and `style=\"display:block;max-width:100%;"
            "height:auto\"`, or it will break in Outlook.",
        ]
    else:
        lines += ["", "No images are available. Build a type-led layout — that is a "
                      "legitimate and often better design, not a fallback."]

    if has_reference_images:
        lines += [
            "",
            "== THE REFERENCE ==",
            "Design references are attached as images. Read them for LAYOUT, "
            "PROPORTION, COLOUR RELATIONSHIPS and TONE, and rebuild that feeling in "
            "email-safe HTML. Do not attempt to copy them pixel for pixel, do not "
            "reproduce their logos or their photographs, and do not use their brand "
            "names. You are taking direction, not tracing.",
            "Where the reference does something the medium cannot do — overlapping "
            "elements, custom shapes, a web font that will not load — find the "
            "closest thing that survives in Outlook and say so in `notes`.",
        ]
    if reference_note:
        lines += ["", f"What the operator said about the reference: {reference_note}"]

    return "\n".join(lines)


#: A house template that ships with the product.
#:
#: It exists for two reasons. A deployment with no AI key can still put its
#: mail in something designed rather than sending bare paragraphs; and it is
#: the worked example of the brief above — the type scale, the single accent,
#: the card on a tinted ground, the VML button, the dark-mode block — so the
#: model has a standard to meet rather than a description to interpret.
#:
#: `{{brand}}`, `{{content}}` and `{{unsubscribe}}` are filled in later.
STARTER_HTML = """<!doctype html>
<html dir="{dir}" lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<link href="https://fonts.googleapis.com/css2?family=Estedad:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  @media (max-width:600px) {{
    .sp {{ padding-left:24px !important; padding-right:24px !important; }}
    .hero {{ font-size:26px !important; }}
  }}
  @media (prefers-color-scheme:dark) {{
    .bg {{ background:#0f1115 !important; }}
    .card {{ background:#1b1d22 !important; border-color:#2b2f36 !important; }}
    .tx {{ color:#e8eaee !important; }}
    .tx2 {{ color:#9aa2ad !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#f6f7f9">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{{{{subject}}}}</div>
<table class="bg" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f6f7f9">
<tr><td align="center" style="padding:32px 12px">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%">

    <tr><td class="sp" style="padding:0 8px 20px;font-family:{font};font-size:15px;font-weight:600;color:#6b7280;text-align:{start}">{{{{brand}}}}</td></tr>

    <tr><td class="card" style="background:#ffffff;border:1px solid #e8eaee;border-radius:16px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td class="sp" style="padding:40px 40px 0">
          <div class="hero tx" style="font-family:{font};font-size:32px;line-height:1.25;font-weight:700;letter-spacing:-0.02em;color:#16181d">{{{{subject}}}}</div>
          <div style="height:4px;width:56px;background:{accent};border-radius:2px;margin:20px 0 0"></div>
        </td></tr>

        <tr><td class="sp tx" style="padding:24px 40px 0;font-family:{font};font-size:16px;line-height:1.7;color:#16181d;text-align:{start}">
          {{{{content}}}}
        </td></tr>

        <tr><td class="sp" style="padding:32px 40px 40px">
          <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="{{{{cta_url}}}}" style="height:48px;v-text-anchor:middle;width:220px" arcsize="21%" fillcolor="{accent}" stroke="f"><w:anchorlock/><center style="color:#ffffff;font-family:sans-serif;font-size:16px;font-weight:600"><![endif]-->
          <a href="{{{{cta_url}}}}" style="display:inline-block;padding:14px 32px;background:{accent};color:#ffffff;font-family:{font};font-size:16px;font-weight:600;text-decoration:none;border-radius:10px">{cta}</a>
          <!--[if mso]></center></v:roundrect><![endif]-->
        </td></tr>
      </table>
    </td></tr>

    <tr><td class="sp tx2" style="padding:24px 8px 0;font-family:{font};font-size:13px;line-height:1.7;color:#6b7280;text-align:center">
      {unsub_intro} <a href="{{{{unsubscribe}}}}" style="color:#6b7280">{unsub}</a>
    </td></tr>

  </table>
</td></tr>
</table>
</body>
</html>"""


def starter(lang: str = "en", accent: str = "#7ba3cd") -> str:
    """The house template, in one language."""
    persian = lang == "fa"
    return STARTER_HTML.format(
        dir="rtl" if persian else "ltr",
        lang="fa" if persian else "en",
        start="right" if persian else "left",
        font=FONT_STACK,
        accent=accent,
        cta="مشاهده" if persian else "Take a look",
        unsub_intro="این ایمیل را دریافت کردید چون در فهرست ما هستید." if persian
                    else "You are receiving this because you are on our list.",
        unsub="لغو اشتراک" if persian else "Unsubscribe",
    )
