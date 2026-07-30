"""שפת העיצוב של יוני - טוקנים, גופנים ורכיבים.

הרעיון המרכזי מגיע ממודל הנתונים עצמו, לא מהשם: התוכנה מתארת ידע כ"לבנים חסרות"
(status.json). כלומר ידע הוא קיר, ומה שחסר הוא חור בקיר. כל העיצוב נגזר מזה -
כולל הצבעים, שכל אחד מהם מסמן *מצב לימודי* ולא סתם גוון:

    set   (תכלת)  לבנה שהונחה - נושא שנרכש
    open  (אפור)  לבנה חסרה   - נושא פתוח
    now   (ענבר)  הלבנה הנוכחית - מה שעובדים עליו עכשיו

הגופנים משובצים בקובץ עצמו (base64) ולא נטענים מ-Google Fonts: התוכנה כולה עובדת
בלי אינטרנט, ואסור שדפדפן של ילד יפנה לשרת חיצוני רק כדי לצייר אותיות.
"""

import base64
import os

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# ---------------------------------------------------------------------------
# טוקנים
# ---------------------------------------------------------------------------
MORTAR = "#E9EEF3"    # רקע - הטיט שבין הלבנים
PAPER = "#FDFDFC"     # משטחים מורמים (כרטיסים, בועות)
INK = "#16233B"       # טקסט ראשי וכותרות
INK_DIM = "#5A6B84"   # טקסט משני
SET = "#2E6DA4"       # לבנה שהונחה (תכלת)
SET_DEEP = "#1D4C77"  # עומק/ריחוף
OPEN = "#C9D4DF"      # לבנה חסרה - חלל, לא כישלון
NOW = "#E2A03C"       # הלבנה הנוכחית - המבטא היחיד, במשורה


def _font_face(filename, family, weight):
    """משבץ קובץ גופן כ-base64 - כדי שלא תהיה שום פנייה לרשת."""
    path = os.path.join(FONT_DIR, filename)
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""  # הגופן חסר - הדפדפן ייפול חזרה לברירת מחדל, בלי לשבור כלום
    return (
        "@font-face{font-family:'%s';font-style:normal;font-weight:%s;"
        "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2');}"
        % (family, weight, encoded)
    )


def _fonts():
    return "".join([
        _font_face("frank-ruhl-libre-700.woff2", "FrankRuhl", 700),
        _font_face("assistant-400.woff2", "Assistant", 400),
        _font_face("assistant-600.woff2", "Assistant", 600),
    ])


CSS = """
%(fonts)s

:root{
  --mortar:%(mortar)s; --paper:%(paper)s; --ink:%(ink)s; --ink-dim:%(ink_dim)s;
  --set:%(set)s; --set-deep:%(set_deep)s; --open:%(open)s; --now:%(now)s;
  --display:'FrankRuhl',Georgia,serif;
  --body:'Assistant',-apple-system,'Segoe UI',sans-serif;
  --brick-r:3px;
}

/* ---- בסיס + RTL ---------------------------------------------------- */
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  direction:rtl; background:var(--mortar); color:var(--ink);
  font-family:var(--body);
}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stMain"] .block-container{max-width:920px;padding-top:2.2rem;}
h1,h2,h3,p,label,li,.stMarkdown{direction:rtl;text-align:right;}
textarea,input,[data-testid="stChatInput"] textarea{direction:rtl;text-align:right;}

h1,h2,h3{font-family:var(--display);color:var(--ink);letter-spacing:-.01em;}

/* ---- הקיר: אלמנט החתימה --------------------------------------------
   הלבנים מונחות מימין לשמאל, בכיוון שבו קוראים עברית.               */
.wall{display:flex;flex-direction:column;gap:4px;margin:0 0 1.6rem;}
.wall-row{display:flex;flex-direction:row-reverse;gap:4px;}
.brick{
  height:17px;border-radius:var(--brick-r);flex:1 1 auto;
  animation:set-brick .42s cubic-bezier(.2,.7,.3,1) both;
}
.brick.is-set{background:var(--set);}
.brick.is-open{
  background:transparent;
  border:1.5px dashed var(--open);
  box-shadow:inset 0 1px 5px rgba(22,35,59,.07);
}
.brick.is-now{background:var(--now);}
.brick.is-gap{background:none;border:none;box-shadow:none;animation:none;}
/* יחסי לבנה אמיתיים: חצי-לבנה בקצה השורה יוצרת מישקים מדורגים (בנייה בקשר).
   בלי הדירוג הזה זו רשת, לא קיר - וזה מה שהופך את הצורה לקריאה. */
.brick.w1{flex-grow:1;} .brick.w2{flex-grow:2;} .brick.w3{flex-grow:3;}
.brick.w4{flex-grow:4;} .brick.w6{flex-grow:6;} .brick.w8{flex-grow:8;}
.brick.w10{flex-grow:10;} .brick.w12{flex-grow:12;}

@keyframes set-brick{
  from{opacity:0;transform:translateX(14px) scaleX(.86);}
  to{opacity:1;transform:none;}
}

/* ---- כותרת הכניסה --------------------------------------------------- */
.entry-head{margin-bottom:.4rem;}
.entry-title{
  font-family:var(--display);font-weight:700;font-size:clamp(2.6rem,7vw,4.2rem);
  line-height:.95;color:var(--ink);margin:0;
}
.entry-sub{
  font-family:var(--body);font-weight:600;font-size:1.05rem;
  color:var(--ink-dim);margin:.5rem 0 0;
}
.entry-sub .accent{color:var(--now);}
.eyebrow{
  font-family:var(--body);font-weight:600;font-size:.72rem;
  letter-spacing:.16em;color:var(--ink-dim);text-transform:none;
  margin:0 0 .5rem;
}

/* ---- טפסים ופקדים ---------------------------------------------------- */
[data-testid="stForm"]{
  background:var(--paper);border:1px solid rgba(22,35,59,.09);
  border-radius:8px;padding:1.4rem 1.5rem;box-shadow:0 1px 2px rgba(22,35,59,.04);
}
.stTextInput input{
  background:var(--mortar)!important;border:1px solid rgba(22,35,59,.14)!important;
  border-radius:var(--brick-r)!important;color:var(--ink)!important;
  font-family:var(--body)!important;
}
.stTextInput input:focus{border-color:var(--set)!important;box-shadow:0 0 0 3px rgba(46,109,164,.18)!important;}
.stButton button,.stFormSubmitButton button{
  background:var(--set);color:#fff;border:none;border-radius:var(--brick-r);
  font-family:var(--body);font-weight:600;padding:.5rem 1.4rem;
  transition:background .15s ease;
}
.stButton button:hover,.stFormSubmitButton button:hover{background:var(--set-deep);color:#fff;}
.stButton button:focus-visible,.stFormSubmitButton button:focus-visible{
  outline:3px solid var(--now);outline-offset:2px;
}

[data-baseweb="tab-list"]{gap:.4rem;background:transparent;border-bottom:1px solid rgba(22,35,59,.1);}
[data-baseweb="tab"]{font-family:var(--body);font-weight:600;color:var(--ink-dim);}
[data-baseweb="tab"][aria-selected="true"]{color:var(--set);}
[data-baseweb="tab-highlight"]{background:var(--set);}

/* ---- שיחה ------------------------------------------------------------ */
[data-testid="stChatMessage"]{
  direction:rtl;text-align:right;background:var(--paper);
  border:1px solid rgba(22,35,59,.07);border-radius:8px;
  border-inline-start:3px solid var(--set);
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
  background:transparent;border-inline-start-color:var(--open);
}
[data-testid="stChatInput"]{background:var(--paper);border-radius:8px;}

/* ---- הודעת מצוקה: רכה בכוונה, לא אזעקה ------------------------------ */
.care{
  background:var(--paper);border:1px solid rgba(226,160,60,.4);
  border-inline-start:4px solid var(--now);border-radius:8px;
  padding:1.1rem 1.3rem;line-height:1.75;
}
.care .care-line{display:block;margin:.15rem 0;}
.care .hotline{font-weight:600;color:var(--ink);}

/* ---- סרגל צד --------------------------------------------------------- */
[data-testid="stSidebar"]{background:var(--paper);border-inline-start:1px solid rgba(22,35,59,.08);}
[data-testid="stSidebar"] *{direction:rtl;text-align:right;}
.who{font-family:var(--display);font-size:1.35rem;color:var(--ink);margin:0;}
.who-id{font-family:var(--body);font-size:.8rem;color:var(--ink-dim);}

/* ---- נגישות ---------------------------------------------------------- */
:focus-visible{outline:3px solid var(--now);outline-offset:2px;}
@media (prefers-reduced-motion:reduce){
  .brick{animation:none!important;}
  *{transition:none!important;}
}
@media (max-width:640px){
  .entry-title{font-size:2.4rem;}
  .brick{height:20px;}
}
"""


def css():
    """מחזיר את גיליון הסגנון המלא, עם הגופנים משובצים."""
    return "<style>" + CSS % {
        "fonts": _fonts(), "mortar": MORTAR, "paper": PAPER, "ink": INK,
        "ink_dim": INK_DIM, "set": SET, "set_deep": SET_DEEP,
        "open": OPEN, "now": NOW,
    } + "</style>"


# ---------------------------------------------------------------------------
# רכיבים
# ---------------------------------------------------------------------------
def wall(rows, animate=True):
    """מצייר קיר לבנים.

    rows: רשימה של שורות; כל שורה היא רשימה של (state, width) כאשר
    state הוא "set" | "open" | "now" ו-width הוא 1..3.

    ההנחה מתבצעת מימין לשמאל (row-reverse) - בכיוון הקריאה בעברית. זו לא
    קישוט: הקיר נבנה באותו כיוון שבו הילד קורא אותו.
    """
    html = ['<div class="wall">']
    index = 0
    for row in rows:
        html.append('<div class="wall-row">')
        for state, width in row:
            delay = f"animation-delay:{index * 26}ms;" if animate else "animation:none;"
            html.append(f'<div class="brick is-{state} w{width}" style="{delay}"></div>')
            index += 1
        html.append("</div>")
    html.append("</div>")
    return "".join(html)


def _course(cells, per_row=6):
    """מחלק לבנים לשורות, ומדרג את המישקים: שורה זוגית מתחילה בלבנה שלמה,
    שורה אי-זוגית בחצי לבנה. זה הקשר שהופך רשת לקיר.

    שורה אחרונה חלקית מקבלת מילוי שקוף ("gap") - בלי זה flex מותח את הלבנים
    הבודדות לרוחב כל השורה, והקיר מאבד את הפרופורציה שלו.
    """
    rows, i, line = [], 0, 0
    while i < len(cells):
        take = per_row if line % 2 == 0 else per_row + 1
        row = list(cells[i:i + take])
        if line % 2 == 1 and row:  # חצאי לבנה בקצוות
            row = [(row[0][0], 1)] + row[1:-1] + ([(row[-1][0], 1)] if len(row) > 1 else [])
        missing = take - len(cells[i:i + take])
        if missing > 0:
            row.append(("gap", missing * 2))
        rows.append(row)
        i += take
        line += 1
    return rows


# הקיר של מסך הכניסה: כמעט שלם, ולבנה אחת חסרה - המקום של התלמיד.
def _entry_cells():
    # 32 = 6+7+6+7+6 בדיוק, כך שכל השורות מלאות ואין שורה יתומה בתחתית.
    cells = [("set", 2)] * 32
    cells[19] = ("open", 2)  # החור היחיד, בערך במרכז המבט
    return cells


ENTRY_WALL = _course(_entry_cells())


def student_wall(open_bricks, closed_count=16):
    """בונה את הקיר האמיתי של התלמיד מתוך status.json.

    הלבנה הראשונה הפתוחה מסומנת "now" - זה מה שעובדים עליו עכשיו.
    """
    cells = [("set", 2)] * closed_count
    for i, _ in enumerate(open_bricks):
        cells.append(("now" if i == 0 else "open", 2))
    return wall(_course(cells or [("open", 2)], per_row=5))
