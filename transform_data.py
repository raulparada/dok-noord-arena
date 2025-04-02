import csv
from datetime import datetime

from main import Match, Outcome, to_csv

# Input and output file paths
input_file = "misc/data-database.csv"


# Function to parse and transform data
def transform_data(input_file):
    with open(input_file, "r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile, delimiter=";")
        matches_by_date = {}

        for row in reader:
            matches = matches_by_date.setdefault(row.get("Date"), [])
            if matches:
                match = matches[-1]
                winners = match.setdefault("winners", [])
                losers = match.setdefault("losers", [])
                if len(winners) + len(losers) == 10:
                    match = {}
                    matches.append(match)
                    winners = match.setdefault("winners", [])
                    losers = match.setdefault("losers", [])
            else:
                match = {}
                matches.append(match)
                winners = match.setdefault("winners", [])
                losers = match.setdefault("losers", [])

            player = row.get("Player")
            if player == "Pablo OG":
                player = "Pablo"
            elif player.lower() == "pablo p":
                player = "PabloP"
            elif player == "Sandero":
                player = "Sander"
            elif player.lower() == "jo han":
                player = "Johan"

            result = row.get("Result")
            if result == "W":
                winners.append(player)
            elif result == "L":
                losers.append(player)

        for date, matches in matches_by_date.items():
            for match in matches:
                date_old = datetime.strptime(date, "%d/%m/%Y")
                # Convert date to ISO 8601 format
                date_new = date_old.strftime("%Y-%m-%dT20:00")
                match_new = Match(
                    date=date_new,
                    team_1="[white]" + "_".join(p.lower() for p in match["winners"]),
                    team_2="[black]" + "_".join(p.lower() for p in match["losers"]),
                    outcome=Outcome.TEAM_1_WINNER,
                    recording_id=None,
                )
                print(match_new)
                to_csv(match_new, "data/matches-new")


if __name__ == "__main__":
    # Run the transformation
    transform_data(input_file)
    print("Data has been transformed and saved")
