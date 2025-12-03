# Copilot Team Usage

## Overview

This section of the project leverages GitHub OAuth2 for user authentication, granting access to essential data.

The tech stack and UI is the same as the Organization Usage.

### Requirements for Team Copilot Usage

To retrieve data, a team must meet the following criteria:

- At least 5 members with active Copilot licenses.
- These 5 users must be active for a minimum of 1 day.

## Access

### Flow & Session

When on the team usage page, a `Login with GitHub` is displayed. Once clicked on, the user is taken to GitHub's authorisation page. The permissions **read-only** personal user data and **read-only** organizations and teams are required for this application. Clicking on the green `Authorize` button takes the user back to the application.

The session is saved to streamlit's `session_state`. For security, the session resets after refresh but not when navigating between pages. This means the user has to press the `Login with GitHub` button each page refresh.

### Types of Access

#### Regular User

A user within ONSDigital. Upon authentication, the app identifies the teams they belong to and populates the selection box accordingly. If the user is part of a qualifying team, they can view the data. Users not associated with any team cannot select teams.

#### Admin User

An enhanced regular user with the ability to search for any team. This user belongs to a specific whitelisted team, enabling them to view metrics for any team that meets the Copilot usage data requirements.

## Metrics

### Team History Metrics

The team history metrics function retrieves historical usage data for each team identified with Copilot usage. This data includes detailed metrics about the team's activity over time. New data for a team is fetched only from the last captured date in the file.

#### Functionality

- **Input**: The function in addition to the GitHub Client takes a team name, organisation and the optional "since" as a query parameter as input.
- **Process**:
  - Fetches historical data for the specified team using the GitHub API.
  - If the since query parameter exist then fetch data only after the specified date.
  - Filters and organizes the data into a structured format.
- **Output**: A JSON object containing the team's historical metrics, including:
  - Team name
  - Activity data
  - Copilot usage statistics

#### Usage

The historical metrics are stored in an S3 bucket as a json file (`teams_history.json`).

#### Example

For a team named `kehdev`, the historical metrics might include:

```json
{
  "team": {
    "name": "kehdev",
    "slug": "kehdev",
    "description": "Team responsible for CI/CD pipelines",
    "url": "https://github.com/orgs/<organisation>/teams/kehdev"
  },
  "data": [
    {
      "date": "2025-07-01",
      "active_members": 10,
      "copilot_usage_hours": 50
    },
    {
      "date": "2025-07-02",
      "active_members": 12,
      "copilot_usage_hours": 60
    }
  ]
}
```
