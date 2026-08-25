import requests
import datetime
from xml.sax.saxutils import escape

API_KEY = "185f668365a14c6dade238bd621d5a13"  # Replace with your API token
PL_COMPETITION_ID = "PL"

headers = {"X-Auth-Token": API_KEY}
url = f"https://api.football-data.org/v4/competitions/{PL_COMPETITION_ID}/matches?status=SCHEDULED,TIMED"

response = requests.get(url, headers=headers)
data = response.json()

matches = data.get("matches", [])

# Collect all teams
teams = {}
for m in matches:
    home = m["homeTeam"]["name"]
    away = m["awayTeam"]["name"]
    for t in [home, away]:
        if t not in teams:
            team_id = t.lower().replace(" ", "").replace("fc", "").strip()
            teams[t] = team_id

xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="PL-Fixture-EPG">']

# Channel Definitions
for name, team_id in teams.items():
    xml_lines.append(f'  <channel id="{team_id}.pl">')
    xml_lines.append(f'    <display-name>{escape(name)}</display-name>')
    xml_lines.append('  </channel>')

# Program Schedules
for team_name, team_id in teams.items():
    team_matches = [m for m in matches if m["homeTeam"]["name"] == team_name or m["awayTeam"]["name"] == team_name]
    
    for match in team_matches:
        utc_str = match["utcDate"].replace("Z", "+0000")
        match_time = datetime.datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        start_str = match_time.strftime("%Y%m%d%H%M%S +0000")
        end_time = match_time + datetime.timedelta(hours=2)
        stop_str = end_time.strftime("%Y%m%d%H%M%S +0000")
        
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        opponent = away if home == team_name else f"@{home}"
        stage = match.get("matchday", "")
        title = f"Live: {home} vs {away}"
        desc = f"Premier League Matchday {stage} - Kickoff at {match_time.strftime('%H:%M UTC on %d %b %Y')}"
        
        xml_lines.append(f'  <programme start="{start_str}" stop="{stop_str}" channel="{team_id}.pl">')
        xml_lines.append(f'    <title lang="en">{escape(title)}</title>')
        xml_lines.append(f'    <desc lang="en">{escape(desc)}</desc>')
        xml_lines.append('  </programme>')

xml_lines.append('</tv>')

with open("pl_epg.xml", "w", encoding="utf-8") as f:
    f.write("\n".join(xml_lines))
