# NBA Player Prop Analysis Tool

This project is an interactive NBA player prop analysis tool that helps evaluate
over/under betting performance using historical game data.

It allows users to select a player, stat, opponent, season, and betting line,
then instantly see:
- Recent game performance
- Over vs under hit rates
- A color-coded bar chart showing results by game

This tool is designed for data-driven sports betting analysis and exploratory modeling.

---

## Features

- Pulls official NBA player game logs using `nba_api`
- Supports multiple seasons (2019–20 through 2025–26)
- Interactive dropdowns and filters using Jupyter widgets
- Custom stat selection:
  - Points
  - Rebounds
  - Assists
  - PRA, PR, PA, RA
  - Shooting and advanced combo stats
- Over/Under hit rate calculation for any betting line
- Visual bar chart:
  - Green = Over the line
  - Red = Under the line
- Matchup and date displayed for each game

---

## How It Works (High Level)

1. NBA game logs are downloaded season by season.
2. All seasons are combined into one dataset.
3. Stats are cleaned and converted to numeric values.
4. Composite stats (PRA, PR, etc.) are calculated.
5. Filters are applied based on user selections.
6. The selected stat is compared against a betting line.
7. Results are displayed in both table and chart form.

---

## Tech Stack

- Python
- Jupyter Notebook
- pandas
- numpy
- matplotlib
- nba_api
- ipywidgets

