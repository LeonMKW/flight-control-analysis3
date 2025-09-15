# -*- coding: UTF-8 -*-
import logging
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from utils.flightcontrol_utils import vcIdnew, get_task_list, commands, correctframe, uplock, obc_resetnew, payload_pwr, \
    file_inspect, \
    electric_propulsion, monitor_data, orbit_data, experimental_lock_data, experimental_telemetry_data, \
    hist_interval_data, gnss_interval_data
from tqdm import tqdm
from utils.db import set_value, init_val
from data.fileinspection import map_dict
from utils.core_algorithm import analyze_lock_intervals, analyze_lock_status, analyze_telemetry_intervals, \
    calculate_hist_interval, calculate_gnss_interval

from utils.ASsatellitestatus_utils import get_AScommands, get_AS02_datatransmission, get_AS02_hist_data_save, \
    get_AS03_in_sight_sensing_task_data, get_AS03_out_sight_sensing_task_data, get_AS03_hist_data_save
from utils.flightcontrol_utils import get_task_list

logger = logging.getLogger(__name__)


def AS02_sensing_upload(post_token_url,
                        post_token_user_name,
                        post_token_password,
                        metedataservice_url,
                        _influxdb,
                        client,
                        tf1,
                        tf2,
                        satID,
                        mongo_collection=None):
    """
    - 新版：文件号从 TCKAF06.packageForm.params.record1..record8 读取
    - 新增：solar_angle 仅保存成区间字符串（如 "50-60"）
    - 保留：TCKBB02 取消逻辑 (v0==4369 且在 TCKAF06 后 300s 内)
    - 若提供 mongo_collection，则将每条 doc 落库；同时返回 JSON 字符串
    """
    import json
    import pandas as pd

    # --- helpers ---
    def hex_to_int(x):
        try:
            if isinstance(x, str) and x.lower().startswith("0x"):
                return int(x, 16)
            return int(x)
        except (ValueError, TypeError):
            return None

    def str_to_num(x):
        try:
            if isinstance(x, (int, float)):
                return x
            if isinstance(x, str) and '.' in x:
                return float(x)
            return int(x)
        except (ValueError, TypeError):
            return None

    # 太阳高度角映射：只返回纯区间字符串
    SOLAR_ANGLE_MAP = {
        "0x1111": "20-30",
        "0x2222": "30-40",
        "0x3333": "40-50",
        "0x4444": "50-60",
        "0x5555": "60-70",
    }

    def decode_solar_angle(val):
        if isinstance(val, str):
            # 统一小写键
            key = val.lower()
            # 我们的字典是小写键
            return SOLAR_ANGLE_MAP.get(key, None) if key.startswith("0x") else SOLAR_ANGLE_MAP.get(val, None)
        return None

    # 拉取窗口内命令
    AS02_commands = get_AScommands(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   metedataservice_url,
                                   _influxdb,
                                   client,
                                   tf1,
                                   tf2,
                                   satID)

    if not isinstance(AS02_commands, pd.DataFrame) or AS02_commands.empty:
        return "[]"

    TCKAF06_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF06']
    TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']

    # 取消逻辑：v0==4369
    def is_cancel_task(param_str):
        try:
            param = json.loads(param_str)
            return param.get('packageForm', {}).get('params', {}).get('v0') == 4369
        except Exception:
            return False

    results = []

    for _, row in TCKAF06_commands.iterrows():
        t_time = row.get('timestamp', None)
        if t_time is None:
            continue

        # 检查 300s 取消
        cancel = TCKBB02_commands[
            (TCKBB02_commands['timestamp'] > t_time) &
            (TCKBB02_commands['timestamp'] <= t_time + 300) &
            (TCKBB02_commands['param'].apply(is_cancel_task))
            ]
        if not cancel.empty:
            continue

        # 解析 TCKAF06
        try:
            payload = json.loads(row['param'])
        except Exception:
            continue

        pkg = payload.get('packageForm', {}) or {}
        params = pkg.get('params', {}) or {}

        # ---- 在任何可能 continue 之前，先把 files 定义好，避免 UnboundLocal ----
        files = {
            'file1': params.get('record1'),
            'file2': params.get('record2'),
            'file3': params.get('record3'),
            'file4': params.get('record4'),
            'file5': params.get('record5'),
            'file6': params.get('record6'),
            'file7': params.get('record7'),
            'file8': params.get('record8'),
        }

        # 影像参数
        start1 = str_to_num(params.get('start1'))
        end1 = str_to_num(params.get('end1'))
        pitch1 = str_to_num(params.get('pitch1'))
        camera_state = hex_to_int(params.get('camera_state'))
        scan_mode = hex_to_int(params.get('scan_mode'))
        solar_angle = decode_solar_angle(params.get('solar_angle'))  # 只返回 "50-60" 这类字符串

        if start1 is None:
            # 关键索引缺失，跳过
            continue

        # 去重：任一已有任务 start1 在 60s 内视为重复
        if any(abs(start1 - x['TCKAF06']['start1']) < 60 for x in results):
            continue

        doc = {
            'TCKAF06': {
                'timestamp': t_time,
                'start1': start1,
                'end1': end1,
                'pitch1': pitch1,
                'camera_state': camera_state,
                'scan_mode': scan_mode,
                'solar_angle': solar_angle  # 例如 "50-60"
            },
            # 为了兼容旧结构，仍然导出 TCS801 字段（来源已变为 TCKAF06）
            'TCS801': {
                'timestamp': t_time,
                **files
            }
        }

        # 可加卫星代号，便于检索
        sat_code = payload.get('satelliteCode')
        if sat_code:
            doc['satellite_code'] = sat_code

        results.append(doc)

        # 若提供 collection，则落库
        if mongo_collection is not None:
            try:
                mongo_collection.insert_one(doc)
            except Exception:
                # 可以在此记录日志，但不要打断整体流程
                pass

    return json.dumps(results, ensure_ascii=False)


# def AS02_payload_data_transmission(post_token_url,
#                                    post_token_user_name,
#                                    post_token_password,
#                                    metedataservice_url,
#                                    _influxdb_input,
#                                    client_input,
#                                    influxdb_action,
#                                    host_action,
#                                    tf1,
#                                    tf2,
#                                    satID):
#     # Helper function to convert hex strings to integers
#     def hex_to_int(hex_str):
#         try:
#             if isinstance(hex_str, str) and hex_str.startswith("0x"):
#                 return int(hex_str, 16)
#             else:
#                 return int(hex_str)
#         except (ValueError, TypeError):
#             return None
#
#     # Helper function to convert numerical strings to int or float
#     def str_to_num(num_str):
#         try:
#             if isinstance(num_str, str):
#                 num_str = num_str.strip()
#                 if num_str.startswith("0x"):
#                     return hex_to_int(num_str)
#                 elif '.' in num_str:
#                     return float(num_str)
#                 else:
#                     return int(num_str)
#             else:
#                 return num_str  # If it's already a number
#         except (ValueError, TypeError):
#             return None
#
#     # Retrieve the command data
#     AS02_payloaddatatransmission = get_AS02_datatransmission(post_token_url,
#                                                              post_token_user_name,
#                                                              post_token_password,
#                                                              metedataservice_url,
#                                                              _influxdb_input,
#                                                              client_input,
#                                                              tf1,
#                                                              tf2,
#                                                              satID)
#
#     # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
#     AS02_payloaddatatransmission = AS02_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])
#
#     # Initialize list to store the results
#     payload_transmission_data = []
#
#     # Iterate over each TMK2014 and TMK2015 pair
#     for _, payload_row in AS02_payloaddatatransmission.iterrows():
#         TMK2014 = payload_row['TMK2014']
#         TMK2015 = payload_row['TMK2015']
#
#         if TMK2014 != 0 and TMK2015 != 0:
#             duration = TMK2015 - TMK2014
#
#             # Calculate the start time for querying commands (48 hours before TMK2014)
#             start_time = int(TMK2014 - 48 * 3600)
#             end_time = int(TMK2014)
#
#             # Convert start_time and end_time to datetime strings
#             start_time_str = pd.to_datetime(start_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
#             end_time_str = pd.to_datetime(end_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
#
#             # Retrieve the command data for the specific time range
#             AS02_commands = get_AScommands(post_token_url,
#                                            post_token_user_name,
#                                            post_token_password,
#                                            metedataservice_url,
#                                            influxdb_action,
#                                            host_action,
#                                            tf1=start_time_str,
#                                            tf2=end_time_str,
#                                            satID=satID)
#
#             # Filter for relevant commands
#             TCKAF03_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03']
#             TCS804_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS804']
#             TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']
#
#             # Find TCKAF03 commands with start equal to TMK2014
#             def is_matching_tckaf03(param_str):
#                 try:
#                     param = json.loads(param_str)
#                     start = str_to_num(param.get('packageForm', {}).get('params', {}).get('start'))
#                     return start == TMK2014
#                 except json.JSONDecodeError:
#                     return False
#
#             matching_tckaf03 = TCKAF03_commands[TCKAF03_commands['param'].apply(is_matching_tckaf03)]
#
#             if not matching_tckaf03.empty:
#                 tckaf03_row = matching_tckaf03.iloc[0]
#                 tckaf03_time = tckaf03_row['timestamp']
#                 try:
#                     tckaf03_params = json.loads(tckaf03_row['param'])
#                 except json.JSONDecodeError:
#                     continue  # Skip this iteration if JSON is invalid
#
#                 # Check for TCKBB02 commands between TCKAF03's timestamp and TMK2014
#                 def is_matching_tckbb02(param_str):
#                     try:
#                         param = json.loads(param_str)
#                         v0 = str_to_num(param.get('packageForm', {}).get('params', {}).get('v0'))
#                         return v0 == 17476
#                     except json.JSONDecodeError:
#                         return False
#
#                 matching_tckbb02 = TCKBB02_commands[
#                     (TCKBB02_commands['timestamp'] > tckaf03_time) &
#                     (TCKBB02_commands['timestamp'] <= TMK2014) &
#                     (TCKBB02_commands['param'].apply(is_matching_tckbb02))
#                     ]
#
#                 # If TCKBB02 with v0 == 17476 is found, ignore this task group
#                 if not matching_tckbb02.empty:
#                     continue
#
#                 # Find TCS804 commands within 60 seconds after the TCKAF03 time
#                 matching_tcs804 = TCS804_commands[
#                     (TCS804_commands['timestamp'] > tckaf03_time) &
#                     (TCS804_commands['timestamp'] <= tckaf03_time + 60)
#                     ]
#
#                 if matching_tcs804.empty:
#                     continue
#
#                 tcs804_list = []
#                 for _, tcs804_row in matching_tcs804.iterrows():
#                     try:
#                         tcs804_params = json.loads(tcs804_row['param'])
#                     except json.JSONDecodeError:
#                         continue  # Skip this row if JSON is invalid
#
#                     # Extract and convert File1, File2, and Port
#                     file_params = tcs804_params.get('packageForm', {}).get('params', {})
#                     file1 = str_to_num(file_params.get('File1'))
#                     file2 = str_to_num(file_params.get('File2'))
#                     port = str_to_num(file_params.get('Port'))
#
#                     tcs804_list.append({
#                         'timestamp': tcs804_row['timestamp'],
#                         'File1': file1,
#                         'File2': file2,
#                         'Port': port
#                     })
#
#                 # Parse and convert TCKAF03 params
#                 tckaf03_package = tckaf03_params.get('packageForm', {})
#                 tckaf03_params_dict = tckaf03_package.get('params', {})
#
#                 altqka1 = str_to_num(tckaf03_params_dict.get('altqka1'))
#                 altqka2 = str_to_num(tckaf03_params_dict.get('altqka2'))
#                 altqka3 = str_to_num(tckaf03_params_dict.get('altqka3'))
#                 count = str_to_num(tckaf03_params_dict.get('count'))
#                 latka1 = str_to_num(tckaf03_params_dict.get('latka1'))
#                 latka2 = str_to_num(tckaf03_params_dict.get('latka2'))
#                 latka3 = str_to_num(tckaf03_params_dict.get('latka3'))
#                 lonka1 = str_to_num(tckaf03_params_dict.get('lonka1'))
#                 lonka2 = str_to_num(tckaf03_params_dict.get('lonka2'))
#                 lonka3 = str_to_num(tckaf03_params_dict.get('lonka3'))
#                 start = str_to_num(tckaf03_params_dict.get('start'))
#                 time1 = str_to_num(tckaf03_params_dict.get('time1'))
#                 time2 = str_to_num(tckaf03_params_dict.get('time2'))
#                 time3 = str_to_num(tckaf03_params_dict.get('time3'))
#
#                 # Ensure required fields are valid
#                 if start is None:
#                     continue  # Skip if 'start' is invalid
#
#                 payload_transmission_data.append({
#                     'TMK2014': TMK2014,
#                     'TMK2015': TMK2015,
#                     'duration': duration,
#                     'TCKAF03': {
#                         'timestamp': tckaf03_time,
#                         'params': {
#                             'altqka1': altqka1,
#                             'altqka2': altqka2,
#                             'altqka3': altqka3,
#                             'count': count,
#                             'latka1': latka1,
#                             'latka2': latka2,
#                             'latka3': latka3,
#                             'lonka1': lonka1,
#                             'lonka2': lonka2,
#                             'lonka3': lonka3,
#                             'start': start,
#                             'time1': time1,
#                             'time2': time2,
#                             'time3': time3
#                         }
#                     },
#                     'TCS804': tcs804_list
#                 })
#
#     result = json.dumps(payload_transmission_data, ensure_ascii=False)
#     return result


def AS02_payload_data_transmission(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   metedataservice_url,
                                   _influxdb_input,
                                   client_input,
                                   influxdb_action,
                                   host_action,
                                   tf1,
                                   tf2,
                                   satID):
    """
    New logic (order-robust, schedule-based):
      - Find all TCKAF03/TCS804/TCKBB02 in [tf1, tf2] for satID.
      - For each TCKAF03:
          * start_s = TCKAF03.packageForm.params.start   (seconds)
          * duration = TCKAF03.packageForm.params.time1  (seconds)
          * Belonging TCS804 = those with:
              - delayForm.isDelay == true
              - |to_ts(delayForm.seconds) - start_s| <= 20 minutes
          * If none, still output a record with a single TCS804 {File1=0, File2=0, Port=0}
          * If a TCKBB02(v0==17476) exists in (send_ts_of_this_TCKAF03, next_TCKAF03_send_ts or tf2], drop this task
      - Dedupe TCS804 across tasks using commandId (fallback to row index)
    """

    # ---------------- Helpers ----------------
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.strip().lower().startswith("0x"):
                return int(hex_str, 16)
            return int(hex_str)
        except (ValueError, TypeError):
            return None

    def str_to_num(v):
        try:
            if isinstance(v, str):
                s = v.strip()
                if s.lower().startswith("0x"):
                    return hex_to_int(s)
                if '.' in s:
                    return float(s)
                return int(s)
            return v
        except (ValueError, TypeError):
            return None

    def safe_json_loads(maybe_json):
        if isinstance(maybe_json, dict):
            return maybe_json
        if isinstance(maybe_json, str):
            try:
                return json.loads(maybe_json)
            except json.JSONDecodeError:
                return None
        return None

    def to_bool(x):
        if isinstance(x, bool):
            return x
        if isinstance(x, str):
            return x.strip().lower() in ("true", "1", "yes", "y")
        if isinstance(x, (int, float)):
            return x != 0
        return False

    def parse_iso_to_ts(iso_str):
        try:
            if not iso_str:
                return None
            return float(pd.to_datetime(iso_str, utc=True).timestamp())
        except Exception:
            return None

    # Right boundary for last-window (for TCKBB02 rule)
    try:
        tf2_sec = pd.to_datetime(tf2, utc=True).timestamp() if isinstance(tf2, str) else float(tf2)
    except Exception:
        tf2_sec = None

    # ---------------- Load commands ----------------
    AS02_commands = get_AScommands(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   metedataservice_url,
                                   influxdb_action,
                                   host_action,
                                   tf1=tf1,
                                   tf2=tf2,
                                   satID=satID)
    # print(AS02_commands.to_string())

    if AS02_commands is None or len(AS02_commands) == 0:
        return json.dumps([], ensure_ascii=False)

    # Filter by cmd_code
    TCKAF03_df = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03'].copy()
    TCS804_df = AS02_commands[AS02_commands['cmd_code'] == 'TCS804'].copy()
    TCKBB02_df = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02'].copy()

    # Sort TCKAF03 by send timestamp for windowing TCKBB02
    if 'timestamp' in TCKAF03_df.columns:
        TCKAF03_df = TCKAF03_df.sort_values('timestamp').reset_index(drop=True)

    # Pre-extract list of TCKAF03 items with both send_ts and start_s
    tckaf03_items = []
    for _, row in TCKAF03_df.iterrows():
        send_ts = row.get('timestamp')
        pobj = safe_json_loads(row.get('param')) if 'param' in row else None
        if not pobj:
            continue
        pf = pobj.get('packageForm', {}) if isinstance(pobj, dict) else {}
        p = pf.get('params', {}) if isinstance(pf, dict) else {}
        start_s = str_to_num(p.get('start'))
        duration = str_to_num(p.get('time1'))  # seconds
        if start_s is None:
            # If start is missing, we can still output (but matching will likely be none)
            start_s = None
        tckaf03_items.append({
            'row': row,
            'send_ts': send_ts,
            'start_s': start_s,
            'duration': duration,
            'params': {
                'altqka1': str_to_num(p.get('altqka1')),
                'altqka2': str_to_num(p.get('altqka2')),
                'altqka3': str_to_num(p.get('altqka3')),
                'count': str_to_num(p.get('count')),
                'latka1': str_to_num(p.get('latka1')),
                'latka2': str_to_num(p.get('latka2')),
                'latka3': str_to_num(p.get('latka3')),
                'lonka1': str_to_num(p.get('lonka1')),
                'lonka2': str_to_num(p.get('lonka2')),
                'lonka3': str_to_num(p.get('lonka3')),
                'start': start_s,
                'time1': duration,
                'time2': str_to_num(p.get('time2')),
                'time3': str_to_num(p.get('time3')),
            }
        })

    # Build a sorted list of send_ts for TCKBB02 windowing
    tckaf03_send_times = [it['send_ts'] for it in tckaf03_items]
    tckaf03_send_times_sorted = sorted([ts for ts in tckaf03_send_times if isinstance(ts, (int, float))])

    def next_send_after(curr_send):
        if curr_send is None:
            return None
        for ts in tckaf03_send_times_sorted:
            if ts > curr_send:
                return ts
        return None

    # Pre-index all TCS804 with their delay info
    # We keep original send 'timestamp' for output; use delayForm.seconds only for matching
    tcs804_index = []  # list of dicts; each has uniq_id, send_ts, delayed_ts, file1, file2, port, whole row (optional)
    for i, row in TCS804_df.reset_index(drop=True).iterrows():
        send_ts = row.get('timestamp')
        pobj = safe_json_loads(row.get('param')) if 'param' in row else None
        # delay info generally lives at top-level in source JSON; many pipelines pack it into 'param'
        delay_form = None
        if pobj and isinstance(pobj, dict):
            delay_form = pobj.get('delayForm')
        # Fallback: if the row somehow had a 'delayForm' column outside 'param'
        if delay_form is None and 'delayForm' in row:
            delay_form = row.get('delayForm')

        is_delay = to_bool(delay_form.get('isDelay')) if isinstance(delay_form, dict) else False
        delayed_ts = parse_iso_to_ts(delay_form.get('seconds')) if isinstance(delay_form, dict) else None

        # Extract File1/2/Port (not required for matching)
        pform = pobj.get('packageForm', {}) if isinstance(pobj, dict) else {}
        pp = pform.get('params', {}) if isinstance(pform, dict) else {}
        file1 = str_to_num(pp.get('File1'))
        file2 = str_to_num(pp.get('File2'))
        port = str_to_num(pp.get('Port'))

        # Unique id for dedup across tasks
        cmd_id = None
        if isinstance(pobj, dict):
            cmd_id = pobj.get('commandId')
        if not cmd_id and 'commandId' in row:
            cmd_id = row.get('commandId')
        if not cmd_id:
            cmd_id = f"rowidx-{i}"

        tcs804_index.append({
            'uniq_id': cmd_id,
            'send_ts': send_ts,
            'delayed_ts': delayed_ts,
            'is_delay': is_delay,
            'file1': file1,
            'file2': file2,
            'port': port,
        })

    # Dedup usage across tasks
    used_tcs_ids = set()
    TWENTY_MIN = 100 * 60

    results = []

    for it in tckaf03_items:
        send_ts = it['send_ts']
        start_s = it['start_s']
        duration = it['duration']

        # --- TCKBB02 exclusion (same as before): between this send_ts and next TCKAF03 send_ts (or tf2) ---
        def is_matching_tckbb02(param_val):
            obj = safe_json_loads(param_val)
            if not obj:
                return False
            p = obj.get('packageForm', {}).get('params', {})
            v0 = str_to_num(p.get('v0'))
            return v0 == 17476

        right_bound = next_send_after(send_ts)
        if tf2_sec is not None:
            if right_bound is None:
                right_bound = tf2_sec
            else:
                right_bound = min(right_bound, tf2_sec)

        if (isinstance(send_ts, (int, float)) and isinstance(right_bound, (int, float)) and right_bound > send_ts):
            bb02_window = TCKBB02_df[
                (TCKBB02_df['timestamp'] > send_ts) &
                (TCKBB02_df['timestamp'] <= right_bound) &
                (TCKBB02_df['param'].apply(is_matching_tckbb02))
                ]
            if not bb02_window.empty:
                # Abort this task due to TCKBB02(v0==17476)
                continue

        # --- Collect matching TCS804 by scheduled time proximity to start_s ---
        matched = []
        if isinstance(start_s, (int, float)):
            # candidates: isDelay==True AND delayed_ts is not None AND within ±20 minutes of start_s
            cands = [
                t for t in tcs804_index
                if t['is_delay'] and isinstance(t['delayed_ts'], (int, float))
                   and abs(t['delayed_ts'] - start_s) <= TWENTY_MIN
                   and t['uniq_id'] not in used_tcs_ids
            ]
            # Prefer closer ones first (greedy assignment)
            cands.sort(key=lambda t: abs(t['delayed_ts'] - start_s))
            for t in cands:
                matched.append({
                    'timestamp': t['send_ts'],
                    'File1': t['file1'],
                    'File2': t['file2'],
                    'Port': t['port']
                })
                used_tcs_ids.add(t['uniq_id'])

        # If none matched, add a placeholder zero record as requested
        if not matched:
            matched = [{
                'timestamp': None,
                'File1': 0,
                'File2': 0,
                'Port': 0
            }]

        results.append({
            'duration': duration,  # seconds
            'TCKAF03': {
                'timestamp': send_ts,
                'params': it['params']
            },
            'TCS804': matched
        })

    return json.dumps(results, ensure_ascii=False)


def AS02_platform_data_transmission(post_token_url,
                                    post_token_user_name,
                                    post_token_password,
                                    metedataservice_url,
                                    _influxdb_input,
                                    client_input,
                                    influxdb_action,
                                    host_action,
                                    tf1,
                                    tf2,
                                    satID):
    """
    Platform version (TCS813):
      - Order-robust, schedule-based matching by comparing TCS813.delayForm.seconds to TCKAF03.params.start (±20 min).
      - If none matched, keep a placeholder TCS813 (FileNum=0, Port=0).
      - Exclude the task if TCKBB02 with v0==17476 appears after this TCKAF03's send time and before next TCKAF03 (or tf2).
      - duration = TCKAF03.params.time1 (seconds).
    """

    # ---------------- Helpers ----------------
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.strip().lower().startswith("0x"):
                return int(hex_str, 16)
            return int(hex_str)
        except (ValueError, TypeError):
            return None

    def str_to_num(v):
        try:
            if isinstance(v, str):
                s = v.strip()
                if s.lower().startswith("0x"):
                    return hex_to_int(s)
                if '.' in s:
                    return float(s)
                return int(s)
            return v
        except (ValueError, TypeError):
            return None

    def safe_json_loads(maybe_json):
        if isinstance(maybe_json, dict):
            return maybe_json
        if isinstance(maybe_json, str):
            try:
                return json.loads(maybe_json)
            except json.JSONDecodeError:
                return None
        return None

    def to_bool(x):
        if isinstance(x, bool):
            return x
        if isinstance(x, str):
            return x.strip().lower() in ("true", "1", "yes", "y")
        if isinstance(x, (int, float)):
            return x != 0
        return False

    def parse_iso_to_ts(iso_str):
        try:
            if not iso_str:
                return None
            return float(pd.to_datetime(iso_str, utc=True).timestamp())
        except Exception:
            return None

    # Right boundary for last-window (for TCKBB02 rule)
    try:
        tf2_sec = pd.to_datetime(tf2, utc=True).timestamp() if isinstance(tf2, str) else float(tf2)
    except Exception:
        tf2_sec = None

    # ---------------- Load commands ----------------
    AS02_commands = get_AScommands(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   metedataservice_url,
                                   influxdb_action,
                                   host_action,
                                   tf1=tf1,
                                   tf2=tf2,
                                   satID=satID)

    if AS02_commands is None or len(AS02_commands) == 0:
        return json.dumps([], ensure_ascii=False)

    # Filter by cmd_code
    TCKAF03_df = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03'].copy()
    TCS813_df = AS02_commands[AS02_commands['cmd_code'] == 'TCS813'].copy()
    TCKBB02_df = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02'].copy()

    if 'timestamp' in TCKAF03_df.columns:
        TCKAF03_df = TCKAF03_df.sort_values('timestamp').reset_index(drop=True)

    # -------- Prepare TCKAF03 items --------
    tckaf03_items = []
    for _, row in TCKAF03_df.iterrows():
        send_ts = row.get('timestamp')
        pobj = safe_json_loads(row.get('param')) if 'param' in row else None
        if not pobj:
            continue
        pf = pobj.get('packageForm', {}) if isinstance(pobj, dict) else {}
        p = pf.get('params', {}) if isinstance(pf, dict) else {}

        start_s = str_to_num(p.get('start'))  # seconds (scheduled)
        time1_s = str_to_num(p.get('time1'))  # duration seconds

        tckaf03_items.append({
            'row': row,
            'send_ts': send_ts,
            'start_s': start_s,
            'duration': time1_s,
            'params': {
                'altqka1': str_to_num(p.get('altqka1')),
                'altqka2': str_to_num(p.get('altqka2')),
                'altqka3': str_to_num(p.get('altqka3')),
                'count': str_to_num(p.get('count')),
                'latka1': str_to_num(p.get('latka1')),
                'latka2': str_to_num(p.get('latka2')),
                'latka3': str_to_num(p.get('latka3')),
                'lonka1': str_to_num(p.get('lonka1')),
                'lonka2': str_to_num(p.get('lonka2')),
                'lonka3': str_to_num(p.get('lonka3')),
                'start': start_s,
                'time1': time1_s,
                'time2': str_to_num(p.get('time2')),
                'time3': str_to_num(p.get('time3')),
            }
        })

    # For TCKBB02 windowing (send_ts -> next send_ts capped by tf2)
    tckaf03_send_times = sorted([it['send_ts'] for it in tckaf03_items if isinstance(it['send_ts'], (int, float))])

    def next_send_after(curr_send):
        if curr_send is None:
            return None
        for ts in tckaf03_send_times:
            if ts > curr_send:
                return ts
        return None

    # -------- Index TCS813 with delay info --------
    tcs813_index = []
    for i, row in TCS813_df.reset_index(drop=True).iterrows():
        send_ts = row.get('timestamp')
        pobj = safe_json_loads(row.get('param')) if 'param' in row else None

        delay_form = None
        if pobj and isinstance(pobj, dict):
            delay_form = pobj.get('delayForm')
        if delay_form is None and 'delayForm' in row:
            delay_form = row.get('delayForm')

        is_delay = to_bool(delay_form.get('isDelay')) if isinstance(delay_form, dict) else False
        delayed_ts = parse_iso_to_ts(delay_form.get('seconds')) if isinstance(delay_form, dict) else None

        pform = pobj.get('packageForm', {}) if isinstance(pobj, dict) else {}
        pp = pform.get('params', {}) if isinstance(pform, dict) else {}

        # Be tolerant to inconsistent key casing: "FIleNum" vs "FileNum"
        file_num = str_to_num(pp.get('FIleNum')) if 'FIleNum' in pp else str_to_num(
            pp.get('FileNum')) if 'FileNum' in pp else str_to_num(pp.get('fileNum'))
        port = str_to_num(pp.get('Port'))

        cmd_id = None
        if isinstance(pobj, dict):
            cmd_id = pobj.get('commandId')
        if not cmd_id and 'commandId' in row:
            cmd_id = row.get('commandId')
        if not cmd_id:
            cmd_id = f"rowidx-{i}"

        tcs813_index.append({
            'uniq_id': cmd_id,
            'send_ts': send_ts,
            'delayed_ts': delayed_ts,
            'is_delay': is_delay,
            'file_num': file_num,
            'port': port,
        })

    used_tcs_ids = set()
    TWENTY_MIN = 20 * 60

    results = []

    for it in tckaf03_items:
        send_ts = it['send_ts']
        start_s = it['start_s']
        duration = it['duration']

        # ---- TCKBB02 exclusion in (send_ts, next_send] capped by tf2 ----
        def is_matching_tckbb02(param_val):
            obj = safe_json_loads(param_val)
            if not obj:
                return False
            p = obj.get('packageForm', {}).get('params', {})
            v0 = str_to_num(p.get('v0'))
            return v0 == 17476

        right_bound = next_send_after(send_ts)
        if tf2_sec is not None:
            right_bound = right_bound if right_bound is not None else tf2_sec
            right_bound = min(right_bound, tf2_sec)

        if (isinstance(send_ts, (int, float)) and isinstance(right_bound, (int, float)) and right_bound > send_ts):
            bb02_window = TCKBB02_df[
                (TCKBB02_df['timestamp'] > send_ts) &
                (TCKBB02_df['timestamp'] <= right_bound) &
                (TCKBB02_df['param'].apply(is_matching_tckbb02))
                ]
            if not bb02_window.empty:
                continue

        # ---- Match TCS813 to this TCKAF03 by delayed_ts ≈ start_s ----
        matched = []
        if isinstance(start_s, (int, float)):
            cands = [
                t for t in tcs813_index
                if t['is_delay'] and isinstance(t['delayed_ts'], (int, float))
                   and abs(t['delayed_ts'] - start_s) <= TWENTY_MIN
                   and t['uniq_id'] not in used_tcs_ids
            ]
            cands.sort(key=lambda t: abs(t['delayed_ts'] - start_s))
            for t in cands:
                matched.append({
                    'timestamp': t['send_ts'],
                    'FileNum': t['file_num'],
                    'Port': t['port']
                })
                used_tcs_ids.add(t['uniq_id'])

        # No match → placeholder
        if not matched:
            matched = [{
                'timestamp': None,
                'FileNum': 0,
                'Port': 0
            }]

        results.append({
            'duration': duration,  # seconds
            'TCKAF03': {
                'timestamp': send_ts,
                'params': it['params']
            },
            'TCS813': sorted(matched, key=lambda x: (x['timestamp'] is None, x['timestamp']))
        })

    return json.dumps(results, ensure_ascii=False)


def AS02_hist_file_save(post_token_url,
                        post_token_user_name,
                        post_token_password,
                        metedataservice_url,
                        _influxdb_input,
                        client_input,
                        influxdb_action,
                        host_action,
                        tf1,
                        tf2,
                        satID):
    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            return None

    # Retrieve the command data
    AS02hist_file_save_command = get_AScommands(post_token_url,
                                                post_token_user_name,
                                                post_token_password,
                                                metedataservice_url,
                                                influxdb_action,
                                                host_action,
                                                tf1=tf1, tf2=tf2,
                                                satID=satID)

    # Retrieve the telemetry data
    AS02hist_file_save_telemetry = get_AS02_hist_data_save(post_token_url,
                                                           post_token_user_name,
                                                           post_token_password,
                                                           metedataservice_url,
                                                           _influxdb_input,
                                                           client_input,
                                                           tf1, tf2,
                                                           satID)
    # print(AS02hist_file_save_telemetry.to_string())

    # Filter for relevant commands
    TCS811_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS811']
    TCS812_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCS812']
    TCH209_commands = AS02hist_file_save_command[AS02hist_file_save_command['cmd_code'] == 'TCH209']

    # Initialize list to store the results
    hist_file_save_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS811 command
    for _, tcs811_row in TCS811_commands.iterrows():
        tcs811_time = tcs811_row['timestamp']
        try:
            tcs811_params = json.loads(tcs811_row['param'])
        except json.JSONDecodeError:
            continue  # Skip this iteration if JSON is invalid

        # Extract and convert 'FIle' and 'Channel' parameters
        package_params = tcs811_params.get('packageForm', {}).get('params', {})
        tcs811_file_str = package_params.get('FIle')
        tcs811_channel_str = package_params.get('Channel')

        tcs811_file = str_to_num(tcs811_file_str)
        tcs811_channel = str_to_num(tcs811_channel_str)

        # Ensure required fields are valid
        if tcs811_file is None or tcs811_channel is None:
            continue  # Skip if essential parameters are invalid

        # Find the corresponding TCH209 commands within 10 minutes (600 seconds) after TCS811
        matching_tch209 = TCH209_commands[
            (TCH209_commands['timestamp'] > tcs811_time) &
            (TCH209_commands['timestamp'] <= tcs811_time + 600)
            ]

        tch209_filenames = []
        for _, tch209_row in matching_tch209.iterrows():
            try:
                tch209_params = json.loads(tch209_row['param'])
            except json.JSONDecodeError:
                continue  # Skip this row if JSON is invalid

            filename = tch209_params.get('packageForm', {}).get('params', {}).get('filename')
            if filename:
                tch209_filenames.append(filename)

        # Check for the corresponding TCS812 command after TCS811
        matching_tcs812 = TCS812_commands[
            (TCS812_commands['timestamp'] > tcs811_time)
        ]

        if matching_tcs812.empty:
            # Depending on desired behavior, you might want to continue instead of returning
            return {'error': 'file_saving_stop_not_found(TCS812)'}

        tcs812_row = matching_tcs812.iloc[0]
        tcs812_time = tcs812_row['timestamp']
        try:
            tcs812_params = json.loads(tcs812_row['param'])
        except json.JSONDecodeError:
            continue  # Skip this iteration if JSON is invalid

        tcs812_delay_seconds_str = tcs812_params.get('delayForm', {}).get('seconds')
        if not tcs812_delay_seconds_str:
            continue  # Skip if 'seconds' is missing

        # Parse the delay time and convert it to a timestamp
        try:
            tcs812_dt = datetime.strptime(tcs812_delay_seconds_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
            tcs812_timestamp = int(tcs812_dt.timestamp())
        except ValueError:
            continue  # Skip if datetime parsing fails

        # Find the first record in TMS1007 after TCS811
        matching_tms1007_start = AS02hist_file_save_telemetry[
            (AS02hist_file_save_telemetry['timestamp'] > tcs811_time)
        ]

        if matching_tms1007_start.empty:
            continue

        tms1007_start_row = matching_tms1007_start.iloc[0]
        tms1007_start_time = tms1007_start_row['timestamp']
        tms1007_start_value = tms1007_start_row.get('TMS1007')

        # Find the first record in TMS1007 after TCS812's delay seconds
        matching_tms1007_end = AS02hist_file_save_telemetry[
            (AS02hist_file_save_telemetry['timestamp'] > tcs812_timestamp)
        ]

        if matching_tms1007_end.empty:
            continue

        tms1007_end_row = matching_tms1007_end.iloc[0]
        tms1007_end_time = tms1007_end_row['timestamp']
        tms1007_end_value = tms1007_end_row.get('TMS1007')

        # Ensure telemetry values are valid numbers
        if tms1007_start_value is None or tms1007_end_value is None:
            continue

        # Calculate the absolute difference of values
        file_size = abs(tms1007_end_value - tms1007_start_value)

        hist_file_save_data.append({
            'hist_data_saving_time': tcs811_time,
            'save_to_number': tcs811_file,
            'files_saved': tch209_filenames,
            'file_size': file_size
        })

    result = json.dumps(hist_file_save_data, ensure_ascii=False)
    return result


def silicon_battery_task(post_token_url,
                         post_token_user_name,
                         post_token_password,
                         metedataservice_url,
                         influxdb_action,
                         host_action,
                         tf1,
                         tf2,
                         satID):
    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            return None

    # Retrieve the command data
    AS_commands = get_AScommands(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        influxdb_action,
        host_action,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )

    # Filter for TCN090 commands
    TCN090_commands = AS_commands[AS_commands['cmd_code'] == 'TCN090']

    # Initialize list to store the results
    silicon_battery_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')  # If needed for further processing

    # Iterate over each TCN090 command
    for _, tcn090_row in TCN090_commands.iterrows():
        tcn090_time = tcn090_row['timestamp']

        # Parse the 'param' JSON
        try:
            tcn090_params = json.loads(tcn090_row['param'])
        except json.JSONDecodeError:
            # Skip this command if JSON is invalid
            continue

        # Extract 'seconds' from 'delayForm'
        delay_seconds_str = tcn090_params.get('delayForm', {}).get('seconds')
        if not delay_seconds_str:
            # Skip if 'seconds' is missing
            continue

        # Parse the delay time and convert it to a timestamp
        try:
            tcn090_dt = datetime.strptime(delay_seconds_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
            tcn090_timestamp = int(tcn090_dt.timestamp())
        except ValueError:
            # Skip if datetime parsing fails
            continue

        # Optionally, extract and convert other parameters if needed
        # For example, if there are additional parameters in 'packageForm', handle them here

        # Append the processed data to the list
        silicon_battery_data.append({
            'command_sent_time': tcn090_time,
            'command_execution_time': tcn090_timestamp
        })

    # Convert the result to JSON
    result = json.dumps(silicon_battery_data, ensure_ascii=False)
    return result


def delete_platform_data_task(post_token_url,
                              post_token_user_name,
                              post_token_password, metedataservice_url, influxdb_action, host_action, tf1, tf2, satID):
    # Retrieve the command data
    AS_commands = get_AScommands(post_token_url,
                                 post_token_user_name,
                                 post_token_password, metedataservice_url, influxdb_action, host_action, tf1=tf1,
                                 tf2=tf2, satID=satID)

    # Filter for TCS815 commands
    TCS815_commands = AS_commands[AS_commands['cmd_code'] == 'TCS815']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCS815 command
    for _, tcs815_row in TCS815_commands.iterrows():
        tcs815_time = tcs815_row['timestamp']
        tcs815_params = json.loads(tcs815_row['param'])
        tcs815_delay_seconds = tcs815_params['delayForm']['seconds']

        # Parse the delay time and convert it to a timestamp
        tcs815_dt = datetime.strptime(tcs815_delay_seconds, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
        tcs815_timestamp = int(tcs815_dt.timestamp())

        delete_payload_data.append({
            'command_time': tcs815_time,
            'delay_time': tcs815_timestamp,
            'params': tcs815_params['packageForm']['params']
        })

    result = json.dumps(delete_payload_data, ensure_ascii=False)
    return result


def delete_platform_folder_task(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                metedataservice_url,
                                influxdb_action,
                                host_action,
                                tf1,
                                tf2,
                                satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Retrieve the command data
    AS_commands = get_AScommands(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        influxdb_action,
        host_action,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )

    # Check if AS_commands DataFrame is empty
    if AS_commands.empty:
        logger.info("No AS_commands retrieved. Exiting function.")
        return json.dumps([])  # Return empty JSON list

    # Ensure 'cmd_code' column exists
    if 'cmd_code' not in AS_commands.columns:
        logger.error("'cmd_code' column not found in AS_commands DataFrame.")
        return json.dumps([])

    # Filter for TCH208 commands using 'cmd_code'
    TCH208_commands = AS_commands[AS_commands['cmd_code'] == 'TCH208']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc
    # tz_local is defined but not used in this function; keep if needed for future use
    tz_local = pytz.timezone('Asia/Shanghai')

    # Iterate over each TCH208 command
    for index, tch208_row in TCH208_commands.iterrows():
        tch208_time = tch208_row.get('timestamp')

        # Parse the 'param' JSON
        param_str = tch208_row.get('param')
        if not param_str:
            logger.warning(f"Missing 'param' in TCH208 command at index {index}. Skipping.")
            continue

        try:
            tch208_params = json.loads(param_str)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in 'param' for TCH208 command at index {index}. Skipping.")
            continue

        # Extract 'seconds' from 'delayForm'
        delay_form = tch208_params.get('delayForm', {})
        delay_seconds_str = delay_form.get('seconds')
        if not delay_seconds_str:
            logger.warning(f"Missing 'seconds' in 'delayForm' for TCH208 command at index {index}. Skipping.")
            continue

        # Parse the delay time and convert it to a timestamp
        try:
            tch208_dt = datetime.strptime(delay_seconds_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
            tch208_timestamp = int(tch208_dt.timestamp())
        except ValueError:
            logger.warning(f"Invalid datetime format in 'seconds' for TCH208 command at index {index}. Skipping.")
            continue

        # Extract 'filename' parameter
        package_form = tch208_params.get('packageForm', {})
        package_params = package_form.get('params', {})
        filename = package_params.get('filename')

        if filename is None:
            logger.warning(f"Missing 'filename' in 'params' for TCH208 command at index {index}. Skipping.")
            continue

        # Append the processed data to the list
        delete_payload_data.append({
            'command_time': tch208_time,
            'delay_time': tch208_timestamp,
            'params': {
                'filename': filename
            }
        })

    # Convert the result to JSON
    result = json.dumps(delete_payload_data, ensure_ascii=False)
    return result


def delete_payload_data_task(post_token_url,
                             post_token_user_name,
                             post_token_password,
                             metedataservice_url,
                             influxdb_action,
                             host_action,
                             tf1,
                             tf2,
                             satID):
    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            return None

    # Retrieve the command data
    AS_commands = get_AScommands(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        influxdb_action,
        host_action,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )

    # Filter for TCS808 commands
    TCS808_commands = AS_commands[AS_commands['cmd_code'] == 'TCS808']

    # Initialize list to store the results
    delete_payload_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')  # If needed for further processing

    # Iterate over each TCS808 command
    for _, tcs808_row in TCS808_commands.iterrows():
        tcs808_time = tcs808_row['timestamp']

        # Parse the 'param' JSON
        try:
            tcs808_params = json.loads(tcs808_row['param'])
        except json.JSONDecodeError:
            # Skip this command if JSON is invalid
            continue

        # Extract 'seconds' from 'delayForm'
        delay_seconds_str = tcs808_params.get('delayForm', {}).get('seconds')
        if not delay_seconds_str:
            # Skip if 'seconds' is missing
            continue

        # Parse the delay time and convert it to a timestamp
        try:
            tcs808_dt = datetime.strptime(delay_seconds_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
            tcs808_timestamp = int(tcs808_dt.timestamp())
        except ValueError:
            # Skip if datetime parsing fails
            continue

        # Extract and convert 'EndFileNum' and 'StartFileNum' parameters
        package_params = tcs808_params.get('packageForm', {}).get('params', {})
        end_file_num_str = package_params.get('EndFileNum')
        start_file_num_str = package_params.get('StartFileNum')

        end_file_num = str_to_num(end_file_num_str)
        start_file_num = str_to_num(start_file_num_str)

        # Ensure required fields are valid
        if end_file_num is None or start_file_num is None:
            continue  # Skip if essential parameters are invalid

        # Append the processed data to the list
        delete_payload_data.append({
            'command_time': tcs808_time,
            'delay_time': tcs808_timestamp,
            'params': {
                'EndFileNum': end_file_num,
                'StartFileNum': start_file_num
            }
        })

    # Convert the result to JSON
    result = json.dumps(delete_payload_data, ensure_ascii=False)
    return result


def AS03_sensing_upload(post_token_url,
                        post_token_user_name,
                        post_token_password,
                        metedataservice_url,
                        _influxdb,
                        client,
                        tf1,
                        tf2,
                        satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Retrieve the command data
    AS03_commands = get_AScommands(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        _influxdb,
        client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )

    # Check if AS03_commands DataFrame is empty
    if AS03_commands.empty:
        logger.info("No AS03_commands retrieved. Exiting function.")
        return json.dumps([])  # Return empty JSON list

    # Ensure 'cmd_code' column exists
    if 'cmd_code' not in AS03_commands.columns:
        logger.error("'cmd_code' column not found in AS03_commands DataFrame.")
        return json.dumps([])

    # Filter for TCKAF15 and TCKBB02 commands using 'cmd_code'
    TCKAF15_commands = AS03_commands[AS03_commands['cmd_code'] == 'TCKAF15']
    TCKBB02_commands = AS03_commands[AS03_commands['cmd_code'] == 'TCKBB02']

    # Initialize list to store the results
    sensing_task_data = []

    # Iterate over each TCKAF15 command
    for index, tckaf15_row in TCKAF15_commands.iterrows():
        tckaf15_time = tckaf15_row.get('timestamp')

        # Parse the 'param' JSON
        param_str = tckaf15_row.get('param')
        if not param_str:
            logger.warning(f"Missing 'param' in TCKAF15 command at index {index}. Skipping.")
            continue

        try:
            tckaf15_full_params = json.loads(param_str)
            tckaf15_params = tckaf15_full_params.get('packageForm', {}).get('params', {})
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in 'param' for TCKAF15 command at index {index}. Skipping.")
            continue

        # Extract and convert parameters
        task_start_str = tckaf15_params.get('start')
        task_end_str = tckaf15_params.get('end')
        side_str = tckaf15_params.get('side')
        latka_str = tckaf15_params.get('latka')
        lonka_str = tckaf15_params.get('lonka')
        altka_str = tckaf15_params.get('altka')
        sendswh_str = tckaf15_params.get('sendswh')
        tar_str = tckaf15_params.get('tar')

        # Convert parameters
        task_start = str_to_num(task_start_str)
        task_end = str_to_num(task_end_str)
        duration = task_end - task_start if (task_start is not None and task_end is not None) else None
        side = str_to_num(side_str)
        lat = str_to_num(latka_str)
        lon = str_to_num(lonka_str)
        alt = str_to_num(altka_str)
        sendswh = str_to_num(sendswh_str)
        tar = str_to_num(tar_str)

        # Validate essential parameters
        if None in [task_start, task_end, duration, side, lat, lon, alt, sendswh, tar]:
            logger.warning(f"Invalid or missing parameters in TCKAF15 command at index {index}. Skipping.")
            continue

        # Check for task cancellation
        def is_cancel_task(param_str):
            try:
                param = json.loads(param_str)
                return param.get('packageForm', {}).get('params', {}).get('v0') == 26214
            except json.JSONDecodeError:
                return False

        cancel_task = TCKBB02_commands[
            (TCKBB02_commands['timestamp'] > tckaf15_time) &
            (TCKBB02_commands['timestamp'] <= tckaf15_time + 300) &
            (TCKBB02_commands['param'].apply(is_cancel_task))
            ]

        if not cancel_task.empty:
            logger.info(f"Task cancellation found for TCKAF15 command at index {index}. Skipping.")
            continue

        # Check for duplicate tasks
        duplicate_found = False
        for existing_task in sensing_task_data:
            existing_start = existing_task['TCKAF15'].get('start')
            if existing_start and abs(task_start - existing_start) < 60:
                duplicate_found = True
                logger.info(f"Duplicate task found for TCKAF15 command at index {index}. Skipping.")
                break

        if duplicate_found:
            continue

        # Append the processed data to the list
        sensing_task_data.append({
            'TCKAF15': {
                'timestamp': tckaf15_time,
                'start': task_start,
                'end': task_end,
                'duration': duration,
                'side': side,
                'lat': lat,
                'lon': lon,
                'alt': alt,
                'sendswh': sendswh,
                'tar': tar
            }
        })

    # Convert the result to JSON
    result = json.dumps(sensing_task_data, ensure_ascii=False)
    return result


def AS03_in_sight_sensing_task(post_token_url,
                               post_token_user_name,
                               post_token_password, orbit_service, metedataservice_url, _influxdb, client, tf1, tf2,
                               satID):
    # Retrieve the telemetry data, including the new dataframes
    result_df_00F0, result_df_0620, result_df_0094, result_df_0684, result_df_00D0 = get_AS03_in_sight_sensing_task_data(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url, _influxdb, client, tf1, tf2, satID)
    # print(result_df_00F0)
    # print(result_df_0620)
    # print(result_df_0094)
    # print(result_df_0684)
    # print(result_df_00D0)

    # Convert timestamps to float for consistency
    result_df_00F0['timestamp'] = result_df_00F0['timestamp'].astype(float)
    result_df_0620['timestamp'] = result_df_0620['timestamp'].astype(float)
    result_df_0094['timestamp'] = result_df_0094['timestamp'].astype(float)
    result_df_0684['timestamp'] = result_df_0684['timestamp'].astype(float)
    result_df_00D0['timestamp'] = result_df_00D0['timestamp'].astype(float)

    task_list = get_task_list(post_token_url,
                              post_token_user_name,
                              post_token_password, orbit_service, tf1, tf2, satID)

    result = {'InfaredSensing': {}}

    for i, task in task_list.iterrows():
        task_start = pd.to_datetime(task['starting'])
        task_end = pd.to_datetime(task['ending'])

        # Get data within task start and end times
        df_00F0_task = result_df_00F0[(result_df_00F0['timestamp'] >= task_start.timestamp()) &
                                      (result_df_00F0['timestamp'] <= task_end.timestamp())]

        df_0620_task = result_df_0620[(result_df_0620['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0620['timestamp'] <= task_end.timestamp())]
        df_0094_task = result_df_0094[(result_df_0094['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0094['timestamp'] <= task_end.timestamp())]
        df_0684_task = result_df_0684[(result_df_0684['timestamp'] >= task_start.timestamp()) &
                                      (result_df_0684['timestamp'] <= task_end.timestamp())]
        df_00D0_task = result_df_00D0[(result_df_00D0['timestamp'] >= task_start.timestamp()) &
                                      (result_df_00D0['timestamp'] <= task_end.timestamp())]

        # Process probeon (1.2)
        probeon_groups = (df_00F0_task['TMY002'] != df_00F0_task['TMY002'].shift()).cumsum()
        consecutive_probeon_groups = df_00F0_task.groupby(probeon_groups).filter(
            lambda x: (x['TMY002'] == 15).all() and len(x) >= 2)

        probeon_data = {}
        for j, (group, group_df) in enumerate(consecutive_probeon_groups.groupby(probeon_groups), start=1):
            if (group_df['TMY002'] == 15).all():
                starttimestamp = group_df['timestamp'].iloc[0]
                endtimestamp = group_df['timestamp'].iloc[-1]
                duration = endtimestamp - starttimestamp
                probeon_data[str(j)] = {
                    'starttimestamp': starttimestamp,
                    'endtimestamp': endtimestamp,
                    'duration': duration
                }

        # Process cameraon and shooting (1.3, 1.4, 1.5)
        cameraon = df_0620_task[df_0620_task['TMH1084'] == 1]
        shooting = df_00F0_task[df_00F0_task['TMY005'] == 2]

        cameraon_data = {
            'starttimestamp': cameraon['timestamp'].iloc[0] if not cameraon.empty else None,
            'endtimestamp': cameraon['timestamp'].iloc[-1] if not cameraon.empty else None,
            'duration': (cameraon['timestamp'].iloc[-1] - cameraon['timestamp'].iloc[0]) if not cameraon.empty else None
        }

        shooting_data = {
            'starttimestamp': shooting['timestamp'].iloc[0] if not shooting.empty else None,
            'endtimestamp': shooting['timestamp'].iloc[-1] if not shooting.empty else None,
            'duration': (shooting['timestamp'].iloc[-1] - shooting['timestamp'].iloc[0]) if not shooting.empty else None
        }

        # If shooting_data is empty, use TMK2008 and TMK2009
        if shooting.empty:
            # Find first non-zero values of TMK2008 and TMK2009
            tmk2008_non_zero = df_0684_task[df_0684_task['TMK2008'] != 0]
            tmk2009_non_zero = df_0684_task[df_0684_task['TMK2009'] != 0]

            if not tmk2008_non_zero.empty and not tmk2009_non_zero.empty:
                starttimestamp = tmk2008_non_zero['TMK2008'].iloc[0]
                endtimestamp = tmk2009_non_zero['TMK2009'].iloc[0]
                duration = endtimestamp - starttimestamp

                shooting_data = {
                    'starttimestamp': starttimestamp,
                    'endtimestamp': endtimestamp,
                    'duration': duration
                }
            else:
                shooting_data = {
                    'starttimestamp': None,
                    'endtimestamp': None,
                    'duration': None
                }

        # Process temperatures (1.3, 1.4, 1.5)
        if not cameraon.empty:
            cameraon_tmy017 = df_00F0_task[(df_00F0_task['timestamp'] >= cameraon['timestamp'].iloc[0]) &
                                           (df_00F0_task['timestamp'] <= cameraon['timestamp'].iloc[-1])]
            cameraon_tms627 = df_0094_task[(df_0094_task['timestamp'] >= cameraon['timestamp'].iloc[0]) &
                                           (df_0094_task['timestamp'] <= cameraon['timestamp'].iloc[-1])]
        else:
            cameraon_tmy017 = pd.DataFrame()
            cameraon_tms627 = pd.DataFrame()

        # Update shooting_tms627 based on new shooting_data
        if shooting_data['starttimestamp'] is not None and shooting_data['endtimestamp'] is not None:
            shooting_tms627 = df_0094_task[(df_0094_task['timestamp'] >= shooting_data['starttimestamp']) &
                                           (df_0094_task['timestamp'] <= shooting_data['endtimestamp'])]
        else:
            shooting_tms627 = pd.DataFrame()

        cameraon_tmy017_data = {
            'time': cameraon_tmy017['timestamp'].tolist() if not cameraon_tmy017.empty else [],
            'value': cameraon_tmy017['TMY017'].tolist() if not cameraon_tmy017.empty else []
        }

        cameraon_tms627_data = {
            'time': cameraon_tms627['timestamp'].tolist() if not cameraon_tms627.empty else [],
            'value': cameraon_tms627['TMS627'].tolist() if not cameraon_tms627.empty else []
        }

        shooting_tms627_data = {
            'time': shooting_tms627['timestamp'].tolist() if not shooting_tms627.empty else [],
            'value': shooting_tms627['TMS627'].tolist() if not shooting_tms627.empty else []
        }

        # Initialize status fields
        sensing_status = "0"
        ram_status = "0"
        infra_B_can_bus_status = "0"
        side_swipe_angle = None

        # Check for status conditions
        if df_0620_task['TMH1084'].sum() > 10:
            sensing_status = "1"
            # Get the interval of the first and last timestamp where TMH1084 == 1
            interval_start = df_0620_task[df_0620_task['TMH1084'] == 1]['timestamp'].iloc[0]
            interval_end = df_0620_task[df_0620_task['TMH1084'] == 1]['timestamp'].iloc[-1]

            interval_df_0620 = df_0620_task[(df_0620_task['timestamp'] >= interval_start) &
                                            (df_0620_task['timestamp'] <= interval_end)]

            if interval_df_0620['TMH1070'].sum() > 10:
                ram_status = "1"
                infra_B_can_bus_status = "0"
            if interval_df_0620['TMH1090'].sum() <= 10:
                infra_B_can_bus_status = "1"
                ram_status = "0"

            # Get the first value of TMK2115 that is not 0 during the task period
            side_swipe_angle_values = df_0684_task[df_0684_task['TMK2115'] != 0]['TMK2115']
            if not side_swipe_angle_values.empty:
                side_swipe_angle = side_swipe_angle_values.iloc[0]

        # Get 'payloadfileno' as the last non-zero value of TMS006 during the task time
        tms006_non_zero = df_00D0_task[df_00D0_task['TMS006'] != 0]['TMS006']
        if not tms006_non_zero.empty:
            payloadfileno = tms006_non_zero.iloc[-1]  # Get the last non-zero value
        else:
            payloadfileno = None

        # Assemble task data
        if sensing_status == "1":  # Only add the task data if sensing_status is "1"
            task_data = {
                'probeon(探测器上电时间)': probeon_data,
                'cameraon(相机上下电时间)': cameraon_data,
                'shooting(成像时间)': shooting_data,
                'cameraonTMY017(相机上电焦面测点)': cameraon_tmy017_data,
                'cameraonTMS627(相机上电制冷机测点)': cameraon_tms627_data,
                'shootingTMS627(成像期间电制冷机测点)': shooting_tms627_data,
                'sensing_status': sensing_status,  # 0无成像 1成像
                'ram_status': ram_status,  # 0好 1坏
                'infra_B_can_bus_status': infra_B_can_bus_status,  # 0好 1坏
                'side-swipe-angle': side_swipe_angle,
                'payloadfileno': payloadfileno  # Updated field
            }

            result['InfaredSensing'][str(i + 1)] = task_data

    return json.dumps(result, indent=4, ensure_ascii=False)


def AS03_out_sight_sensing_task(post_token_url,
                                post_token_user_name,
                                post_token_password,
                                orbit_service,
                                metedataservice_url,
                                _influxdb,
                                client,
                                influxdb_action,
                                host_action,
                                tf1,
                                tf2,
                                satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Step 1: Get the uploaded sensing data tasks
    AS03_sensing_upload_data = AS03_sensing_upload(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        influxdb_action,
        host_action,
        tf1,
        tf2,
        satID
    )

    try:
        AS03_sensing_upload_data = json.loads(AS03_sensing_upload_data)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from AS03_sensing_upload_data. Exiting function.")
        return json.dumps({})

    # Step 2: Adjust satIDs based on satID
    if satID == '13':
        satIDs = '13,16'  # Include both '13' and '16'
    else:
        satIDs = satID

    # Step 3: Retrieve the task list
    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satIDs
    )

    # Ensure 'task_list' is a DataFrame
    if not isinstance(task_list, pd.DataFrame):
        logger.error("Expected task_list to be a DataFrame, but got something else.")
        raise ValueError("Expected task_list to be a DataFrame, but got something else.")

    # Step 4: Retrieve the telemetry data
    result_df_00F0, result_df_0620, result_df_0684, result_df_00D0, result_df_00D4 = get_AS03_out_sight_sensing_task_data(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        _influxdb,
        client,
        tf1,
        tf2,
        satID
    )

    # Ensure result_df_0620 and result_df_00D0 are DataFrames
    if not isinstance(result_df_0620, pd.DataFrame):
        logger.error("Expected result_df_0620 to be a DataFrame, but got something else.")
        raise ValueError("Expected result_df_0620 to be a DataFrame, but got something else.")
    if not isinstance(result_df_00D0, pd.DataFrame):
        logger.error("Expected result_df_00D0 to be a DataFrame, but got something else.")
        raise ValueError("Expected result_df_00D0 to be a DataFrame, but got something else.")

    # Convert timestamps to float
    result_df_0620['timestamp'] = result_df_0620['timestamp'].astype(float)
    result_df_00D0['timestamp'] = result_df_00D0['timestamp'].astype(float)

    result = {'InfaredSensing': {}}

    # Step 5: Identify out-of-sight tasks
    out_sight_tasks = []
    for task in AS03_sensing_upload_data:
        tckaf15 = task.get('TCKAF15', {})
        task_start = tckaf15.get('start')  # Start time in seconds since epoch
        task_end = tckaf15.get('end')
        duration = tckaf15.get('duration')
        side = tckaf15.get('side')
        lat = tckaf15.get('lat')
        lon = tckaf15.get('lon')
        alt = tckaf15.get('alt')

        # Validate essential fields
        if None in [task_start, task_end, duration, side, lat, lon, alt]:
            logger.warning(f"Missing essential fields in task: {task}. Skipping.")
            continue

        # Check if task_start is within any task in task_list
        in_sight = False
        for _, row in task_list.iterrows():
            list_task_start = pd.to_datetime(row['starting'], utc=True).timestamp()
            list_task_end = pd.to_datetime(row['ending'], utc=True).timestamp()
            if list_task_start <= task_start <= list_task_end:
                in_sight = True
                break
        if not in_sight:
            # This is an out-of-sight task
            out_sight_tasks.append(task)

    # Step 6: Process each out-of-sight task
    for i, task in enumerate(out_sight_tasks, start=1):
        tckaf15 = task.get('TCKAF15', {})
        task_start = tckaf15.get('start')
        task_end = tckaf15.get('end')
        duration = tckaf15.get('duration')
        side = tckaf15.get('side')
        lat = tckaf15.get('lat')
        lon = tckaf15.get('lon')
        alt = tckaf15.get('alt')

        # Validate essential fields
        if None in [task_start, task_end, duration, side, lat, lon, alt]:
            logger.warning(f"Missing essential fields in out-of-sight task: {task}. Skipping.")
            continue

        # Search TMH1084 in ±1800 seconds of task_start
        window_start = task_start - 1800
        window_end = task_start + 1800

        # Filter result_df_0620 within this window
        df_window = result_df_0620[
            (result_df_0620['timestamp'] >= window_start) &
            (result_df_0620['timestamp'] <= window_end)
            ]

        # Filter result_df_00D0 within this window
        df_payload_fileno = result_df_00D0[
            (result_df_00D0['timestamp'] >= window_start) &
            (result_df_00D0['timestamp'] <= window_end)
            ]

        # Find intervals where TMH1084 == 1
        sensing_tasks = df_window[df_window['TMH1084'] == 1]

        if sensing_tasks.empty:
            # No sensing activity for this task, set fields to 'nodata'
            task_data = {
                'upload_task': {
                    'start': task_start,
                    'end': task_end,
                    'duration': duration,
                    'side': side,
                    'lat': lat,
                    'lon': lon,
                    'alt': alt
                },
                'cameraon': {
                    'starttimestamp': 'nodata',
                    'endtimestamp': 'nodata',
                    'duration': 'nodata'
                },
                'ram_status': 'nodata',
                'infra_B_can_bus_status': 'nodata',
                'payloadfileno': 'nodata'
            }
            # Use a unique key for each task
            result['InfaredSensing'][f'Task_{i}'] = task_data
            continue  # Skip to the next task

        # Proceed if sensing_tasks is not empty
        # Calculate the time difference between consecutive rows
        sensing_tasks = sensing_tasks.copy()  # Avoid SettingWithCopyWarning
        sensing_tasks['time_diff'] = sensing_tasks['timestamp'].diff().fillna(0)

        # Group consecutive intervals where the time difference is less than 200 seconds
        sensing_tasks['group'] = (sensing_tasks['time_diff'] > 200).cumsum()

        # Step 7: Process each group
        for group_id, group_df in sensing_tasks.groupby('group'):
            group_task_start = group_df['timestamp'].iloc[0]
            group_task_end = group_df['timestamp'].iloc[-1]

            # Calculate ram_status and infra_B_can_bus_status
            ram_status = "0"
            infra_B_can_bus_status = "0"
            if group_df['TMH1070'].sum() > 1:
                ram_status = "1"
                infra_B_can_bus_status = "0"
            elif group_df['TMH1090'].sum() == 0:
                infra_B_can_bus_status = "1"
                ram_status = "0"

            # Process cameraon data
            cameraon_data = {
                'starttimestamp': group_task_start,
                'endtimestamp': group_task_end,
                'duration': group_task_end - group_task_start
            }

            # Get 'payloadfileno' as the last non-zero value of TMS006 during the task time
            fileno_series = df_payload_fileno[df_payload_fileno['TMS006'] != 0]['TMS006']
            if not fileno_series.empty:
                payloadfileno = fileno_series.iloc[-1]  # Get the last non-zero value
            else:
                payloadfileno = 'nodata'

            # Assemble task data with additional task information
            task_data = {
                'upload_task': {
                    'start': task_start,
                    'end': task_end,
                    'duration': duration,
                    'side': side,
                    'lat': lat,
                    'lon': lon,
                    'alt': alt
                },
                'cameraon': cameraon_data,
                'ram_status': ram_status,  # 0: good, 1: bad
                'infra_B_can_bus_status': infra_B_can_bus_status,  # 0: good, 1: bad
                'payloadfileno': payloadfileno  # Updated field
            }

            # Use a unique key for each task and group
            result['InfaredSensing'][f'Task_{i}_Group_{group_id}'] = task_data

    return json.dumps(result, indent=4, ensure_ascii=False)


# AS03 remote infrared sensing outsight (with fallback rules for RAM/CAN-B)
def AS03_out_sight_sensing_task_new(post_token_url,
                                    post_token_user_name,
                                    post_token_password,
                                    orbit_service,
                                    metedataservice_url,
                                    _influxdb,
                                    client,
                                    influxdb_action,
                                    host_action,
                                    tf1,
                                    tf2,
                                    satID):
    """
    Out-of-sight sensing task report for AS03.

    Primary path:
      - Use TMH1084 (camera-on), TMH1070, TMH1090 (0620) to determine sensing intervals and status.

    Fallback path (when 0620 is unavailable or contains no TMH1084=1 near tasks):
      - Use 00D4: TMS050/TMS051, 00F0: TMY037/TMY038, and TCS809 to infer ram_status & infra_B_can_bus_status
        by your specified rules (1/2/3 TCKAF15 cases, and TCS809 presence -> all nodata).

    NOTE: TMS050 comparisons use ORIGINAL SCALE (≈ +6 per shot). Thresholds:
      - Single shot: 5–7
      - Double shots: 10–14
      - Triple shots: 15–21

    Output structure keeps "InfaredSensing" for backward compatibility.
    """

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # ----------------------------
    # Helpers
    # ----------------------------
    def to_int_or_none(x):
        try:
            if isinstance(x, str) and x.strip().endswith('Z'):
                # ISO 8601 → epoch seconds
                return int(pd.to_datetime(x, utc=True).timestamp())
            return int(float(x))
        except Exception:
            return None

    def pick_prev(df, t, col):
        """Last row with timestamp <= t; returns (ts, value) or (None, None)."""
        if not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
            return None, None
        sub = df[df['timestamp'] <= t]
        if sub.empty:
            return None, None
        row = sub.iloc[-1]
        return int(row['timestamp']), row[col]

    def pick_after(df, t, col):
        """First row with timestamp >= t; returns (ts, value) or (None, None)."""
        if not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
            return None, None
        sub = df[df['timestamp'] >= t]
        if sub.empty:
            return None, None
        row = sub.iloc[0]
        return int(row['timestamp']), row[col]

    def pick_after_relaxed(df, t, col, extra_wait=5400):
        """
        先严格找 >= t 的第一个点（用于 t = t0+720）。
        若找不到，再在 (t, t+extra_wait] 内找第一个点。
        """
        ts, val = pick_after(df, t, col)
        if ts is not None:
            return ts, val
        if not isinstance(df, pd.DataFrame) or df.empty or col not in df.columns:
            return None, None
        sub = df[(df['timestamp'] > t) & (df['timestamp'] <= t + extra_wait)]
        if sub.empty:
            return None, None
        row = sub.iloc[0]
        return int(row['timestamp']), row[col]

    def get_TCS809_events():
        """Read TCS809 commands (DataSource=='01' and isDelay==true). Use delayForm.seconds as the key time."""
        try:
            cmds = get_AScommands(
                post_token_url, post_token_user_name, post_token_password,
                metedataservice_url, influxdb_action, host_action,
                tf1=tf1_tm_ext, tf2=tf2_tm_ext, satID=satID
            )
            if cmds.empty or 'cmd_code' not in cmds.columns or 'param' not in cmds.columns:
                return []
            tcs809 = cmds[cmds['cmd_code'] == 'TCS809']
            out = []
            for _, row in tcs809.iterrows():
                try:
                    p = json.loads(row['param'])
                except Exception:
                    continue
                params = (p.get('packageForm') or {}).get('params') or {}
                ds = str(params.get('DataSource', '')).strip()
                delay = p.get('delayForm') or {}
                is_delay = bool(delay.get('isDelay', False))
                key_iso = delay.get('seconds')
                if ds in ('01', '1') and is_delay and key_iso:
                    ts = to_int_or_none(key_iso)  # convert ISO8601 to epoch seconds
                    if ts is not None:
                        out.append({'delay_seconds': ts})
            return out
        except Exception as e:
            logger.warning(f"Failed to read TCS809 events: {e}")
            return []

    # ---- Harden telemetry frames: coerce timestamps & fields to numeric ----
    def _sanitize_tm_df(df, numeric_cols):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df
        # 1) timestamp -> numeric seconds
        if 'timestamp' in df.columns:
            # strip spaces, coerce to numeric
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
            # handle ms/ns if any (just in case)
            if df['timestamp'].max() > 1e12:
                df['timestamp'] = (df['timestamp'] // 1000)
            # drop bad rows, cast to int
            df = df.dropna(subset=['timestamp'])
            df['timestamp'] = df['timestamp'].astype('int64')
        # 2) telemetry value cols -> numeric
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        # 3) sort for deterministic prev/after picks
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    # ----------------------------
    # Step 1: Get uploaded sensing tasks (TCKAF15 list)
    # ----------------------------
    AS03_sensing_upload_data = AS03_sensing_upload(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        influxdb_action,
        host_action,
        tf1, tf2, satID
    )
    try:
        AS03_sensing_upload_data = json.loads(AS03_sensing_upload_data)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from AS03_sensing_upload().")
        return json.dumps({})

    # ----------------------------
    # Step 2: satIDs for visibility task list
    # ----------------------------
    satIDs = '13,16' if satID == '13' else satID

    # ----------------------------
    # Step 3: Task list (visibility window)
    # ----------------------------
    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1, tf2, satIDs
    )
    if not isinstance(task_list, pd.DataFrame):
        raise ValueError("Expected task_list to be a DataFrame.")

    # ----------------------------
    # Step 4: Telemetry data
    # ----------------------------
    # NEW: widen only the telemetry fetch window by ±24h
    tf1_dt = pd.to_datetime(tf1, utc=True)
    tf2_dt = pd.to_datetime(tf2, utc=True)

    tf1_tm_ext = (tf1_dt - pd.Timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
    tf2_tm_ext = (tf2_dt + pd.Timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')

    result_df_00F0, result_df_0620, result_df_0684, result_df_00D0, result_df_00D4 = get_AS03_out_sight_sensing_task_data(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        _influxdb,
        client,
        tf1=tf1_tm_ext,  # <— use extended telemetry window
        tf2=tf2_tm_ext,  # <— use extended telemetry window
        satID=satID
    )
    # Apply to each DF
    result_df_00F0 = _sanitize_tm_df(result_df_00F0, ['TMY002', 'TMY017', 'TMY005', 'TMY037', 'TMY038'])
    result_df_0620 = _sanitize_tm_df(result_df_0620, ['TMH1070', 'TMH1084', 'TMH1090'])
    result_df_0684 = _sanitize_tm_df(result_df_0684, ['TMK2115'])
    result_df_00D0 = _sanitize_tm_df(result_df_00D0, ['TMS006'])
    result_df_00D4 = _sanitize_tm_df(result_df_00D4, ['TMS050', 'TMS051'])

    # Optional quick sanity prints (remove later)
    # print('[00D0] timestamp dtype:', getattr(result_df_00D0.get('timestamp'), 'dtype', None))
    # print('[00D0] head ts:', result_df_00D0['timestamp'].head(3).tolist() if not result_df_00D0.empty else None)

    # ----------------------------
    # Step 5: Pick out-of-sight tasks (TCKAF15.start not inside any visibility window)
    # ----------------------------
    def is_in_sight(t_start):
        # task_list starting/ending are timestamps in ISO; convert
        for _, row in task_list.iterrows():
            list_task_start = pd.to_datetime(row['starting'], utc=True).timestamp()
            list_task_end = pd.to_datetime(row['ending'], utc=True).timestamp()
            if list_task_start <= t_start <= list_task_end:
                return True
        return False

    out_sight_tasks = []
    for task in AS03_sensing_upload_data:
        t15 = task.get('TCKAF15', {})
        task_start = to_int_or_none(t15.get('start'))
        task_end = to_int_or_none(t15.get('end'))
        duration = (task_end - task_start) if (task_start is not None and task_end is not None) else None
        side = t15.get('side')
        lat = t15.get('lat')
        lon = t15.get('lon')
        alt = t15.get('alt')
        if None in (task_start, task_end, duration, side, lat, lon, alt):
            continue
        if not is_in_sight(task_start):
            out_sight_tasks.append(task)

    result = {'InfaredSensing': {}}

    # Pre-read TCS809 (delay_seconds set)
    tcs809_events = get_TCS809_events()
    tcs809_times = set([e['delay_seconds'] for e in tcs809_events if 'delay_seconds' in e])

    # ----------------------------
    # Primary path for each out-of-sight task:
    #   Try TMH1084 (camera-on) in +/-1800s window.
    #   If no TMH1084 data (empty/columns missing) → fallback later.
    # ----------------------------
    fallback_candidates = []  # collect (index, task) that need fallback
    for i, task in enumerate(out_sight_tasks, start=1):
        t15 = task.get('TCKAF15', {})
        task_start = to_int_or_none(t15.get('start'))
        task_end = to_int_or_none(t15.get('end'))
        duration = (task_end - task_start) if (task_start is not None and task_end is not None) else None
        side = t15.get('side')
        lat = t15.get('lat')
        lon = t15.get('lon')
        alt = t15.get('alt')

        # base record
        base = {
            'upload_task': {
                'start': task_start,
                'end': task_end,
                'duration': duration,
                'side': side,
                'lat': lat,
                'lon': lon,
                'alt': alt
            },
            'cameraon': {
                'starttimestamp': 'nodata',
                'endtimestamp': 'nodata',
                'duration': 'nodata'
            },
            'ram_status': 'nodata',
            'infra_B_can_bus_status': 'nodata',
            'payloadfileno': 'nodata'
        }

        # window for telemetry lookups
        window_start = task_start - 1800

        window_end = task_start + 1800

        # Payload file no from 00D0 (last non-zero TMS006 in window)
        payload_series = pd.Series(dtype='int64')
        if isinstance(result_df_00D0, pd.DataFrame) and not result_df_00D0.empty and 'TMS006' in result_df_00D0.columns:
            df_payload = result_df_00D0[(result_df_00D0['timestamp'] >= window_start) &
                                        (result_df_00D0['timestamp'] <= window_end)]
            if not df_payload.empty:
                payload_series = df_payload['TMS006']
        if not payload_series.empty:
            nz = payload_series[payload_series != 0]
            if not nz.empty:
                base['payloadfileno'] = int(nz.iloc[-1])

        # If 0620 usable with TMH1084==1, use primary path
        need_fallback = True
        if isinstance(result_df_0620, pd.DataFrame) and not result_df_0620.empty:
            if all(c in result_df_0620.columns for c in ('TMH1084', 'TMH1070', 'TMH1090')):
                df_window = result_df_0620[(result_df_0620['timestamp'] >= window_start) &
                                           (result_df_0620['timestamp'] <= window_end)]
                if not df_window.empty:
                    sensing_tasks = df_window[df_window['TMH1084'] == 1]
                    if not sensing_tasks.empty:
                        need_fallback = False
                        # group camera-on segments by 200s gap
                        sensing_tasks = sensing_tasks.copy()
                        sensing_tasks['time_diff'] = sensing_tasks['timestamp'].diff().fillna(0)
                        sensing_tasks['group'] = (sensing_tasks['time_diff'] > 200).cumsum()
                        for group_id, g in sensing_tasks.groupby('group'):
                            g_start = int(g['timestamp'].iloc[0])
                            g_end = int(g['timestamp'].iloc[-1])

                            # ram/infra_B from 0620
                            ram_status = "0"
                            infra_B_status = "0"
                            if g['TMH1070'].sum() > 1:
                                ram_status = "1"
                                infra_B_status = "0"
                            elif g['TMH1090'].sum() == 0:
                                infra_B_status = "1"
                                ram_status = "0"

                            cameraon = {
                                'starttimestamp': g_start,
                                'endtimestamp': g_end,
                                'duration': g_end - g_start
                            }
                            rec = {
                                'upload_task': base['upload_task'],
                                'cameraon': cameraon,
                                'ram_status': ram_status,
                                'infra_B_can_bus_status': infra_B_status,
                                'payloadfileno': base['payloadfileno']
                            }
                            # Keep legacy key style with groups
                            result['InfaredSensing'][f'Task_{i}_Group_{int(group_id)}'] = rec

        if need_fallback:
            # store baseline (so we still return a Task_i node even if no eventual inference)
            result['InfaredSensing'][f'Task_{i}'] = base
            fallback_candidates.append((i, task))

    # ----------------------------
    # Fallback route (apply your rules) for tasks in fallback_candidates
    # ----------------------------
    if fallback_candidates:
        df_d4 = result_df_00D4 if isinstance(result_df_00D4, pd.DataFrame) else pd.DataFrame()
        df_f0 = result_df_00F0 if isinstance(result_df_00F0, pd.DataFrame) else pd.DataFrame()

        # Precompute all out-of-sight tasks (index, obj, t0) for window membership checks
        all_out_sight = []
        for j, t in enumerate(out_sight_tasks, start=1):
            t0j = to_int_or_none(t.get('TCKAF15', {}).get('start'))
            if t0j is not None:
                all_out_sight.append((j, t, t0j))

        if not df_d4.empty and all(c in df_d4.columns for c in ('TMS050', 'TMS051')):
            windows = {}  # (P_ts, A_ts) -> {'fb_tasks': [(i, task, t0)], 'all_tasks': [(j, task, t0)], 'Pvals':{}, 'Avals':{}}

            # 1) Build windows from each fallback candidate
            for i, task in fallback_candidates:
                t15 = task.get('TCKAF15', {})
                t0 = to_int_or_none(t15.get('start'))
                if t0 is None:
                    continue

                # P (<= t0), A (>= t0 + 720)
                P_ts_50, P_50 = pick_prev(df_d4, t0, 'TMS050')
                P_ts_51, P_51 = pick_prev(df_d4, t0, 'TMS051')

                A_ts_50, A_50 = pick_after_relaxed(df_d4, t0 + 720, 'TMS050')
                A_ts_51, A_51 = pick_after_relaxed(df_d4, t0 + 720, 'TMS051')

                P_ts_37, P_37 = pick_prev(df_f0, t0, 'TMY037') if not df_f0.empty else (None, None)
                P_ts_38, P_38 = pick_prev(df_f0, t0, 'TMY038') if not df_f0.empty else (None, None)
                A_ts_37, A_37 = pick_after_relaxed(df_f0, t0 + 720, 'TMY037') if not df_f0.empty else (None, None)
                A_ts_38, A_38 = pick_after_relaxed(df_f0, t0 + 720, 'TMY038') if not df_f0.empty else (None, None)

                # print(f'[FB] task#{i} t0={t0} '
                #       f'P50/P51={P_50}/{P_51} A50/A51={A_50}/{A_51} '
                #       f'P37/P38={P_37}/{P_38} A37/A38={A_37}/{A_38}')

                # If any required A/P missing → record window but will assign nodata later
                if None in (P_50, P_51, A_50, A_51, A_37, A_38) or P_ts_50 is None or A_ts_50 is None:
                    win_key = (None, None, i)
                    windows.setdefault(win_key, {'fb_tasks': [], 'all_tasks': [], 'Pvals': {}, 'Avals': {}})
                    windows[win_key]['fb_tasks'].append((i, task, t0))
                    windows[win_key]['Pvals'] = {'TMS050': P_50, 'TMS051': P_51, 'TMY037': P_37, 'TMY038': P_38}
                    windows[win_key]['Avals'] = {'TMS050': A_50, 'TMS051': A_51, 'TMY037': A_37, 'TMY038': A_38}
                    continue

                # Normal keyed window
                win_key = (int(P_ts_50), int(A_ts_50))
                if win_key not in windows:
                    windows[win_key] = {'fb_tasks': [], 'all_tasks': [], 'Pvals': {}, 'Avals': {}}
                    windows[win_key]['Pvals'] = {'TMS050': P_50, 'TMS051': P_51, 'TMY037': P_37, 'TMY038': P_38}
                    windows[win_key]['Avals'] = {'TMS050': A_50, 'TMS051': A_51, 'TMY037': A_37, 'TMY038': A_38}

                    # Compute ALL out-of-sight TCKAF15 in this P..A window (fallback + primary)
                    P_ts, A_ts = win_key
                    in_window = [(j, tt, t0j) for (j, tt, t0j) in all_out_sight if P_ts <= t0j <= A_ts]
                    in_window.sort(key=lambda x: x[2])  # time order
                    windows[win_key]['all_tasks'] = in_window

                # Attach this fallback task to the window
                windows[win_key]['fb_tasks'].append((i, task, t0))

            # 2) Apply rules per window (using count of ALL out-of-sight tasks)
            for win_key, bundle in windows.items():
                P = bundle['Pvals'];
                A = bundle['Avals']
                all_tasks_sorted = bundle['all_tasks']  # [(idx, task, t0), ...] across the window
                fb_ids = {i for (i, _, _) in bundle['fb_tasks']}
                n = len(all_tasks_sorted)

                # print("this round (all out-of-sight in window):", n)

                def assign(i_task, rs, infra):
                    key = f'Task_{i_task}'
                    if key not in result['InfaredSensing']:
                        result['InfaredSensing'][key] = {
                            'upload_task': {},
                            'cameraon': {'starttimestamp': 'nodata', 'endtimestamp': 'nodata', 'duration': 'nodata'},
                            'ram_status': 'nodata',
                            'infra_B_can_bus_status': 'nodata',
                            'payloadfileno': 'nodata'
                        }
                    result['InfaredSensing'][key]['ram_status'] = rs
                    result['InfaredSensing'][key]['infra_B_can_bus_status'] = infra

                # Missing P/A → set nodata for fallback tasks only
                if P.get('TMS050') is None or P.get('TMS051') is None or A.get('TMS050') is None or A.get(
                        'TMS051') is None \
                        or A.get('TMY037') is None or A.get('TMY038') is None or n == 0:
                    for i_task, _, _ in bundle['fb_tasks']:
                        assign(i_task, 'nodata', 'nodata')
                    continue

                # TCS809 suppression
                has_809 = False
                if isinstance(win_key, tuple) and len(win_key) >= 2 and win_key[0] is not None and win_key[
                    1] is not None:
                    P_ts, A_ts = win_key[0], win_key[1]
                    has_809 = any(P_ts <= t <= A_ts for t in tcs809_times)
                if has_809:
                    for i_task, _, _ in bundle['fb_tasks']:
                        assign(i_task, 'nodata', 'nodata')
                    continue

                # Differences/values (original scale)
                d51 = to_int_or_none(A['TMS051']) - to_int_or_none(P['TMS051'])
                d50 = to_int_or_none(A['TMS050']) - to_int_or_none(P['TMS050'])
                a37 = to_int_or_none(A['TMY037']);
                a38 = to_int_or_none(A['TMY038'])

                # Build position→(rs, infra) map according to your rules
                pos_result = {}  # 1-based position in time order within the window
                if n == 1:
                    if d51 == 1 and (4 <= d50 <= 7) and a37 == 0 and a38 == 0:
                        pos_result[1] = ('0', '0')
                    elif d51 == 1 and d50 == 0 and a37 > 100 and a38 > 100:
                        pos_result[1] = ('0', '1')
                    elif d51 == 0 and a37 == 0 and a38 == 0:
                        pos_result[1] = ('1', '0')
                    elif d51 == 0 and a37 > 100 and a38 > 100:
                        pos_result[1] = ('1', '1')
                elif n == 2:
                    # default none
                    if d51 == 2 and (8 <= d50 <= 14) and a37 == 0 and a38 == 0:
                        pos_result[1] = ('0', '0');
                        pos_result[2] = ('0', '0')
                    elif d51 == 0 and d50 == 0 and a37 > 100 and a38 > 100:
                        pos_result[1] = ('1', '1');
                        pos_result[2] = ('1', '1')
                    elif d51 == 2 and (4 <= d50 <= 7) and a37 > 100 and a38 > 100:
                        pos_result[1] = ('0', '0');
                        pos_result[2] = ('0', '1')
                    elif d51 == 2 and (4 <= d50 <= 7) and a37 == 0 and a38 == 0:
                        pos_result[1] = ('0', '1');
                        pos_result[2] = ('0', '0')
                    elif d51 == 2 and d50 == 0 and a37 > 100 and a38 > 100:
                        pos_result[1] = ('0', '1');
                        pos_result[2] = ('0', '1')
                    elif d51 == 1 and (4 <= d50 <= 7) and a37 == 0 and a38 == 0:
                        pos_result[1] = ('1', '0');
                        pos_result[2] = ('0', '0')
                    elif d51 == 1 and d50 == 0 and a37 == 0 and a38 == 0:
                        pos_result[1] = ('1', '0');
                        pos_result[2] = ('0', '1')
                    elif d51 == 2 and d50 == 0 and a37 == 0 and a38 == 0:
                        pos_result[1] = ('1', '0');
                        pos_result[2] = ('0', '0')
                    elif d51 == 0 and a37 == 0 and a38 == 0:
                        pos_result[1] = ('1', 'nodata');
                        pos_result[2] = ('1', '0')
                elif n == 3:
                    if d51 == 3 and (12 <= d50 <= 21):
                        pos_result[1] = ('0', '0');
                        pos_result[2] = ('0', '0');
                        pos_result[3] = ('0', '0')
                    elif d51 == 0 and d50 == 0:
                        pos_result[1] = ('1', '1');
                        pos_result[2] = ('1', '1');
                        pos_result[3] = ('1', '1')
                    elif d51 == 3 and d50 == 0:
                        pos_result[1] = ('0', '1');
                        pos_result[2] = ('0', '1');
                        pos_result[3] = ('0', '1')
                    elif d51 == 3 and (8 <= d50 <= 14) and a37 > 100 and a38 > 100:
                        pos_result[1] = ('0', '0');
                        pos_result[2] = ('0', '0');
                        pos_result[3] = ('0', '1')

                # 3) Assign only to fallback tasks in this window (by their time order position)
                # Map idx -> position
                idx_to_pos = {all_tasks_sorted[k][0]: k + 1 for k in range(n)}  # j -> 1..n
                for i_task, _, _ in bundle['fb_tasks']:
                    pos = idx_to_pos.get(i_task)
                    if pos is None or pos not in pos_result:
                        assign(i_task, 'nodata', 'nodata')
                    else:
                        rs, infra = pos_result[pos]
                        assign(i_task, rs, infra)

    return json.dumps(result, indent=4, ensure_ascii=False)


def AS03_payload_data_transmission(post_token_url,
                                   post_token_user_name,
                                   post_token_password,
                                   metedataservice_url,
                                   _influxdb_input,
                                   client_input,
                                   influxdb_action,
                                   host_action,
                                   tf1,
                                   tf2,
                                   satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Retrieve the command data
    AS03_payloaddatatransmission = get_AS02_datatransmission(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        _influxdb_input,
        client_input,
        tf1,
        tf2,
        satID
    )

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS03_payloaddatatransmission = AS03_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    payload_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for index, payload_row in AS03_payloaddatatransmission.iterrows():
        TMK2014 = payload_row.get('TMK2014')
        TMK2015 = payload_row.get('TMK2015')

        if TMK2014 != 0 and TMK2015 != 0:
            duration = TMK2015 - TMK2014

            # Calculate the start time for querying commands (48 hours before TMK2014)
            start_time = int(TMK2014 - 48 * 3600)
            end_time = int(TMK2014)

            # Convert start_time and end_time to datetime strings
            start_time_str = pd.to_datetime(start_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
            end_time_str = pd.to_datetime(end_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')

            # Retrieve the command data for the specific time range
            AS02_commands = get_AScommands(
                post_token_url,
                post_token_user_name,
                post_token_password,
                metedataservice_url,
                influxdb_action,
                host_action,
                tf1=start_time_str,
                tf2=end_time_str,
                satID=satID
            )

            # Ensure 'cmd_code' column exists
            if 'cmd_code' not in AS02_commands.columns:
                logger.error(f"'cmd_code' column not found in AS02_commands DataFrame at index {index}. Skipping.")
                continue

            # Filter for relevant commands
            TCKAF03_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03']
            TCS804_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS804']
            TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']
            # Uncomment for debugging
            # print(TCKAF03_commands.to_string())
            # print(TCS804_commands.to_string())
            # print(TCKBB02_commands.to_string())

            # Find TCKAF03 commands with start equal to TMK2014
            matching_tckaf03 = TCKAF03_commands[
                TCKAF03_commands['param'].apply(
                    lambda x: str_to_num(json.loads(x)['packageForm']['params'].get('start')) == TMK2014
                )
            ]

            if not matching_tckaf03.empty:
                tckaf03_row = matching_tckaf03.iloc[0]
                tckaf03_time = tckaf03_row.get('timestamp')
                try:
                    tckaf03_params = json.loads(tckaf03_row.get('param', '{}'))
                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON in 'param' for TCKAF03 command at index {tckaf03_row.name}. Skipping.")
                    continue

                # Extract parameters from TCKAF03
                tckaf03_package_params = tckaf03_params.get('packageForm', {}).get('params', {})
                # Convert all relevant parameters
                tckaf03_package_params_converted = {}
                for key, value in tckaf03_package_params.items():
                    tckaf03_package_params_converted[key] = str_to_num(value)

                # Check for TCKBB02 commands between TCKAF03's timestamp and TMK2014
                def is_cancel_task(param_str):
                    try:
                        param = json.loads(param_str)
                        v0 = str_to_num(param.get('packageForm', {}).get('params', {}).get('v0'))
                        logger.debug(f"Checking v0: {v0}")  # Debug log
                        return v0 == 17476
                    except json.JSONDecodeError:
                        return False

                matching_tckbb02 = TCKBB02_commands[
                    (TCKBB02_commands['timestamp'] > tckaf03_time) &
                    (TCKBB02_commands['timestamp'] <= TMK2014) &
                    (TCKBB02_commands['param'].apply(is_cancel_task))
                    ]

                # If TCKBB02 with v0 == 17476 is found, ignore this task group
                if not matching_tckbb02.empty:
                    logger.info(f"TCKBB02 command with v0 == 17476 found for TMK2014: {TMK2014}. Skipping task group.")
                    continue

                # Find TCS804 commands within 60 seconds after the TCKAF03 time
                matching_tcs804 = TCS804_commands[
                    (TCS804_commands['timestamp'] > tckaf03_time) &
                    (TCS804_commands['timestamp'] <= tckaf03_time + 60)
                    ]

                # Filter TCS804 commands based on DataSource == 1
                matching_tcs804_payload = matching_tcs804[
                    matching_tcs804['param'].apply(
                        lambda x: str_to_num(json.loads(x)['packageForm']['params'].get('DataSource')) == 1
                    )
                ]

                if matching_tcs804_payload.empty:
                    logger.info(
                        f"No matching TCS804 commands with DataSource == 1 found for TMK2014: {TMK2014}. Skipping task group.")
                    continue

                tcs804_list = []
                for _, tcs804_row in matching_tcs804_payload.iterrows():
                    try:
                        tcs804_params = json.loads(tcs804_row.get('param', '{}'))
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Invalid JSON in 'param' for TCS804 command at index {tcs804_row.name}. Skipping.")
                        continue

                    file_params = tcs804_params.get('packageForm', {}).get('params', {})

                    # Extract FileStart and FileEnd with conversion
                    file_start = str_to_num(file_params.get('FileStart'))
                    file_end = str_to_num(file_params.get('FileEnd'))

                    # Only append if both FileStart and FileEnd are valid
                    if file_start is not None and file_end is not None:
                        tcs804_list.append({
                            'timestamp': tcs804_row.get('timestamp'),
                            'FileStart': file_start,
                            'FileEnd': file_end
                        })
                    else:
                        logger.warning(
                            f"Invalid FileStart or FileEnd in TCS804 command at index {tcs804_row.name}. Skipping this TCS804 command.")
                        continue

                # Only append if there are valid TCS804 entries
                if tcs804_list:
                    payload_transmission_data.append({
                        'TMK2014': TMK2014,
                        'TMK2015': TMK2015,
                        'duration': duration,
                        'TCKAF03': {
                            'timestamp': tckaf03_time,
                            'params': tckaf03_package_params_converted
                        },
                        'TCS804': tcs804_list
                    })
                else:
                    logger.info(f"No valid TCS804 entries found for TMK2014: {TMK2014}. Skipping task group.")

    # Convert the result to JSON
    result = json.dumps(payload_transmission_data, ensure_ascii=False)
    return result


def AS03_platform_data_transmission(post_token_url,
                                    post_token_user_name,
                                    post_token_password,
                                    metedataservice_url,
                                    _influxdb_input,
                                    client_input,
                                    influxdb_action,
                                    host_action,
                                    tf1,
                                    tf2,
                                    satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Retrieve the command data
    AS03_payloaddatatransmission = get_AS02_datatransmission(
        post_token_url,
        post_token_user_name,
        post_token_password,
        metedataservice_url,
        _influxdb_input,
        client_input,
        tf1,
        tf2,
        satID
    )

    # Remove duplicate rows with the same TMK2014 and TMK2015 values, keeping only the first occurrence
    AS03_payloaddatatransmission = AS03_payloaddatatransmission.drop_duplicates(subset=['TMK2014', 'TMK2015'])

    # Initialize list to store the results
    payload_transmission_data = []

    # Iterate over each TMK2014 and TMK2015 pair
    for index, payload_row in AS03_payloaddatatransmission.iterrows():
        TMK2014 = payload_row.get('TMK2014')
        TMK2015 = payload_row.get('TMK2015')

        if TMK2014 != 0 and TMK2015 != 0:
            duration = TMK2015 - TMK2014

            # Calculate the start time for querying commands (48 hours before TMK2014)
            start_time = int(TMK2014 - 48 * 3600)
            end_time = int(TMK2014)

            # Convert start_time and end_time to datetime strings
            start_time_str = pd.to_datetime(start_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')
            end_time_str = pd.to_datetime(end_time, unit='s').strftime('%Y-%m-%dT%H:%M:%SZ')

            # Retrieve the command data for the specific time range
            AS02_commands = get_AScommands(
                post_token_url,
                post_token_user_name,
                post_token_password,
                metedataservice_url,
                influxdb_action,
                host_action,
                tf1=start_time_str,
                tf2=end_time_str,
                satID=satID
            )

            # Ensure 'cmd_code' column exists
            if 'cmd_code' not in AS02_commands.columns:
                logger.error(f"'cmd_code' column not found in AS02_commands DataFrame at index {index}. Skipping.")
                continue

            # Filter for relevant commands
            TCKAF03_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKAF03']
            TCS804_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCS804']
            TCKBB02_commands = AS02_commands[AS02_commands['cmd_code'] == 'TCKBB02']
            # Uncomment the following lines for debugging
            # print(TCKAF03_commands.to_string())
            # print(TCS804_commands.to_string())
            # print(TCKBB02_commands.to_string())

            # Find TCKAF03 commands with start equal to TMK2014
            matching_tckaf03 = TCKAF03_commands[
                TCKAF03_commands['param'].apply(
                    lambda x: str_to_num(json.loads(x)['packageForm']['params'].get('start')) == TMK2014
                )
            ]

            if not matching_tckaf03.empty:
                tckaf03_row = matching_tckaf03.iloc[0]
                tckaf03_time = tckaf03_row.get('timestamp')
                try:
                    tckaf03_params = json.loads(tckaf03_row.get('param', '{}'))
                except json.JSONDecodeError:
                    logger.warning(
                        f"Invalid JSON in 'param' for TCKAF03 command at index {tckaf03_row.name}. Skipping.")
                    continue

                # Extract parameters from TCKAF03
                tckaf03_package_params = tckaf03_params.get('packageForm', {}).get('params', {})
                # Convert all relevant parameters
                tckaf03_package_params_converted = {}
                for key, value in tckaf03_package_params.items():
                    tckaf03_package_params_converted[key] = str_to_num(value)

                # Check for TCKBB02 commands between TCKAF03's timestamp and TMK2014
                def is_cancel_task(param_str):
                    try:
                        param = json.loads(param_str)
                        v0 = str_to_num(param.get('packageForm', {}).get('params', {}).get('v0'))
                        logger.debug(f"Checking v0: {v0}")  # Debug log
                        return v0 == 17476
                    except json.JSONDecodeError:
                        return False

                matching_tckbb02 = TCKBB02_commands[
                    (TCKBB02_commands['timestamp'] > tckaf03_time) &
                    (TCKBB02_commands['timestamp'] <= TMK2014) &
                    (TCKBB02_commands['param'].apply(is_cancel_task))
                    ]

                # If TCKBB02 with v0 == 17476 is found, ignore this task group
                if not matching_tckbb02.empty:
                    logger.info(f"TCKBB02 command with v0 == 17476 found for TMK2014: {TMK2014}. Skipping task group.")
                    continue

                # Find TCS804 commands within 60 seconds after the TCKAF03 time
                matching_tcs804 = TCS804_commands[
                    (TCS804_commands['timestamp'] > tckaf03_time) &
                    (TCS804_commands['timestamp'] <= tckaf03_time + 60)
                    ]

                # Filter TCS804 commands based on DataSource == 0
                matching_tcs804_payload = matching_tcs804[
                    matching_tcs804['param'].apply(
                        lambda x: str_to_num(json.loads(x)['packageForm']['params'].get('DataSource')) == 0
                    )
                ]

                if matching_tcs804_payload.empty:
                    logger.info(
                        f"No matching TCS804 commands with DataSource == 0 found for TMK2014: {TMK2014}. Skipping task group.")
                    continue

                tcs804_list = []
                for _, tcs804_row in matching_tcs804_payload.iterrows():
                    try:
                        tcs804_params = json.loads(tcs804_row.get('param', '{}'))
                    except json.JSONDecodeError:
                        logger.warning(
                            f"Invalid JSON in 'param' for TCS804 command at index {tcs804_row.name}. Skipping.")
                        continue

                    file_params = tcs804_params.get('packageForm', {}).get('params', {})

                    # Extract FileStart and FileEnd with conversion
                    file_start = str_to_num(file_params.get('FileStart'))
                    file_end = str_to_num(file_params.get('FileEnd'))

                    # Only append if both FileStart and FileEnd are valid
                    if file_start is not None and file_end is not None:
                        tcs804_list.append({
                            'timestamp': tcs804_row.get('timestamp'),
                            'FileStart': file_start,
                            'FileEnd': file_end
                        })
                    else:
                        logger.warning(
                            f"Invalid FileStart or FileEnd in TCS804 command at index {tcs804_row.name}. Skipping this TCS804 command.")
                        continue

                # Only append if there are valid TCS804 entries
                if tcs804_list:
                    payload_transmission_data.append({
                        'TMK2014': TMK2014,
                        'TMK2015': TMK2015,
                        'duration': duration,
                        'TCKAF03': {
                            'timestamp': tckaf03_time,
                            'params': tckaf03_package_params_converted
                        },
                        'TCS804': tcs804_list
                    })
                else:
                    logger.info(f"No valid TCS804 entries found for TMK2014: {TMK2014}. Skipping task group.")

    # Convert the result to JSON
    result = json.dumps(payload_transmission_data, ensure_ascii=False)
    return result


def AS03_hist_file_save(post_token_url,
                        post_token_user_name,
                        post_token_password,
                        metedataservice_url,
                        _influxdb_input,
                        client_input,
                        influxdb_action,
                        host_action,
                        tf1,
                        tf2,
                        satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Helper function to convert hex strings to integers
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            else:
                return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    # Helper function to convert numerical strings to int or float
    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                num_str = num_str.strip()
                if num_str.lower().startswith("0x"):
                    return hex_to_int(num_str)
                elif '.' in num_str:
                    return float(num_str)
                else:
                    return int(num_str)
            else:
                return num_str  # If it's already a number
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    # Adjust tf2 by adding one day
    try:
        tf2_dt = datetime.strptime(tf2, "%Y-%m-%dT%H:%M:%S.%fZ")
        tf2_dt += timedelta(days=1)
        # Format back to the original string format with milliseconds precision
        tf2_adjusted = tf2_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except ValueError as e:
        logger.error(f"Invalid tf2 format: {e}")
        return json.dumps({'error': 'Invalid tf2 format'}, ensure_ascii=False)

    # Retrieve the command data with adjusted tf2
    try:
        AS03hist_file_save_command = get_AScommands(
            post_token_url,
            post_token_user_name,
            post_token_password,
            metedataservice_url,
            influxdb_action,
            host_action,
            tf1=tf1,
            tf2=tf2_adjusted,
            satID=satID
        )
    except Exception as e:
        logger.error(f"Error retrieving AS02_commands: {e}")
        return json.dumps({'error': 'Failed to retrieve AS02_commands'}, ensure_ascii=False)

    # Retrieve the telemetry data with adjusted tf2
    try:
        AS03hist_file_save_telemetry = get_AS03_hist_data_save(
            post_token_url,
            post_token_user_name,
            post_token_password,
            metedataservice_url,
            _influxdb_input,
            client_input,
            tf1=tf1,
            tf2=tf2_adjusted,
            satID=satID
        )
    except Exception as e:
        logger.error(f"Error retrieving AS03_hist_data_save: {e}")
        return json.dumps({'error': 'Failed to retrieve AS03_hist_data_save'}, ensure_ascii=False)

    # Initialize list to store the results
    hist_file_save_data = []

    # Define the timezone
    tz_utc = pytz.utc
    tz_local = pytz.timezone('Asia/Shanghai')

    # Filter for relevant commands
    TCS813_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCS813']
    TCS803_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCS803']
    TCH209_commands = AS03hist_file_save_command[AS03hist_file_save_command['cmd_code'] == 'TCH209']

    # Iterate over each TCS813 command
    for _, tcs813_row in TCS813_commands.iterrows():
        tcs813_time = tcs813_row.get('timestamp')
        try:
            tcs813_params = json.loads(tcs813_row.get('param', '{}'))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in 'param' for TCS813 command at index {tcs813_row.name}. Skipping.")
            continue

        # Check "Payload" == 0 (after conversion)
        payload = str_to_num(tcs813_params['packageForm']['params'].get('Payload'))
        if payload != 0:
            logger.info(f"TCS813 command at timestamp {tcs813_time} has Payload != 0. Skipping.")
            continue

        # Find the nearest TCS803 command after TCS813
        matching_tcs803 = TCS803_commands[TCS803_commands['timestamp'] > tcs813_time]

        if matching_tcs803.empty:
            logger.error('file_saving_stop_not_found(TCS803)')
            return json.dumps({'error': 'file_saving_stop_not_found(TCS803)'}, ensure_ascii=False)

        tcs803_row = matching_tcs803.iloc[0]
        tcs803_time = tcs803_row.get('timestamp')
        try:
            tcs803_params = json.loads(tcs803_row.get('param', '{}'))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in 'param' for TCS803 command at index {tcs803_row.name}. Skipping.")
            continue

        tcs803_delay_seconds_str = tcs803_params['delayForm']['seconds']
        try:
            # Parse the delay time and convert it to a timestamp
            tcs803_dt = datetime.strptime(tcs803_delay_seconds_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=tz_utc)
            tcs803_timestamp = int(tcs803_dt.timestamp())
        except ValueError:
            logger.warning(f"Invalid 'seconds' format in TCS803 command at index {tcs803_row.name}. Skipping.")
            continue

        # Find the corresponding TCH209 commands between TCS813 and TCS803
        matching_tch209 = TCH209_commands[
            (TCH209_commands['timestamp'] > tcs813_time) &
            (TCH209_commands['timestamp'] <= tcs803_time)
            ]

        tch209_filenames = []
        for _, tch209_row in matching_tch209.iterrows():
            try:
                tch209_params = json.loads(tch209_row.get('param', '{}'))
                filename = tch209_params['packageForm']['params'].get('filename')
                if filename:
                    tch209_filenames.append(filename)
                else:
                    logger.warning(f"Missing 'filename' in TCH209 command at index {tch209_row.name}.")
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in 'param' for TCH209 command at index {tch209_row.name}. Skipping.")
                continue

        # Find the first record in TMS043 after TCS813
        matching_tms043_start = AS03hist_file_save_telemetry[
            AS03hist_file_save_telemetry['timestamp'] > tcs813_time
            ]

        if matching_tms043_start.empty:
            logger.info(f"No TMS043 start record found after TCS813 timestamp {tcs813_time}. Skipping.")
            continue

        tms043_start_record = matching_tms043_start.iloc[0]
        tms043_start_time = tms043_start_record.get('timestamp')
        tms043_start_value = tms043_start_record.get('TMS043')
        if tms043_start_value is None:
            logger.warning(f"Missing 'TMS043' value in telemetry record at timestamp {tms043_start_time}. Skipping.")
            continue

        # Find the first record in TMS043 after TCS803's delay seconds
        matching_tms043_end = AS03hist_file_save_telemetry[
            AS03hist_file_save_telemetry['timestamp'] > tcs803_timestamp
            ]

        if matching_tms043_end.empty:
            logger.info(f"No TMS043 end record found after TCS803 timestamp {tcs803_timestamp}. Skipping.")
            continue

        tms043_end_record = matching_tms043_end.iloc[0]
        tms043_end_time = tms043_end_record.get('timestamp')
        tms043_end_value = tms043_end_record.get('TMS043')
        if tms043_end_value is None:
            logger.warning(f"Missing 'TMS043' value in telemetry record at timestamp {tms043_end_time}. Skipping.")
            continue

        # Calculate the absolute difference of values
        file_size = abs(tms043_end_value - tms043_start_value)

        # Extract 'File' parameter (assuming 'FIle' is a typo for 'File')
        # Handle both 'File' and 'FIle' due to potential inconsistencies
        file_param = tcs813_params['packageForm']['params'].get('File') or tcs813_params['packageForm']['params'].get(
            'FIle')
        save_to_number = str_to_num(file_param) if file_param else 0

        # **New Condition: Only append if 'files_saved' is not empty**
        if tch209_filenames:
            hist_file_save_data.append({
                'hist_data_saving_time': tcs813_time,
                'save_to_number': save_to_number,
                'files_saved': tch209_filenames,
                'file_size': file_size
            })
        else:
            logger.info(f"No files saved for hist_data_saving_time {tcs813_time}. Skipping.")

    # Convert the result to JSON
    try:
        result = json.dumps(hist_file_save_data, ensure_ascii=False)
    except TypeError as e:
        logger.error(f"Error converting hist_file_save_data to JSON: {e}")
        return json.dumps({'error': 'Failed to convert data to JSON'}, ensure_ascii=False)

    return result  # Removed the trailing comma to avoid returning a tuple


def AS03_delete_data_task(post_token_url,
                          post_token_user_name,
                          post_token_password,
                          metedataservice_url,
                          influxdb_action,
                          host_action,
                          tf1,
                          tf2,
                          satID):
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # ---- Helpers ----
    def hex_to_int(hex_str):
        try:
            if isinstance(hex_str, str) and hex_str.lower().startswith("0x"):
                return int(hex_str, 16)
            return int(hex_str)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert hex string to int: {hex_str}")
            return None

    def str_to_num(num_str):
        try:
            if isinstance(num_str, str):
                s = num_str.strip()
                if s.lower().startswith("0x"):
                    return hex_to_int(s)
                if '.' in s:
                    return float(s)
                return int(s)
            return num_str
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert string to number: {num_str}")
            return None

    def parse_delay_seconds(iso_str):
        """Accept 'YYYY-MM-DDTHH:MM:SSZ' or '...SS.sssZ'."""
        if not iso_str:
            return None
        tz_utc = pytz.utc
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(iso_str, fmt).replace(tzinfo=tz_utc)
                return int(dt.timestamp())
            except ValueError:
                continue
        logger.warning(f"Invalid 'seconds' format: {iso_str}")
        return None

    # ---- Load commands ----
    try:
        AS_commands = get_AScommands(
            post_token_url,
            post_token_user_name,
            post_token_password,
            metedataservice_url,
            influxdb_action,
            host_action,
            tf1=tf1,
            tf2=tf2,
            satID=satID
        )
    except Exception as e:
        logger.error(f"Error retrieving AS_commands: {e}")
        return json.dumps({'error': 'Failed to retrieve AS_commands'}, ensure_ascii=False)

    # Filter for TCS809 commands
    if AS_commands is None or len(AS_commands) == 0:
        return json.dumps([], ensure_ascii=False)

    TCS809_commands = AS_commands[AS_commands['cmd_code'] == 'TCS809']

    delete_records = []

    # ---- Parse rows ----
    for _, row in TCS809_commands.iterrows():
        cmd_ts = row.get('timestamp')
        param_str = row.get('param', '{}')

        try:
            obj = json.loads(param_str) if isinstance(param_str, str) else (param_str or {})
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in 'param' for TCS809 at index {row.name}. Skipping.")
            continue

        # delayForm may be inside param JSON; if not, try column fallbacks if present
        delay_form = obj.get('delayForm') or row.get('delayForm') or {}
        secs_iso = delay_form.get('seconds')
        tcs809_timestamp = parse_delay_seconds(secs_iso)
        if tcs809_timestamp is None:
            # no valid scheduled time => skip
            logger.warning(f"Missing/invalid delayForm.seconds for TCS809 at index {row.name}. Skipping.")
            continue

        package_form = obj.get('packageForm', {})
        package_params = package_form.get('params', {})

        # Normalize DataSource to "00"/"01"
        ds_raw = str(package_params.get('DataSource', '')).strip()
        if ds_raw.isdigit():
            data_source = ds_raw.zfill(2)  # "0"->"00", "1"->"01"
        else:
            data_source = ds_raw  # trust exact value if already "00"/"01"

        file_end = str_to_num(package_params.get('FileEnd'))
        file_start = str_to_num(package_params.get('FileStart'))

        if data_source == '' or file_end is None or file_start is None:
            logger.warning(f"Incomplete TCS809 params (DataSource/FileStart/FileEnd) at index {row.name}. Skipping.")
            continue

        delete_data_type = "0" if data_source == "00" else "1"

        delete_records.append({
            'command_time': cmd_ts,
            'delay_time': tcs809_timestamp,
            'params': {
                'DataSource': data_source,
                'FileEnd': file_end,
                'FileStart': file_start
            },
            'delete_data_type': delete_data_type
        })

    # ---- Dedupe by (DataSource, FileEnd, FileStart), keep earliest command_time ----
    seen = {}
    for d in delete_records:
        key = (d['params']['DataSource'], d['params']['FileEnd'], d['params']['FileStart'])
        if key not in seen or (seen[key]['command_time'] is None or
                               (d['command_time'] is not None and d['command_time'] < seen[key]['command_time'])):
            seen[key] = d

    unique_payload_data = list(seen.values())
    unique_payload_data.sort(key=lambda d: (d['delay_time'], d['params']['DataSource']))

    return json.dumps(unique_payload_data, ensure_ascii=False)
