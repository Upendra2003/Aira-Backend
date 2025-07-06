import gspread
from google.oauth2.service_account import Credentials
import os
import json

def append_to_google_sheet(data_dict):
    # Define the scope
    scope = ["https://spreadsheets.google.com/feeds", 
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]

    # Load credentials from environment variable
    creds_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)

    # Authorize client
    client = gspread.authorize(credentials)

    # Open your sheet
    sheet = client.open("AIRA_Assessments").sheet1

    # Format data
    row_data = [
        data_dict["name"],
        data_dict["age"],
        data_dict["gender"],
        data_dict["occupation"],
        data_dict.get("income", ""),
        data_dict["education"],
        data_dict["hobbies"],
        *data_dict["assessment"]["answers"],
        data_dict["assessment"]["score"],
        data_dict["assessment"]["mental_state"],
        *data_dict["reflections"]["questions"]
    ]

    # Append the row
    sheet.append_row(row_data)
