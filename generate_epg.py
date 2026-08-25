import requests
import datetime
import re
from xml.sax.saxutils import escape, quoteattr
from zoneinfo import ZoneInfo

API_KEY = "YOUR_FOOTBALL_DATA_API_KEY"  # Replace with your API token
PL_COMPETITION_ID = "PL"
UK_TZ = ZoneInfo("Europe/London")

def sanitize_id(name: str) -> str:
    """Creates a clean, XML-safe ID without '&' or special characters."""
    clean = name.lower()
    clean = clean.replace("&", "and")
    clean = re.sub(r"[^a-z0-9]", "", clean)
    clean = clean.replace("fc", "")
    return clean.strip()

def format_xmltv_time(dt: datetime.datetime) -> str:
    """Formats datetime into XMLTV format with timezone offset: YYYYMMDDHHMMSS +0100"""
    return dt.strftime("%Y%m%d%H%M%S %z")

headers = {"X-Auth-Token": API_KEY}
url = f"https://api.football-data.org/v4/competitions/{PL_COMPETITION_ID}/matches?status=SCHEDULED,TIMED"

response = requests.get(url, headers=headers)
data = response.json()
matches = data.get("matches", [])

# Map of clean team names to sanitized channel IDs
teams = {}
for m in matches:
    for side in [m["homeTeam"]["name"], m["awayTeam"]["name"]]:
        if side not in teams:
            teams[side] = sanitize_id(side)

xml_lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<tv generator-info-name="PL-Continuous-Fixture-EPG">'
]

# 1. Generate Channel Definitions
for name, team_id in teams.items():
    xml_lines.append(f'  <channel id="{team_id}.pl">')
    xml_lines.append(f'    <display-name>{escape(name)}</display-name>')
    xml_lines.append('  </channel>')

# 2. Generate Continuous Schedules per Team
now_uk = datetime.datetime.now(UK_TZ)

for team_name, team_id in teams.items():
    channel_id = f"{team_id}.pl"
    
    # Filter and sort this team's scheduled matches chronologically
    team_matches = [
        m for m in matches 
        if m["homeTeam"]["name"] == team_name or m["awayTeam"]["name"] == team_name
    ]
    team_matches.sort(key=lambda x: x["utcDate"])

    # Start timeline from now (or beginning of today)
    timeline_cursor = now_uk.replace(minute=0, second=0, microsecond=0)

    for match in team_matches:
        utc_dt = datetime.datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        ko_uk = utc_dt.astimezone(UK_TZ)

        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        opponent = away if home == team_name else f"@{home}"
        matchday = match.get("matchday", "")

        # Buildup starts 30 mins before KO; match coverage ends 2 hours after KO
        event_start = ko_uk - datetime.timedelta(minutes=30)
        event_end = ko_uk + datetime.timedelta(hours=2)

        ko_time_str = ko_uk.strftime("%H:%M")
        ko_date_str = ko_uk.strftime("%a %d %b")

        # Fill the gap before this match with "Next Match" placeholder
        if event_start > timeline_cursor:
            pre_start_str = format_xmltv_time(timeline_cursor)
            pre_stop_str = format_xmltv_time(event_start)
            
            filler_title = f"Next: vs {opponent} ({ko_date_str} @ {ko_time_str})"
            filler_desc = f"Upcoming Premier League Fixture: {home} vs {away}. Kickoff at {ko_time_str} UK on {ko_date_str}."

            xml_lines.append(f'  <programme start="{pre_start_str}" stop="{pre_stop_str}" channel="{channel_id}">')
            xml_lines.append(f'    <title lang="en">{escape(filler_title)}</title>')
            xml_lines.append(f'    <desc lang="en">{escape(filler_desc)}</desc>')
            xml_lines.append('  </programme>')

        # Live Match Block (starts 30m before kickoff)
        match_start_str = format_xmltv_time(event_start)
        match_stop_str = format_xmltv_time(event_end)
        
        live_title = f"LIVE: {home} vs {away}"
        live_desc = f"Premier League Matchday {matchday} - Kickoff {ko_time_str} UK ({ko_date_str})."

        xml_lines.append(f'  <programme start="{match_start_str}" stop="{match_stop_str}" channel="{channel_id}">')
        xml_lines.append(f'    <title lang="en">{escape(live_title)}</title>')
        xml_lines.append(f'    <desc lang="en">{escape(live_desc)}</desc>')
        xml_lines.append('  </programme>')

        # Advance cursor to the end of this match so the next gap filler takes over
        timeline_cursor = event_end

xml_lines.append('</tv>')

with open("pl_epg.xml", "w", encoding="utf-8") as f:
    f.write("\n".join(xml_lines))
