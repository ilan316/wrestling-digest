# wrestling-digest

## תיאור
מערכת יומית לאיסוף חדשות פלחון מ-RSS feeds, קיבוץ לפי נושא דרך LLM, וסיכום מפורט לפי promotion (AEW/WWE/Other). נשלח כאימייל HTML בכל בוקר (יעד: ~07:43 שעון ישראל). **הפלט באנגלית.**

## טכנולוגיות
- **שפה:** Python 3.11+
- **AI:** Google Gemini API (`gemini-2.5-flash`, free tier) — כל הקריאות עוברות דרך `llm.py`
- **feeds:** RSS via feedparser + OPML
- **Email:** Gmail SMTP (App Password)
- **Scheduler:** GitHub Actions (cron) + Windows Task Scheduler (מקומי)

## GitHub
- **Repo:** https://github.com/ilan316/wrestling-digest
- **Actions:** `.github/workflows/run.yml` — שני cron: `"43 4 * * *"` + `"43 5 * * *"` (04:43 ו-05:43 UTC).
  ה-guard ב-main.py בורר את הריצה שנוחתת על ~07:xx שעון ישראל — **אין צורך לשנות cron ידנית במעברי שעון**.
  הדקה :43 (ולא :00) כדי להימנע מעומס תחילת-שעה של GitHub Actions, שיכול לדחות ריצות ב-1-2 שעות.

## משתני סביבה
```
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey — בלי לחבר billing!
GMAIL_USER=...
GMAIL_APP_PASSWORD=...
RECIPIENT_EMAIL=...
LOOKBACK_HOURS=24
GEMINI_MODEL=             # אופציונלי, ברירת מחדל gemini-2.5-flash
GEMINI_RPM=               # אופציונלי, ברירת מחדל 10 (מגבלת ה-free tier)
```

## הערה — free tier ומגבלת קצב
ה-free tier מוגבל ל-~10 בקשות לדקה, והפייפליין שולח ~62 קריאות ליום.
`llm.py` מחזיק rate limiter גלובלי (`threading.Lock`) שכל ה-worker threads חולקים —
ריצה שלמה לוקחת ~7 דקות. ריצה שנגמרת ב-30 שניות = ה-limiter לא עובד.
כמו כן `thinking_budget=0` הוא **חובה**: ב-2.5-flash ה-thinking דלוק כברירת מחדל
ואוכל את `max_output_tokens`, והתוצאה היא 200 OK עם טקסט ריק.
אם מתחילים 429 — אפשר לרדת ל-`gemini-2.5-flash-lite` דרך `GEMINI_MODEL` בלי שינוי קוד.

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

## הערה — שעון קיץ/חורף (נפתר אוטומטית)
היו שתי ריצות cron יומיות (04:43 + 05:43 UTC), ו-main.py מריץ רק את זו שבה שעון ישראל ≥ 07:00,
עם dedup לפי קובץ ה-digest היומי כדי לא לשלוח פעמיים. קיץ: 04:43→07:43 שולח, 05:43→08:43 מדלג.
חורף: 04:43→06:43 מדלג, 05:43→07:43 שולח. עמיד לדחיות (דחייה רק מאחרת, לא מדלגת יום). אין עוד עריכה ידנית.

## הערה — עיכוב בקבלת המייל
GitHub Actions לא מבטיח ריצה בזמן ה-cron המדויק; בשעות עומס יש דחייה של עד 1-2 שעות.
זו הסיבה לדקה :43 ולא :00. אם דרוש דיוק מוחלט — צריך scheduler חיצוני (Railway/cron מקומי).
