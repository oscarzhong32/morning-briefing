# Morning Briefing

Morning Briefing is a daily financial newsletter generator. It pulls market data, combines RSS with news APIs, uses AI to classify and rank stories, then renders a Bloomberg-style email and saves a local HTML archive.

## What it does

- Fetches market data for indices, FX, commodities, and crypto
- Collects news from Yahoo RSS plus NewsAPI and GNews
- Sends the combined candidate pool to Agnes AI for sector classification and importance ranking
- Builds a sector-based briefing:
  - Global macro
  - Mainland / Hong Kong / Macau
  - Middle East macro
  - Market liquidity and multi-asset snapshot
  - Senior insight
  - Key entity watchlist
- Sends the briefing by email and saves a dated HTML file locally

## How it works

1. RSS, NewsAPI, and GNews are fetched in parallel-ish sequence.
2. The result is deduplicated into one candidate pool.
3. Agnes AI receives up to 90 candidates and returns structured JSON.
4. The app validates and normalizes the AI output.
5. Each sector is sorted by `importance` and capped at 10 stories.
6. The email HTML is rendered with an inline dark shell so Gmail keeps the black background.

## Files

- `morning_briefing.py` - main app
- `config.json` - local config used by the script
- `config.example.json` - template users should copy and fill in
- `setup_task.ps1` - Windows scheduled task helper
- `.github/workflows/briefing.yml` - GitHub Actions schedule

## Configuration

Start by copying `config.example.json` to `config.json`, then fill in the values below.

### Email settings

- `smtp_server` - SMTP host, usually `smtp.gmail.com`
- `smtp_port` - SMTP port, usually `587`
- `sender_email` - Gmail sender address
- `sender_password` - Gmail app password or leave blank and use `BRIEFING_EMAIL_PASSWORD`
- `recipient_email` - primary recipient
- `recipient_emails` - list of recipients
- `use_tls` - usually `true`

For GitHub Actions, set recipients with the repository secret `BRIEFING_RECIPIENT_EMAILS`.
It overrides `config.json` and accepts comma or semicolon separated emails, for example:

```text
person1@example.com,person2@example.com,colleague@example.com
```

### Briefing settings

- `timezone` - usually `Asia/Hong_Kong`
- `delivery_time` - daily send time
- `weekdays_only` - set `false` if you want 7-day delivery

### News sources

RSS sources are listed under `briefing.news_sources`. You can add or remove feeds there.

### AI and news API keys

These are read from environment variables first:

- `AGNES_API_KEY`
- `NEWSAPI_KEY`
- `GNEWS_KEY`
- `BRIEFING_EMAIL_PASSWORD`
- `BRIEFING_RECIPIENT_EMAILS`

You can also put the keys in `config.json`, but environment variables are recommended.

## API setup

### Agnes AI

Used for classification, ranking, and summary generation.

Set:

- `AGNES_API_KEY`
- optional `AGNES_BASE_URL`
- optional `AGNES_MODEL`

### NewsAPI

Used as an extra news candidate source.

Set:

- `NEWSAPI_KEY`

Useful query fields in config:

- `enabled`
- `language`
- `country`
- `q`
- `sources`

### GNews

Used as an extra news candidate source.

Set:

- `GNEWS_KEY`

Useful query fields in config:

- `enabled`
- `language`
- `country`
- `q`

## Running locally

```powershell
python morning_briefing.py
```

The script writes a dated `briefing_YYYY-MM-DD.html` file in the project folder.

## Email delivery

If a sender password is configured, the script sends the email automatically.
If not, it still generates the local HTML file.

## Scheduling

### Windows Task Scheduler

Run `setup_task.ps1` as Administrator.

### GitHub Actions

The workflow runs daily and expects these secrets:

- `BRIEFING_EMAIL_PASSWORD`
- `BRIEFING_RECIPIENT_EMAILS`
- `AGNES_API_KEY`
- `NEWSAPI_KEY`
- `GNEWS_KEY`

If you only want local email delivery, you can skip the news API secrets and the app will fall back to RSS-only candidate sources.

## Notes

- Yahoo RSS is already part of the current setup.
- The app does not force every sector to have 10 stories.
- If a sector has fewer relevant stories, it stays smaller rather than mixing unrelated stories.

## License

No license has been set yet.
