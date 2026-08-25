import requests
import datetime
import re
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

API_KEY = "185f668365a14c6dade238bd621d5a13"
PL_COMPETITION_ID = "PL"
UK_TZ = ZoneInfo("Europe/London")

def sanitize_id(name: str) -> str:
    """Standardizes club names to predictable XML channel IDs."""
    clean = name.lower()
    clean = clean.replace("&", "and")
    clean = re.sub(r"\b(afc|fc)\b", "", clean)
    clean = re.sub(r"[^a-z0-9]", "", clean)
    return clean.strip()

def format_xmltv_time(dt: datetime.datetime) -> str:
    """Formats datetime into XMLTV standard: YYYYMMDDHHMMSS +0100 / +0000"""
    return dt.strftime("%Y%m%d%H%M%S %z")

headers = {"X-Auth-Token": API_KEY}

# 1. Fetch Season Matches
url_matches = f"https://api.football-data.org/v4/competitions/{PL_COMPETITION_ID}/matches"
resp = requests.get(url_matches, headers=headers)

if resp.status_code != 200:
    print(f"API Error {resp.status_code}: {resp.text}")
    matches_raw = []
else:
    matches_raw = resp.json().get("matches", [])

now_uk = datetime.datetime.now(UK_TZ)

# Filter for upcoming matches
upcoming_matches = []
for m in matches_raw:
    utc_str = m.get("utcDate")
    if not utc_str:
        continue
    utc_dt = datetime.datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    match_end = utc_dt.astimezone(UK_TZ) + datetime.timedelta(hours=2)
    
    if match_end > now_uk and m.get("status") not in ["FINISHED", "AWARDED"]:
        upcoming_matches.append(m)

print(f"Upcoming matches found: {len(upcoming_matches)}")

# 2. Extract All Teams
teams = {}
for m in matches_raw:
    for side in [m["homeTeam"]["name"], m["awayTeam"]["name"]]:
        if side not in teams:
            teams[side] = sanitize_id(side)

# Fallback to direct teams list if matches were empty
if not teams:
    url_teams = f"https://api.football-data.org/v4/competitions/{PL_COMPETITION_ID}/teams"
    resp_teams = requests.get(url_teams, headers=headers)
    if resp_teams.status_code == 200:
        for t in resp_teams.json().get("teams", []):
            teams[t["name"]] = sanitize_id(t["name"])

print(f"Teams count: {len(teams)}")

# 3. Build Full XMLTV File using .epl
xml_lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<tv generator-info-name="PL-Continuous-Fixture-EPG">'
]

# Channel Definitions
for name, team_id in sorted(teams.items()):
    xml_lines.append(f'  <channel id="{team_id}.epl">')
    xml_lines.append(f'    <display-name>{escape(name)}</display-name>')
    xml_lines.append('  </channel>')

# Continuous Schedules for EVERY team
for team_name, team_id in sorted(teams.items()):
    channel_id = f"{team_id}.epl"
    
    team_matches = [
        m for m in upcoming_matches 
        if m["homeTeam"]["name"] == team_name or m["awayTeam"]["name"] == team_name
    ]
    team_matches.sort(key=lambda x: x["utcDate"])

    timeline_cursor = now_uk.replace(minute=0, second=0, microsecond=0)

    if not team_matches:
        far_future = timeline_cursor + datetime.timedelta(days=7)
        xml_lines.append(f'  <programme start="{format_xmltv_time(timeline_cursor)}" stop="{format_xmltv_time(far_future)}" channel="{channel_id}">')
        xml_lines.append(f'    <title lang="en">No Upcoming Fixture Scheduled</title>')
        xml_lines.append(f'    <desc lang="en">Check back soon for confirmed kickoff times.</desc>')
        xml_lines.append('  </programme>')
        continue

    for match in team_matches:
        utc_dt = datetime.datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        ko_uk = utc_dt.astimezone(UK_TZ)

        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        opponent = away if home == team_name else f"@{home}"
        matchday = match.get("matchday", "")

        event_start = ko_uk - datetime.timedelta(minutes=30)
        event_end = ko_uk + datetime.timedelta(hours=2)

        ko_time_str = ko_uk.strftime("%H:%M")
        ko_date_str = ko_uk.strftime("%a %d %b")

        # 24/7 Gap filler before match
        if event_start > timeline_cursor:
            pre_start_str = format_xmltv_time(timeline_cursor)
            pre_stop_str = format_xmltv_time(event_start)
            
            filler_title = f"Next: vs {opponent} ({ko_date_str} @ {ko_time_str})"
            filler_desc = f"Upcoming: {home} vs {away}. Kickoff at {ko_time_str} UK on {ko_date_str}."

            xml_lines.append(f'  <programme start="{pre_start_str}" stop="{pre_stop_str}" channel="{channel_id}">')
            xml_lines.append(f'    <title lang="en">{escape(filler_title)}</title>')
            xml_lines.append(f'    <desc lang="en">{escape(filler_desc)}</desc>')
            xml_lines.append('  </programme>')

        # Live match window (starts 30m before kickoff)
        match_start_str = format_xmltv_time(max(event_start, timeline_cursor))
        match_stop_str = format_xmltv_time(event_end)
        
        live_title = f"LIVE: {home} vs {away}"
        live_desc = f"Premier League Matchday {matchday} - Kickoff {ko_time_str} UK ({ko_date_str})."

        xml_lines.append(f'  <programme start="{match_start_str}" stop="{match_stop_str}" channel="{channel_id}">')
        xml_lines.append(f'    <title lang="en">{escape(live_title)}</title>')
        xml_lines.append(f'    <desc lang="en">{escape(live_desc)}</desc>')
        xml_lines.append('  </programme>')

        timeline_cursor = event_end

xml_lines.append('</tv>')

with open("pl_epg.xml", "w", encoding="utf-8") as f:
    f.write("\n".join(xml_lines))

print("Successfully generated pl_epg.xml with .epl IDs")
