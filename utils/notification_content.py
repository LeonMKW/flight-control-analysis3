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


def od_precision_content(orbit_precision_summary):
    orbit_precision_summary.pop('a', None)
    orbit_precision_summary.pop('e', None)
    orbit_precision_summary.pop('i', None)
    orbit_precision_summary.pop('dw', None)
    orbit_precision_summary.pop('xw', None)
    orbit_precision_summary.pop('M', None)
    orbit_precision_summary.pop('thrust', None)
    orbit_precision_summary.pop('isValid', None)
    orbit_precision_summary.pop('timestamp', None)

    satellitecode = orbit_precision_summary['spacecraft']
    # Get current timestamp (13 digits)
    current_timestamp = int(time.time() * 1000)
    epochTimeUTC = orbit_precision_summary['epochTimeUTC']

    # Get current time in the desired format
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
    body = f'''{{
    "type": "telemetry_data",
    "code": "Satellite_Orbital_Accuracy_Update",
    "objectType": "satellite",
    "objectId": "1",
    "objectName": "GS-2AP02",
    "ruleName": "",
    "eventTime": 1714982307298,
    "params": {{
        "a": 6888039.9320658,
        "e": 0.0068392903074478,
        "i": 63.440064231145,
        "dw": 350.75765993486,
        "xw": 344.99186253841,
        "M": 333.43692458386,
        "CD": 19.769662302768,
        "remark": "无动力-自动定轨",
        "gnssCount": 718,
        "residual": 23.7182,
        "type": "Gnss",
        "epochTimeUTC": "2024-05-13T01:25:38.000Z",
        "id": 25142,
        "thrust": 0.0,
        "isValid": 1,
        "spacecraft": "GS-2AP02",
        "timestamp": 1715563538,
        "mse": 7.194813179582931,
        "hour_error": 7.0384115390479565,
        "max_error": 40.07423050515354,
        "beijing_time": "2024-05-13 09:25:38",
        "img": "{111111}"
    }}
}}'''
    return body


