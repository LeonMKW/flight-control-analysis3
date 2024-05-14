import time
from datetime import datetime


def OBC_cumulative_reset_content(cumulative_reset_doc):
    satellitecode = cumulative_reset_doc['_satelliteCode']
    timefound = cumulative_reset_doc['time_found']
    timeend = cumulative_reset_doc['time_end']
    # Convert float timestamp to datetime object
    timefound_datetime = datetime.fromtimestamp(timefound)
    timeend_datetime = datetime.fromtimestamp(timeend)
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

def od_precision_content()