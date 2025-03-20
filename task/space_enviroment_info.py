import requests
import datetime
import time


def iso_to_unix_ms(iso_time):

    if not iso_time:  # If empty, return as is
        return ""

    # Convert ISO time to Unix timestamp (seconds) and then to milliseconds
    dt = datetime.datetime.strptime(iso_time, "%Y-%m-%dT%H:%M:%S.%fZ")
    return int(time.mktime(dt.timetuple()) * 1000)


def space_environment_info_with_summary_from_odpa(odpa3_url, tf1, tf2):

    space_environment_info_with_summary_from_odpa_url = f"{odpa3_url}/space-environment-info-with-summary"

    # Convert timestamps or keep them empty if they are already empty
    payload = {
        "start": iso_to_unix_ms(tf1),
        "end": iso_to_unix_ms(tf2)
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(space_environment_info_with_summary_from_odpa_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
        return None
