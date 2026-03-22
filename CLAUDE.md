# wrestling-digest

## תיאור
מערכת יומית לאיסוף חדשות פלחון מ-RSS feeds, קיבוץ לפי נושא דרך Claude, וסיכום מפורט לפי promotion (AEW/WWE/Other). נשלח כאימייל HTML ב-20:00 כל יום.

## טכנולוגיות
- **שפה:** Python 3.11+
- **AI:** Claude API (claude-sonnet-4-6)
- **feeds:** RSS via feedparser + OPML
- **Email:** Gmail SMTP (App Password)
- **Scheduler:** GitHub Actions (cron) + Windows Task Scheduler (מקומי)

## GitHub
- **Repo:** https://github.com/ilan316/wrestling-digest
- **Actions:** `.github/workflows/run.yml` — רץ כל יום ב-18:00 UTC (20:00 ישראל חורף)

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

## הערה חשובה — שעון קיץ
ב-27/3/2026 ישראל עוברת לשעון קיץ (UTC+3).
יש לשנות ב-`run.yml`: `cron: "0 17 * * *"` (במקום 18:00)
