# wrestling-digest

## תיאור
מערכת יומית לאיסוף חדשות פלחון מ-RSS feeds, קיבוץ לפי נושא דרך Claude, וסיכום מפורט לפי promotion (AEW/WWE/Other). נשלח כאימייל HTML בכל בוקר (יעד: 08:00 שעון ישראל).

## טכנולוגיות
- **שפה:** Python 3.11+
- **AI:** Claude API (claude-sonnet-4-6)
- **feeds:** RSS via feedparser + OPML
- **Email:** Gmail SMTP (App Password)
- **Scheduler:** GitHub Actions (cron) + Windows Task Scheduler (מקומי)

## GitHub
- **Repo:** https://github.com/ilan316/wrestling-digest
- **Actions:** `.github/workflows/run.yml` — cron `"43 4 * * *"` = 04:43 UTC ≈ 07:43 שעון ישראל (קיץ).
  הדקה :43 (ולא :00) כדי להימנע מעומס תחילת-שעה של GitHub Actions, שיכול לדחות ריצות ב-1-2 שעות.

## משתני סביבה
```
CLAUDE_API_KEY=...
GMAIL_USER=...
GMAIL_APP_PASSWORD=...
RECIPIENT_EMAIL=...
LOOKBACK_HOURS=24
```

## קבצים מרכזיים
- `main.py` — pipeline ראשי
- `feedly_client.py` — קריאת OPML + RSS fetch מקביל
- `clusterer.py` — קיבוץ כתבות דרך Claude
- `summarizer.py` — סיכום מפורט לפי cluster
- `email_sender.py` — שליחת HTML email
- `blackout.py` / `blackout.json` — חסימה בזמן אירועים חיים
- `update_blackout.py` — עדכון אוטומטי מ-cagematch.net

## כללי עבודה
1. תמיד Plan Mode לפני שינויים
2. אחרי כל שינוי — commit + push
3. שפת תגובה: עברית

## הערה חשובה — שעון קיץ/חורף
ישראל בשעון קיץ (UTC+3) ⇒ cron הנוכחי `"43 4 * * *"` = 07:43 ישראל.
באוקטובר, במעבר לשעון חורף (UTC+2), יש לשנות ל-`"43 5 * * *"` כדי להישאר על ~07:43.

## הערה — עיכוב בקבלת המייל
GitHub Actions לא מבטיח ריצה בזמן ה-cron המדויק; בשעות עומס יש דחייה של עד 1-2 שעות.
זו הסיבה לדקה :43 ולא :00. אם דרוש דיוק מוחלט — צריך scheduler חיצוני (Railway/cron מקומי).
