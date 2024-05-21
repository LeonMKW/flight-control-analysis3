# -*- coding: UTF-8 -*-
import logging
import json
import pandas as pd
import numpy as np
from datetime import timedelta
from utils.flightcontrol_utils import vcIdnew, get_task_list, commands, correctframe, uplock, obc_resetnew, payload_pwr, file_inspect, \
    electric_propulsion, monitor_data, orbit_data, experimental_lock_data, experimental_telemetry_data, \
    hist_interval_data, gnss_interval_data
from tqdm import tqdm
from utils.db import set_value, init_val
from data.fileinspection import map_dict
from utils.core_algorithm import analyze_lock_intervals, analyze_lock_status, analyze_telemetry_intervals, \
    calculate_hist_interval, calculate_gnss_interval


logger = logging.getLogger(__name__)


def downlink_statics(orbit_service, mete_data_service, _influxdb, client, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    vcId_data = vcIdnew(mete_data_service, _influxdb, client, tf1, tf2, satID)

    init_val()
    set_value('total', len(task_list))

    # 理论过境时长
    task_list['duration'] = round((task_list['ending'] - task_list['starting']) /
                                  np.timedelta64(1, 's'))
    # 入境时间差
    time_gap: list = [None] * len(task_list)

    # for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
    for i in range(len(task_list)):
        start_time = task_list['starting'][i]
        end_time = task_list['ending'][i]

        mask = (vcId_data['time'] >= (start_time - timedelta(seconds=20))) & \
               (vcId_data['time'] <= (end_time + timedelta(seconds=20))) & \
               (vcId_data['_source'] == task_list['device'][i])

        diff = vcId_data[mask]
        if diff.empty:
            time_gap[i] = 'failed'
        else:
            first_valid_time = diff['time'].dropna().iloc[0]
            time_difference = (first_valid_time - start_time).total_seconds()
            time_gap[i] = round(time_difference, 2)

            if satID == '1':
                time_gap[i] = time_gap[i] - 27

            if time_gap[i] <= 0:
                time_gap[i] = 0

    task_list['timegap'] = time_gap
    # 理论下行帧计数
    if satID != '1':
        task_list['tdownlink'] = task_list['duration'] * 2
    else:
        task_list['tdownlink'] = task_list['duration'] / 2
    # 实际下行帧计数
    vcIdsum: list = [0] * len(task_list)
    ratio: list = [0] * len(task_list)

    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))
        if task_list['timegap'][i] == "failed":
            ratio[i] = "-"
        elif task_list['rally'][i] in ["missing_info", "normal"]:
            start_time = task_list['starting'][i] - pd.Timedelta(seconds=60)
            end_time = task_list['ending'][i] + pd.Timedelta(seconds=300)
            vcIdcount = vcId_data[(vcId_data['time'] >= start_time) & (vcId_data['time'] <= end_time)]
            vcIdsum[i] = len(vcIdcount)
            ratio[
                i] = f"{100 if vcIdsum[i] / task_list['tdownlink'][i] >= 1 else round(vcIdsum[i] / task_list['tdownlink'][i], 2) * 100:.2f}% "
        elif task_list['rally'][i] in ["rallylast", "rallynext"]:
            start_time = task_list['starting'][i] - pd.Timedelta(seconds=60)
            end_time = task_list['ending'][i] + pd.Timedelta(seconds=300)
            vcIdcount = vcId_data[(vcId_data['time'] >= start_time) &
                                  (vcId_data['time'] <= end_time) &
                                  (vcId_data['_source'] == task_list['device'][i])
                                  ]
            vcIdsum[i] = len(vcIdcount)
            ratio[
                i] = f"{100 if vcIdsum[i] / task_list['tdownlink'][i] >= 1 else round(vcIdsum[i] / task_list['tdownlink'][i], 2) * 100:.2f}% "
        else:
            ratio[i] = "-"

    task_list['rdownlink'] = vcIdsum
    task_list['ratio'] = ratio

    # Convert 'rdownlink' column to 'object' dtype
    task_list['rdownlink'] = task_list['rdownlink'].astype('object')

    # Perform the assignment
    task_list.loc[task_list['timegap'] == '跟踪失败', 'rdownlink'] = '未发现下行帧'
    # task_list.loc[(task_list['rally'] == 'rallynext') | (task_list['rally'] == 'rallylast'), 'rdownlink'] = '接力'

    # print(task_list.to_string())
    # task_list = task_list.to_json(orient='records')
    # return task_list

    # Count the frequency of 'company_name', 'rally', "failed" in 'timegap', length of task_list, and 'station_name'
    company_name_counts = task_list['company_name'].value_counts().to_dict()
    rally_counts = task_list['rally'].value_counts().to_dict()
    failed_timegap_count = int(task_list['timegap'].value_counts().get('failed', 0))
    task_list_length = len(task_list)
    station_name_counts = task_list['station_name'].value_counts().to_dict()

    # Combine the counts with the task_list
    result = {
        'task_list': json.loads(task_list.to_json(orient='records')),
        'company_name_counts': company_name_counts,
        'rally_counts': rally_counts,
        'failed': failed_timegap_count,
        'total_tasks': task_list_length,
        'station_name_counts': station_name_counts
    }

    result = json.dumps(result, ensure_ascii=False)
    return result


def downlink_statics_experiment(orbit_service, mete_data_service, _influxdb, client, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    vcId_data = vcIdnew(mete_data_service, _influxdb, client, tf1, tf2, satID)

    init_val()
    set_value('total', len(task_list))

    # 理论过境时长
    task_list['duration'] = round((task_list['ending'] - task_list['starting']) /
                                  np.timedelta64(1, 's'))
    # 入境时间差
    time_gap: list = [None] * len(task_list)

    # for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
    for i in range(len(task_list)):
        start_time = task_list['starting'][i]
        end_time = task_list['ending'][i]

        mask = (vcId_data['time'] >= (start_time - timedelta(seconds=20))) & \
               (vcId_data['time'] <= (end_time + timedelta(seconds=20))) & \
               (vcId_data['_source'] == task_list['device'][i])

        diff = vcId_data[mask]
        if diff.empty:
            time_gap[i] = 'failed'
        else:
            first_valid_time = diff['time'].dropna().iloc[0]
            time_difference = (first_valid_time - start_time).total_seconds()
            time_gap[i] = round(time_difference, 2)

            if satID == '1':
                time_gap[i] = time_gap[i] - 27

            if time_gap[i] <= 0:
                time_gap[i] = 0

    task_list['timegap'] = time_gap
    # 理论下行帧计数
    if satID != '1':
        task_list['tdownlink'] = task_list['duration'] * 2
    else:
        task_list['tdownlink'] = task_list['duration'] / 2
    # 实际下行帧计数
    vcIdsum: list = [0] * len(task_list)
    ratio: list = [0] * len(task_list)

    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))
        if task_list['timegap'][i] == "failed":
            ratio[i] = "-"
        elif task_list['rally'][i] in ["missing_info", "normal"]:
            start_time = task_list['starting'][i] - pd.Timedelta(seconds=60)
            end_time = task_list['ending'][i] + pd.Timedelta(seconds=300)
            vcIdcount = vcId_data[(vcId_data['time'] >= start_time) & (vcId_data['time'] <= end_time)]
            vcIdsum[i] = len(vcIdcount)
            ratio[
                i] = f"{100 if vcIdsum[i] / task_list['tdownlink'][i] >= 1 else round(vcIdsum[i] / task_list['tdownlink'][i], 2) * 100:.2f}% "
        elif task_list['rally'][i] in ["rallylast", "rallynext"]:
            start_time = task_list['starting'][i] - pd.Timedelta(seconds=60)
            end_time = task_list['ending'][i] + pd.Timedelta(seconds=300)
            vcIdcount = vcId_data[(vcId_data['time'] >= start_time) &
                                  (vcId_data['time'] <= end_time) &
                                  (vcId_data['_source'] == task_list['device'][i])
                                  ]
            vcIdsum[i] = len(vcIdcount)
            ratio[
                i] = f"{100 if vcIdsum[i] / task_list['tdownlink'][i] >= 1 else round(vcIdsum[i] / task_list['tdownlink'][i], 2) * 100:.2f}% "
        else:
            ratio[i] = "-"

    task_list['rdownlink'] = vcIdsum
    task_list['ratio'] = ratio

    # Convert 'rdownlink' column to 'object' dtype
    task_list['rdownlink'] = task_list['rdownlink'].astype('object')

    # Perform the assignment
    task_list.loc[task_list['timegap'] == '跟踪失败', 'rdownlink'] = '未发现下行帧'
    # Modify the structure of the result
    modified_task_list = [{'mission_id': mission['mission_id'], 'mission': mission} for mission in
                          json.loads(task_list.to_json(orient='records'))]

    result = {
        'task_list': modified_task_list,
    }

    result = json.dumps(result, ensure_ascii=False)
    return result


def uplink_statics_new(orbit_service, mete_data_service, _influxdb_input, client_input, _influxdb_action, client_action,
                       tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    correctframe_data = correctframe(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    uplock_data = uplock(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)

    control_command = [0] * len(task_list)
    TMH3005 = [0] * len(task_list)
    telecontrol_diff = [0] * len(task_list)
    multi_device_id = [0] * len(task_list)
    telecontrol_total = [0] * len(task_list)

    init_val()
    set_value('total', len(task_list))

    # for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))
        satellite_code = task_list['satellite_code'][i]
        antenna = task_list['device'][i]

        TMH3005test = correctframe_data[
            (correctframe_data['time'] >= task_list['starting'].iloc[i]) &
            (correctframe_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=300))
            ].dropna()

        controltest = control_data[
            (control_data['time'] >= task_list['starting'].iloc[i]) &
            (control_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120)) &
            (control_data['satellite_code'] == satellite_code) &
            (control_data['antenna_code'] == antenna)
            ]

        xbitlocktest = uplock_data[
            (uplock_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (uplock_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        unlock_stat, lock_interval, auto_lock = analyze_lock_status(xbitlocktest, satID)
        task_list.at[i, 'unlock_stat'] = int(unlock_stat)
        task_list.at[i, 'auto_lock'] = int(auto_lock)
        task_list.at[i, 'lock_interval'] = int(lock_interval)

        if not TMH3005test['correct_command'].isnull().all():
            if TMH3005test['correct_command'].iloc[0] == 0:
                TMH3005[i] = TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0]
            elif 255 in TMH3005test['correct_command'].values:
                TMH3005[i] = (255 - TMH3005test['correct_command'].iloc[0]) + TMH3005test['correct_command'].iloc[
                    -1] + 1
            elif (255 not in TMH3005test['correct_command'].values) and (0 in TMH3005test['correct_command'].values):
                zero_index_series = (TMH3005test['correct_command'] == 0)
                if zero_index_series.any():
                    zero_index = zero_index_series.argmax() - 1
                    TMH3005[i] = (TMH3005test['correct_command'].iloc[zero_index] - TMH3005test['correct_command'].iloc[
                        0]) + TMH3005test['correct_command'].iloc[-1] + 1
                else:
                    TMH3005[i] = (TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0])
            else:
                TMH3005[i] = (TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0])
        else:
            TMH3005[i] = 0

        if controltest['antenna_code'].nunique() >= 2:
            multi_device_id[i] = 1
        else:
            multi_device_id[i] = 0

        if not controltest['satellite_code'].isnull().all():
            control_command[i] = len(controltest)
        else:
            control_command[i] = 0

        telecontrol_diff[i] = control_command[i] - TMH3005[i]
        telecontrol_total[i] = abs(control_command[i]) + abs(TMH3005[i])

        task_list['up'] = control_command
        task_list['increase'] = list(map(int, TMH3005))
        task_list['diff'] = list(map(int, telecontrol_diff))

    uplink_status = []

    for i in range(len(telecontrol_diff)):
        if telecontrol_diff[i] != 0:
            if telecontrol_total[i] == 256:
                uplink_status.append({'missing': 0})
            else:
                uplink_status.append({'missing': telecontrol_diff[i]})
        else:
            uplink_status.append({'missing': 0})

    task_list = pd.concat([task_list, pd.DataFrame(uplink_status)], axis=1)

    # uplink_frequencies = task_list[['missing']].sum().to_dict()
    uplink_frequencies = int(task_list[task_list['missing'] != 0]['missing'].count())

    # print(uplink_frequencies)

    # Combine the counts with the task_list
    result = {
        'task_list': json.loads(task_list.to_json(orient='records')),
        'missing_frequencies': uplink_frequencies
    }
    result = json.dumps(result, ensure_ascii=False)

    return result


def uplink_statics_experiment(orbit_service, mete_data_service, _influxdb_input, client_input, _influxdb_action,
                              client_action,
                              tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    correctframe_data = correctframe(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    uplock_data = uplock(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)

    control_command = [0] * len(task_list)
    TMH3005 = [0] * len(task_list)
    telecontrol_diff = [0] * len(task_list)
    multi_device_id = [0] * len(task_list)
    telecontrol_total = [0] * len(task_list)

    init_val()
    set_value('total', len(task_list))

    # for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))
        satellite_code = task_list['satellite_code'][i]
        antenna = task_list['device'][i]

        TMH3005test = correctframe_data[
            (correctframe_data['time'] >= task_list['starting'].iloc[i]) &
            (correctframe_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=300))
            ].dropna()

        controltest = control_data[
            (control_data['time'] >= task_list['starting'].iloc[i]) &
            (control_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120)) &
            (control_data['satellite_code'] == satellite_code) &
            (control_data['antenna_code'] == antenna)
            ]

        xbitlocktest = uplock_data[
            (uplock_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (uplock_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        unlock_stat, lock_interval, auto_lock = analyze_lock_status(xbitlocktest, satID)
        task_list.at[i, 'unlock_stat'] = int(unlock_stat)
        task_list.at[i, 'auto_lock'] = int(auto_lock)
        task_list.at[i, 'lock_interval'] = int(lock_interval)

        if not TMH3005test['correct_command'].isnull().all():
            if TMH3005test['correct_command'].iloc[0] == 0:
                TMH3005[i] = TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0]
            elif 255 in TMH3005test['correct_command'].values:
                TMH3005[i] = (255 - TMH3005test['correct_command'].iloc[0]) + TMH3005test['correct_command'].iloc[
                    -1] + 1
            elif (255 not in TMH3005test['correct_command'].values) and (0 in TMH3005test['correct_command'].values):
                zero_index_series = (TMH3005test['correct_command'] == 0)
                if zero_index_series.any():
                    zero_index = zero_index_series.argmax() - 1
                    TMH3005[i] = (TMH3005test['correct_command'].iloc[zero_index] - TMH3005test['correct_command'].iloc[
                        0]) + TMH3005test['correct_command'].iloc[-1] + 1
                else:
                    TMH3005[i] = (TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0])
            else:
                TMH3005[i] = (TMH3005test['correct_command'].iloc[-1] - TMH3005test['correct_command'].iloc[0])
        else:
            TMH3005[i] = 0

        if controltest['antenna_code'].nunique() >= 2:
            multi_device_id[i] = 1
        else:
            multi_device_id[i] = 0

        if not controltest['satellite_code'].isnull().all():
            control_command[i] = len(controltest)
        else:
            control_command[i] = 0

        telecontrol_diff[i] = control_command[i] - TMH3005[i]
        telecontrol_total[i] = abs(control_command[i]) + abs(TMH3005[i])

        task_list['up'] = control_command
        task_list['increase'] = list(map(int, TMH3005))
        task_list['diff'] = list(map(int, telecontrol_diff))

    uplink_status = []

    for i in range(len(telecontrol_diff)):
        if telecontrol_diff[i] != 0:
            if telecontrol_total[i] == 256:
                uplink_status.append({'missing': 0})
            else:
                uplink_status.append({'missing': telecontrol_diff[i]})
        else:
            uplink_status.append({'missing': 0})

    task_list = pd.concat([task_list, pd.DataFrame(uplink_status)], axis=1)

    # Modify the structure of the result
    modified_task_list = [{'mission_id': mission['mission_id'], 'mission': mission} for mission in
                          json.loads(task_list.to_json(orient='records'))]

    result = {
        'task_list': modified_task_list,
    }

    result = json.dumps(result, ensure_ascii=False)
    return result


def target_detect(orbit_service, mete_data_service, _influxdb, client, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    TMS002_data = obc_resetnew(mete_data_service, _influxdb, client, tf1, tf2, satID)
    anomal = [' '] * len(task_list)

    for i in range(len(task_list)):
        TMS002 = TMS002_data[
            (TMS002_data['time'] >= task_list['starting'].iloc[i]) &
            (TMS002_data['time'] <= task_list['ending'].iloc[i])
            ]

        if TMS002.empty:
            anomal[i] = '跟踪失败'
        else:
            anomal[i] = '发现目标'
            # if TMS002['obc_reset'].iloc[0] > 0:
            #     anomal[i] = '境外复位'
            # elif TMS002['obc_reset'].iloc[0] == 0 and not TMS002['obc_reset'].eq(0).all():
            #     anomal[i] = '境内复位'
            # elif len(TMS002['obc_switch'].unique()) == 2:
            #     anomal[i] = 'OBC切机'

    task_list['targetdetect'] = anomal

    # # Count the frequency of reset values
    # reset_frequencies = task_list['reset'].value_counts().to_dict()
    # reset_frequencies['无复位'] = reset_frequencies.pop(' ')

    target_frequencies = task_list['targetdetect'].value_counts().to_dict()

    # if ' ' in target_frequencies:
    #     target_frequencies['无复位'] = target_frequencies.pop(' ')
    # else:
    #     print('targetdetect-statics warning: all mission anomal')
    #     pass

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['targetdetect'] != "发现目标"]

    result = {
        # 'task_list_all': json.loads(task_list.to_json(orient='records')),
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'target_frequencies': target_frequencies
    }
    # pprint.pprint(result)

    return json.dumps(result, ensure_ascii=False)


def satcom(orbit_service, mete_data_service, _influxdb, client, _influxdb_action, client_action, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    payload_power = payload_pwr(mete_data_service, _influxdb, client, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    com_status = [' '] * len(task_list)

    if len(payload_power) < 1:
        com_status = [''] * len(task_list)
    else:
        for i in range(len(task_list)):
            payload = payload_power[
                (payload_power['time'] >= task_list['starting'].iloc[i]) &
                (payload_power['time'] <= task_list['ending'].iloc[i])
                ]

            command = control_data[
                (control_data['time'] >= task_list['starting'].iloc[i]) &
                (control_data['time'] <= task_list['ending'].iloc[i])
                ]

            if satID == '1':
                if (
                        (payload['payload_signal1'].between(1.8, 2.7).any() and
                         payload['payload_signal2'].between(1.8, 2.5).any()) and
                        'TCH0112' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(1.8, 2.7).any() and
                         payload['payload_signal2'].between(1.8, 2.5).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = ''

            elif satID == '2':
                if (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any()) and
                        'K8425' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = ''

            elif satID == '7':
                if (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any()) and
                        'K8409' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = ''

            elif satID == '14':
                if (
                        (payload['payload_signal1'].between(1, 5).any() or
                         payload['payload_signal2'].between(1, 5).any()) and
                        'K8409' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(1, 5).any() or
                         payload['payload_signal2'].between(1, 5).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = ''

            else:
                if (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(3.05, 3.65).any()) and
                        'K8425' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(3.05, 3.65).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = ''

    task_list['com_status'] = com_status

    # Count the frequency of com_status values
    com_status_frequencies = task_list['com_status'].value_counts().to_dict()

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['com_status'] != ""]

    result = {
        'task_list_all': json.loads(task_list.to_json(orient='records')),
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'com_status_frequencies': com_status_frequencies
    }

    return json.dumps(result, ensure_ascii=False)


def my_fun(n):
    if n == 2 or n == 170:
        return True


def spiderling_file_inspection(orbit_service, mete_data_service, _influxdb, _client, _influxdb_action, client_action,
                               tf1, tf2,
                               satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    fileinspectdata = file_inspect(mete_data_service, _influxdb, _client, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    map_file = map_dict

    fileinspect: list = [None] * len(task_list)
    fileinspectsum: list = [None] * len(task_list)

    for i in range(len(task_list)):
        if fileinspectdata.empty:
            fileinspect[i] = ""
            fileinspectsum[i] = ''
        else:
            controlK8643 = control_data[(control_data['time'] >= task_list['starting'].iloc[i]) &
                                        (control_data['time'] <= task_list['ending'].iloc[i])]

            filedata = fileinspectdata[(fileinspectdata['time'] >= task_list['starting'].iloc[i]) &
                                       (fileinspectdata['time'] <= task_list['ending'].iloc[i])]

            if filedata.empty:
                fileinspect[i] = ""
                fileinspectsum[i] = ''
            elif (
                    ((filedata.iloc[:, 1:] == 170).any().any() or
                     (filedata.iloc[:, 1:] == 2).any().any()) and
                    (any(controlK8643['cmd_code'].eq("K8643")) or
                     any(controlK8643['cmd_code'].eq("TCH0343")) or
                     any(controlK8643['cmd_code'].eq("TCH271"))
                    )
            ):
                abnormal_columns = ", ".join(
                    filedata.columns[1:][filedata.iloc[:, 1:].apply(
                        lambda x: (x == 170) | (x == 2)
                    ).any()])

                # sat_id = str(task_list['satID'][i])
                abnormal_columns_mapped = ", ".join(
                    map_file.get(satID, {}).get(col, col)
                    for col in abnormal_columns.split(", ")
                )
                fileinspect[i] = f"发现异常文件:{abnormal_columns_mapped} "
                fileinspectsum[i] = '异常'
            else:
                fileinspect[i] = "文件巡检正常"
                fileinspectsum[i] = "正常"

    task_list['fileinspect'] = fileinspect
    task_list['fileinspectsum'] = fileinspectsum

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['fileinspect'] != ""]

    fileinspect_frequency = pd.Series(fileinspect).value_counts().to_dict()
    fileinspect_only = pd.Series(task_list_filtered['fileinspect']).value_counts().to_dict()
    fileinspectsum_frequency = pd.Series(task_list_filtered['fileinspectsum']).value_counts().to_dict()

    # Create a JSON object with 'task_list' and 'fileinspect_frequency'
    result = {
        'task_list_all': json.loads(task_list.to_json(orient='records')),
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'fileinspect_frequency_all': fileinspect_frequency,
        'fileinspect_frequency': fileinspect_only,
        'fileinspectsum_frequency': fileinspectsum_frequency
    }
    # print(result)

    return json.dumps(result, ensure_ascii=False)


def spiderling_file_inspect_experiment(orbit_service, mete_data_service, _influxdb, _client, _influxdb_action,
                                       client_action, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    fileinspectdata = file_inspect(mete_data_service, _influxdb, _client, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    map_file = map_dict
    missions = []

    fileinspect: list = [None] * len(task_list)
    fileinspectsum: list = [None] * len(task_list)

    for i in range(len(task_list)):
        if fileinspectdata.empty:
            fileinspect[i] = ""
            fileinspectsum[i] = ''
        else:
            controlK8643 = control_data[(control_data['time'] >= task_list['starting'].iloc[i]) &
                                        (control_data['time'] <= task_list['ending'].iloc[i])]

            filedata = fileinspectdata[(fileinspectdata['time'] >= task_list['starting'].iloc[i]) &
                                       (fileinspectdata['time'] <= task_list['ending'].iloc[i])]

            if filedata.empty:
                fileinspect[i] = ""
                fileinspectsum[i] = ''
            elif (
                    ((filedata.iloc[:, 1:] == 170).any().any() or (filedata.iloc[:, 1:] == 2).any().any()) and
                    (any(controlK8643['cmd_code'].eq("K8643")) or any(controlK8643['cmd_code'].eq("TCH0343")))
            ):
                abnormal_columns = ", ".join(
                    filedata.columns[1:][filedata.iloc[:, 1:].apply(
                        lambda x: (x == 170) | (x == 2)
                    ).any()])

                # sat_id = str(task_list['satID'][i])
                abnormal_columns_mapped = ", ".join(
                    map_file.get(satID, {}).get(col, col)
                    for col in abnormal_columns.split(", ")
                )
                fileinspect[i] = f"发现异常文件:{abnormal_columns_mapped} "
                fileinspectsum[i] = '异常'
            else:
                fileinspect[i] = "文件巡检正常"
                fileinspectsum[i] = "正常"

    task_list['fileinspect'] = fileinspect
    task_list['fileinspectsum'] = fileinspectsum

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['fileinspect'] != ""]
    drop = ['remark', 'satellite_id', 'station_name', 'device', 'antID',
            'approach_angle', 'max_elvation', 'departure_angle', 'company_name', 'rally']
    task_list_filtered = task_list_filtered.drop(drop, axis=1)

    missions = []

    grouped_tasks = task_list_filtered.groupby('mission_id')
    # Iterate over each mission_id group
    for mission_id, tasks in grouped_tasks:
        # Convert tasks to JSON records
        tasks = json.loads(tasks.to_json(orient='records'))
        res = {}
        for item in tasks:
            res.update(item)

        mission = {
            "mission_id": mission_id,
            "mission": res
        }
        missions.append(mission)

    # final_json = { }
    #
    # for item in mission

    final_json = {"task_list": missions}
    final_json_string = json.dumps(final_json, indent=4)

    return final_json_string


# def orbit_precision_analysis(orbit_propagation_url, mete_data_service, _influxdb, client, tf1, tf2, satID,
#                              CD, M, a, dw, e, i, keplerID, label, periods, radiationFlow, satelliteArea,
#                              satelliteWeight, step, thrust, thrusterWorking, value, xw):
#     gnss_data = get_gnss_data(mete_data_service, _influxdb, client, tf1, tf2, satID)
#     propagation_data =


def general_anomal(orbit_service, mete_data_service, _influxdb, client, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    TMS002_data = obc_resetnew(mete_data_service, _influxdb, client, tf1, tf2, satID)
    anomal = [' '] * len(task_list)

    for i in range(len(task_list)):
        TMS002 = TMS002_data[
            (TMS002_data['time'] >= task_list['starting'].iloc[i]) &
            (TMS002_data['time'] <= task_list['ending'].iloc[i])
            ]

        if TMS002.empty:
            anomal[i] = '跟踪失败'
        else:
            anomal[i] = ''
            if TMS002['obc_reset'].iloc[0] > 0:
                anomal[i] = '境外复位'
            elif TMS002['obc_reset'].iloc[0] == 0 and not TMS002['obc_reset'].eq(0).all():
                anomal[i] = '境内复位'
            elif len(TMS002['obc_switch'].unique()) == 2:
                anomal[i] = 'OBC切机'

    task_list['anomal'] = anomal

    # Filter task_list where anomal is not ''
    task_list_filtered = task_list[task_list['anomal'] != '']

    # Count frequency of non-empty anomalies
    anomal_frequencies = task_list_filtered['anomal'].value_counts().to_dict()

    result = {
        'task_list_all': json.loads(task_list.to_json(orient='records')),
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'anomal_frequencies': anomal_frequencies
    }
    # pprint.pprint(result)

    return json.dumps(result, ensure_ascii=False)


def orbit_control(orbit_service, mete_data_service,
                  _influxdb_chonograf, client_chronograf,
                  _influxdb, client,
                  tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    TMT041_data = electric_propulsion(mete_data_service, _influxdb, client, tf1, tf2, satID)
    tmonitor_data = monitor_data(mete_data_service, _influxdb_chonograf, client_chronograf, tf1, tf2, satID)
    fire_status = [""] * len(task_list)

    if tmonitor_data.empty:
        task_list['fire_status'] = fire_status
    else:
        for i in range(len(task_list)):
            monitor_fire = tmonitor_data[
                (tmonitor_data['time'] >= task_list['starting'].iloc[i]) &
                (tmonitor_data['time'] <= task_list['ending'].iloc[i])
                ]

            propulsion = TMT041_data[
                (TMT041_data['time'] >= task_list['starting'].iloc[i]) &
                (TMT041_data['time'] <= task_list['ending'].iloc[i])
                ]

            # Check fire time
            if monitor_fire.empty:
                fire_status[i] = ""
            elif len(monitor_fire) > 2:
                fire_status[i] = "出现多个序列"
            elif not monitor_fire['fire'].eq(0.0).all():
                # max_value_time = monitor_fire.loc[monitor_fire['fire'].idxmax(), 'time']
                max_fire_timestamp = int(monitor_fire['fire'].max())
                # max_value_time_utc = pd.to_datetime(max_fire_timestamp, unit='s', utc=True)
                # cst = pytz.timezone('Asia/Shanghai')
                # max_value_time_cst = max_value_time_utc.astimezone(cst)
                fire_status[i] = f"{max_fire_timestamp}"
            elif not propulsion['electric_propulsion'].eq(0.0).all() and \
                    propulsion['electric_propulsion'].eq(7.0).any():
                fire_status[i] = "异常结束"
            elif not propulsion['electric_propulsion'].eq(0.0).all() and \
                    propulsion['electric_propulsion'].eq(6.0).any():
                fire_status[i] = "正常结束"
            else:
                fire_status[i] = "请备注"

        task_list['fire_status'] = fire_status

    # print(task_list.to_string())
    return task_list


def orbit_statistics(orbit_service, mete_data_service,
                     _influxdb, client,
                     tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    tmk045data = orbit_data(mete_data_service, _influxdb, client, tf1, tf2, satID)

    orbit_status = [] * len(task_list)

    for i in range(len(task_list)):
        TMK045 = tmk045data.loc[
            (tmk045data['time'] >= task_list['starting'].iloc[i]) &
            (tmk045data['time'] <= task_list['ending'].iloc[i])
            ]

        if TMK045['orbit_stat'].isna().all():
            orbit_status.append('nodata')
        elif (TMK045['orbit_stat'] == 0).any():
            zero_indices = TMK045.loc[TMK045['orbit_stat'] == 0].index
            time_diff = (TMK045.loc[zero_indices, 'time'] -
                         TMK045.loc[zero_indices - 1, 'time']).sum()
            time_diff_seconds = max(1, time_diff.total_seconds())
            orbit_status.append(f"不可用{time_diff_seconds}s")
        else:
            orbit_status.append('可用')

    task_list['orbit_status'] = orbit_status
    # print(task_list.to_string())
    return task_list


def experimental_uplock(orbit_service, mete_data_service, _influxdb_input, client_input,
                        tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    uplock_data = experimental_lock_data(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    missions = []  # List to store results for each task

    init_val()
    set_value('total', len(task_list))

    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))

        xbitlocktest = uplock_data[
            (uplock_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (uplock_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        if not xbitlocktest.empty:  # Check if DataFrame is not empty
            lock_df = analyze_lock_intervals(xbitlocktest, satID)
            # Add mission_id to the lock_df dictionary
            lock_df['mission_id'] = task_list['mission_id'].iloc[i]
            lock_df['satellite_code'] = task_list['satellite_code'].iloc[i]
            lock_df['starting'] = round(task_list['starting'].iloc[i].timestamp() * 1000)
            lock_df['ending'] = round(task_list['ending'].iloc[i].timestamp() * 1000)
        else:
            # Set default values if DataFrame is empty
            lock_df = {
                'mission_id': task_list['mission_id'].iloc[i],
                'satellite_code': task_list['satellite_code'].iloc[i],
                'starting': round(task_list['starting'].iloc[i].timestamp() * 1000),
                'ending': round(task_list['ending'].iloc[i].timestamp() * 1000),
                "total_group_number": 0,
                "interrupt_group": 0,
                "longest_down_length": 0,
                "longest_group_number": 0,
                "longestlock_start": 0,
                "longestlock_end": 0
            }

        # Extract mission ID from task_list
        mission_id = task_list['mission_id'].iloc[i]

        # Construct the mission dictionary with "mission_id" outside the brackets
        task = {"mission_id": mission_id, "mission": lock_df}
        missions.append(task)

    # Wrap the mission list in an outer dictionary
    results = {"task_list": missions}

    # print(results)

    return json.dumps(results)


def experimental_telemetry(orbit_service, mete_data_service, _influxdb_input, client_input,
                           tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    down_data = experimental_telemetry_data(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    missions = []

    init_val()
    set_value('total', len(task_list))

    for i in range(len(task_list)):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))

        xbitlocktest = down_data[
            (down_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (down_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        if not xbitlocktest.empty:  # Check if DataFrame is not empty
            lock_df = analyze_telemetry_intervals(xbitlocktest)
            # Add mission_id to the lock_df dictionary
            lock_df['mission_id'] = task_list['mission_id'].iloc[i]
            lock_df['satellite_code'] = task_list['satellite_code'].iloc[i]
            lock_df['starting'] = round(task_list['starting'].iloc[i].timestamp() * 1000)
            lock_df['ending'] = round(task_list['ending'].iloc[i].timestamp() * 1000)
        else:
            lock_df = {'mission_id': task_list['mission_id'].iloc[i],
                       'satellite_code': task_list['satellite_code'].iloc[i],
                       'starting': round(task_list['starting'].iloc[i].timestamp() * 1000),
                       'ending': round(task_list['ending'].iloc[i].timestamp() * 1000),
                       'total_group_number': 0,
                       'interrupt_group': 0,
                       'longest_down_length': 0,
                       'longest_group_number': 0,
                       'longestdown_start': 0,
                       'longestdown_end': 0}

        # Extract mission ID from task_list
        mission_id = task_list['mission_id'].iloc[i]

        # Construct the mission dictionary with "mission_id" outside the brackets
        task = {"mission_id": mission_id, "mission": lock_df}
        missions.append(task)

    # Wrap the mission list in an outer dictionary
    results = {"task_list": missions}

    # print(results)

    return json.dumps(results)


def hist_interval(orbit_service, mete_data_service, _influxdb_input, client_input, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    hist_data = hist_interval_data(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    missions = []

    for i in range(len(task_list)):
        intervals = hist_data[
            (hist_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (hist_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        lock_df = calculate_hist_interval(intervals)

        # Extract mission ID from task_list
        mission_id = task_list['mission_id'].iloc[i]
        # Add mission_id to the lock_df dictionary
        lock_df['mission_id'] = task_list['mission_id'].iloc[i]
        lock_df['satellite_code'] = task_list['satellite_code'].iloc[i]
        lock_df['starting'] = round(task_list['starting'].iloc[i].timestamp() * 1000)
        lock_df['ending'] = round(task_list['ending'].iloc[i].timestamp() * 1000)

        # Construct the mission dictionary with "mission_id" outside the brackets
        task = {"mission_id": mission_id, "mission": lock_df}
        missions.append(task)

    # Wrap the mission list in an outer dictionary
    results = {"task_list": missions}

    # print(results)

    return json.dumps(results)


def gnss_interval(orbit_service, mete_data_service, _influxdb_input, client_input, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    # print(task_list.to_string())
    gnss_data = gnss_interval_data(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)
    # print(gnss_data.to_string())
    missions = []

    for i in range(len(task_list)):
        intervals = gnss_data[
            (gnss_data['time'] >= task_list['starting'].iloc[i] - pd.Timedelta(seconds=30)) &
            (gnss_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120))
            ]

        lock_df = calculate_gnss_interval(intervals)

        # Extract mission ID from task_list
        mission_id = task_list['mission_id'].iloc[i]
        # Add mission_id to the lock_df dictionary
        lock_df['mission_id'] = task_list['mission_id'].iloc[i]
        lock_df['satellite_code'] = task_list['satellite_code'].iloc[i]
        lock_df['starting'] = round(task_list['starting'].iloc[i].timestamp() * 1000)
        lock_df['ending'] = round(task_list['ending'].iloc[i].timestamp() * 1000)

        # Construct the mission dictionary with "mission_id" outside the brackets
        task = {"mission_id": mission_id, "mission": lock_df}
        missions.append(task)

    # Wrap the mission list in an outer dictionary
    results = {"task_list": missions}

    # print(results)

    return json.dumps(results)

# if __name__ == '__main__':
#     downlink_statics()
