import time
from datetime import datetime
import json
import pytz


def OBC_cumulative_reset_content(cumulative_reset_doc):
    satellitecode = cumulative_reset_doc['_satelliteCode']
    timefound = cumulative_reset_doc['time_found']
    timeend = cumulative_reset_doc['time_end']

    # Define Asia/Shanghai timezone
    shanghai_tz = pytz.timezone('Asia/Shanghai')

    # Convert float timestamp to datetime object
    timefound_datetime = datetime.fromtimestamp(timefound, shanghai_tz)
    timeend_datetime = datetime.fromtimestamp(timeend, shanghai_tz)
    # Get formatted time string
    timefound_str = timefound_datetime.strftime("%Y-%m-%d %H:%M:%S")
    timeend_str = timeend_datetime.strftime("%Y-%m-%d %H:%M:%S")

    cumulative_count = cumulative_reset_doc['cumulative_count']
    # Get current timestamp (13 digits)
    current_timestamp = int(time.time() * 1000)

    # Get current time in the desired format
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    body = f'''{{
        "type": "telemetry_data",
        "code": "Satellite_Reset_Count",
        "objectType": "satellite",
        "objectId": "1",
        "objectName": "{satellitecode}",
        "ruleName": "",
        "eventTime": {current_timestamp},
        "params": {{
            "eventObjectType": "satellite",
            "eventObjectId": "1",
            "eventObjectName": "{satellitecode}",
            "param": {{
                "resetCount": {cumulative_count},
                "timefound": "{timefound_str}",
                "timeend": "{timeend_str}"
            }},
            "eventTimeStr": "{current_time_str}",
            "eventTime": {current_timestamp},
            "eventCode": "Satellite_Reset_Count",
            "eventName": "累计复位计数",
            "eventDesc": "",
            "eventLevel": "INFO"
        }}
    }}'''
    return body


# def od_precision_content(orbit_precision_summary, imgurl):
#     # orbit_precision_summary.pop('a', None)
#     # orbit_precision_summary.pop('e', None)
#     # orbit_precision_summary.pop('i', None)
#     # orbit_precision_summary.pop('dw', None)
#     # orbit_precision_summary.pop('xw', None)
#     # orbit_precision_summary.pop('M', None)
#     # orbit_precision_summary.pop('thrust', None)
#     # orbit_precision_summary.pop('isValid', None)
#     # orbit_precision_summary.pop('timestamp', None)
#     keys_to_remove = ['a', 'e', 'i', 'dw', 'xw', 'M', 'thrust', 'isValid', 'timestamp']
#     for key in keys_to_remove:
#         orbit_precision_summary.pop(key, None)
#
#     # Round float values to 3 decimal places
#     keys_to_round = ['CD', 'residual', 'mse', 'hour_error', 'max_error', '3hr_err', '6hr_err', '12hr_err', '18hr_err']
#     for key in keys_to_round:
#         if key in orbit_precision_summary and isinstance(orbit_precision_summary[key], float):
#             orbit_precision_summary[key] = round(orbit_precision_summary[key], 3)
#     satellitecode = orbit_precision_summary['spacecraft']
#     # Renaming the keys in the original dictionary
#     orbit_precision_summary["err3h"] = orbit_precision_summary.pop("3hr_err")
#     orbit_precision_summary["err6h"] = orbit_precision_summary.pop("6hr_err")
#     orbit_precision_summary["err12h"] = orbit_precision_summary.pop("12hr_err")
#     orbit_precision_summary["err18h"] = orbit_precision_summary.pop("18hr_err")
#
#     # Get current timestamp (13 digits)
#     current_timestamp = int(time.time() * 1000)
#     # epochTimeUTC = orbit_precision_summary['epochTimeUTC']
#     orbit_precision_summary_json = json.dumps(orbit_precision_summary)
#
#     ops = str(orbit_precision_summary_json).replace("{", "").replace("}", "")
#
#     # Get current time in the desired format
#     current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
#     body = f'''{{
#     "type": "telemetry_data",
#     "code": "Satellite_Orbital_Accuracy_Update",
#     "objectType": "satellite",
#     "objectId": "1",
#     "objectName": "{satellitecode}",
#     "ruleName": "",
#     "eventTime": {current_timestamp},
#     "params": {{
#         {ops},
#         "img": "{imgurl}"
#         }}
#     }}'''
#     return body


def spiderling_daily_report_content(imgurl):
    # Get current timestamp and convert to Beijing time
    current_timestamp = int(time.time() * 1000)
    now = datetime.fromtimestamp(current_timestamp / 1000, pytz.timezone('Asia/Shanghai'))

    # Determine time-of-day tag
    hour = now.hour
    if 0 <= hour < 12:
        timeofdayoneword = "早上"
    else:
        timeofdayoneword = "晚上"

    current_date = now.strftime("%Y-%m-%d")

    return {
        "System": "fca3",
        "NoticeCode": "spiderling_flight_control_report",
        "type": "markdown",
        "Param": {
            "reportlink": imgurl,
            "currentdate": current_date,
            "timeofdayoneword": timeofdayoneword,
        }
    }
