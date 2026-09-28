# wrestling-digest

> ⚠️ קובץ זה זהה ל-`CLAUDE.md` / `AGENTS.md` באותה תיקייה. כל עדכון חייב להיכתב **בשני הקבצים**.

## תיאור
מערכת יומית לאיסוף חדשות פלחון מ-RSS feeds, קיבוץ לפי נושא דרך LLM, וסיכום מפורט לפי promotion (AEW/WWE/Other). נשלח כאימייל HTML בכל בוקר (טריגר 10:00 שעון ישראל, המייל מגיע ~10:20-10:40). **הפלט באנגלית.**

**מ-28/09/26 המייל כולל AEW בלבד** (`PROMOTIONS` ב-config.py, ברירת מחדל `AEW`). WWE/Other מסוננים מיד אחרי הקיבוץ — לא מסוכמים ולא נכנסים ל-history. להחזרה: `PROMOTIONS=AEW,WWE,Other`.

## טכנולוגיות
- **שפה:** Python 3.11+
- **AI:** Google Gemini API (free tier) — כל הקריאות עוברות דרך `llm.py`.
  **שני מודלים:** `gemini-3.5-flash-lite` לסיכומים (~60 קריאות), `gemini-3.6-flash` לשתי הקריאות
  המבניות (clusterer + history-filter) דרך `heavy=True`.
  **fallback:** קריאת heavy שנכשלת פעמיים ברצף (503 וכו') או מקבלת 429 PerDay — עוברת ל-lite
  לשאר הניסיונות של אותה קריאה (`_HEAVY_FALLBACK_AFTER` ב-llm.py). נוסף 28/09/26 אחרי ש-3.6-flash
  נפל ב-503 בשלושה בקרים מתוך חמישה (23-25/09) והדדופ דולג.
- **feeds:** RSS via feedparser + OPML, 10 פידים (BodySlam הוסר 28/09/26). User-Agent של Chrome — UA "מזוהה" מקבל 403 מחלק מהאתרים
- **Email:** Gmail SMTP (App Password)
- **Scheduler:** cron-job.org → `workflow_dispatch` ל-GitHub Actions (ראו למטה)

## GitHub
- **Repo:** https://github.com/ilan316/wrestling-digest · ענף `master` (לא `main`)
- **טריגר:** אין `schedule:` ב-workflows (ה-scheduler של GitHub איחר/דילג על ימים שלמים באוגוסט 26).
  cron-job.org job `8348224` שולח POST ל-`run.yml/dispatches` ב-10:00 Asia/Jerusalem (timezone נטיבי —
  **אין צורך לשנות דבר במעברי שעון**). Watchdog: job `8371743` ב-10:45 מפעיל את `watchdog.yml`, שמריץ את run.yml שוב.
  ה-PAT שבכותרת ה-Authorization הוא ללא תפוגה.
- **חסימת כפילות:** ה-`guard` job ב-run.yml מדלג אם כבר הייתה היום ריצה מוצלחת, ו-main.py מדלג אם
  `docs/{date}-digest.html` של היום (שעון ישראל) כבר קיים.

## state ב-docs/ (נשמר דרך `git add docs/` ב-workflow)
- `history.json` — הסיפורים של 5 הימים האחרונים (כולל היום) לדדופ. ב-prompt: TL;DR רק ליומיים האחרונים, ימים ישנים — כותרת בלבד.
- `state.json` — `last_run_ts` של השליחה המוצלחת האחרונה. חלון ה-lookback = מאז הריצה האחרונה + שעה,
  לא פחות מ-`LOOKBACK_HOURS` ולא יותר מ-72 שעות — יום שנפל לא מאבד חדשות.
- כתבה בלי תאריך בפיד שיש בו תאריכים — מדולגת (אחרת היא "חדשה" כל יום מחדש).

## משתני סביבה
```
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey — בלי לחבר billing!
GMAIL_USER=...
GMAIL_APP_PASSWORD=...
RECIPIENT_EMAIL=...
LOOKBACK_HOURS=24
GEMINI_MODEL=             # אופציונלי, ברירת מחדל gemini-3.5-flash-lite (הסיכומים)
GEMINI_MODEL_HEAVY=       # אופציונלי, ברירת מחדל gemini-3.6-flash (clusterer + history-filter)
GEMINI_RPM=               # אופציונלי, ברירת מחדל 10 (מתחת ל-15/דקה שנמדדו)
PROMOTIONS=               # אופציונלי, ברירת מחדל AEW (למייל המלא: AEW,WWE,Other)
```

## הערה — free tier ומגבלות מכסה
**שתי מגבלות שונות, ואסור לבלבל ביניהן** (נמדדו 21/08/26 מול ה-API):

| מודל | מגבלה חוסמת | ערך |
|---|---|---|
| `gemini-3.6-flash` | **PerDay** | **20 בקשות ליום** |
| `gemini-3.5-flash-lite` | PerMinute | 15 בקשות לדקה (אין תקרה יומית שנדלקת בעומס שלנו) |

הפייפליין שולח ~70 קריאות ליום, אז `gemini-3.6-flash` **לא יכול לשאת את הריצה** — ב-21/08
9 מתוך 13 הסיכומים נפלו ל-raw excerpt באמצע ריצת פרודקשן. rate limiter לא פותר תקרה יומית.
לכן הפיצול: הסיכומים ב-lite, ושתי הקריאות המבניות בלבד ב-3.6 דרך `heavy=True`.

`llm.py` מחזיק rate limiter גלובלי (`threading.Lock`) שכל ה-worker threads חולקים —
ריצה שלמה לוקחת ~20-40 דקות (נמדד בספטמבר 26). ריצה שנגמרת ב-30 שניות = ה-limiter לא עובד.

חובה להשתיק thinking: הוא דלוק כברירת מחדל ואוכל את `max_output_tokens`,
והתוצאה היא 200 OK עם טקסט ריק. **הכפתור החליף שם בין דורות** — 2.x מקבל
`thinking_budget=0`, 3.x דוחה אותו ב-400 INVALID_ARGUMENT יבש ודורש
`thinking_level="LOW"` (אין "off" ב-3.x). `_thinking_config()` ב-llm.py בורר לפי שם המודל.
`gemini-2.5-flash` ו-`gemini-2.5-flash-lite` **סגורים למפתחות חדשים**
("no longer available to new users") — הם מופיעים ב-`models.list()` אבל 404 ב-`generateContent`.

כל 429 בלוג מדפיס את ה-`quotaId` — אם כתוב `PerDay` הריצה גמורה ואין טעם ב-retry;
`PerMinute` זה רק האטה.

## קבצים מרכזיים
- `main.py` — pipeline ראשי
- `llm.py` — נקודת ה-LLM היחידה (Gemini client + rate limiter + retry)
- `feedly_client.py` — קריאת OPML + RSS fetch מקביל
- `clusterer.py` — קיבוץ כתבות + dedup מול היסטוריה
- `summarizer.py` — סיכום מפורט לפי cluster
- `email_sender.py` — שליחת HTML email + יצירת עמוד GitHub Pages משולב

## כללי עבודה
1. תמיד Plan Mode לפני שינויים
2. אחרי כל שינוי — commit + push
3. שפת תגובה: עברית

## ⛔ אסור בלי אישור מפורש
- **אין לחבר billing ל-Gemini.** ההכרעה (28/08/26) היא free tier בלבד. הפתרון
  למגבלת ה-20 בקשות/יום הוא הפיצול לשני מודלים — לא שדרוג בתשלום.
- **אין fallback ל-Claude.** נשקל ונפסל. ה-fallback היחיד שמותר הוא heavy→lite בתוך Gemini
  (אושר 28/09/26) — לא להוסיף ספק נוסף.
- **אין לחתוך סיפורים** כדי לחסוך קריאות — הפלט המלא הוא המוצר.
- **אין להשתיק את ה-rate limiter או להריץ ללא Lock** — ריצה שנגמרת ב-30 שניות
  היא ריצה שבורה, לא ריצה מהירה.
- **אין לשנות את שעת הטריגר במעברי שעון קיץ/חורף** — cron-job.org עובד ב-Asia/Jerusalem נטיבית.
- **אין להחזיר `schedule:` ל-run.yml** — ה-scheduler של GitHub לא אמין; הטריגר החיצוני הוא הפתרון.
