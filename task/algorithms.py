# -*- coding: UTF-8 -*-
import logging
import pprint
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from utils.utils import vcIdnew, get_task_list, commands, correctframe, obc_resetnew, payload_pwr, file_inspect, \
    get_gnss_data
from tqdm import tqdm
from utils.db import set_value, init_val

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

    for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
        start_time = task_list['starting'][i]
        end_time = task_list['ending'][i]

        mask = (vcId_data['time'] >= (start_time - timedelta(seconds=20))) & \
               (vcId_data['time'] <= (end_time + timedelta(seconds=20)))
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
        if task_list['timegap'][i] == "failed" or task_list['rally'][i] in ["rallylast", "rallynext"]:
            ratio[i] = "-"
        elif task_list['rally'][i] in ["missing_info", "normal"]:
            start_time = task_list['starting'][i] - pd.Timedelta(seconds=60)
            end_time = task_list['ending'][i] + pd.Timedelta(seconds=300)
            vcIdcount = vcId_data[(vcId_data['time'] >= start_time) & (vcId_data['time'] <= end_time)]
            vcIdsum[i] = len(vcIdcount)
            ratio[
                i] = f"{100 if vcIdsum[i] / task_list['tdownlink'][i] >= 1 else round(vcIdsum[i] / task_list['tdownlink'][i], 2) * 100:.2f}% "
        else:
            ratio[i] = "-"

    task_list['rdownlink'] = vcIdsum
    task_list['ratio'] = ratio

    task_list.loc[task_list['timegap'] == '跟踪失败', 'rdownlink'] = '未发现下行帧'
    task_list.loc[(task_list['rally'] == 'rallynext') | (task_list['rally'] == 'rallylast'), 'rdownlink'] = '接力'

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


def uplink_statics_new(orbit_service, mete_data_service, _influxdb_input, client_input, _influxdb_action, client_action,
                       tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    correctframe_data = correctframe(mete_data_service, _influxdb_input, client_input, tf1, tf2, satID)

    control_command = [0] * len(task_list)
    TMH3005 = [0] * len(task_list)
    telecontrol_diff = [0] * len(task_list)
    multi_device_id = [0] * len(task_list)

    init_val()
    set_value('total', len(task_list))

    for i in tqdm(range(len(task_list)), desc="Processing", unit="task"):
        init_val()
        set_value('progress', i + 1)
        set_value('total', len(task_list))
        satellite_code = task_list['satellite_code'][i]

        TMH3005test = correctframe_data[
            (correctframe_data['time'] >= task_list['starting'].iloc[i]) &
            (correctframe_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=300))
            ].dropna()

        controltest = control_data[
            (control_data['time'] >= task_list['starting'].iloc[i]) &
            (control_data['time'] <= task_list['ending'].iloc[i] + pd.Timedelta(seconds=120)) &
            (control_data['satellite_code'] == satellite_code)
            ]

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

        summary = [
            '多设备发令' if x == 1 else f'发令{int(control_command[i])}增加{int(TMH3005[i])}相差{int(telecontrol_diff[i])}' if
            telecontrol_diff[i] != 0 else f'发令{control_command[i]}全部接收' for i, x in enumerate(multi_device_id)]
        task_list['uplink'] = summary

    uplink_status = []

    for i, x in enumerate(multi_device_id):
        if x == 1:
            uplink_status.append({'多设备发令': 1, '相差': 0, '全部接收': 0})
        elif telecontrol_diff[i] != 0:
            uplink_status.append({'多设备发令': 0, '相差': 1, '全部接收': 0})
        else:
            uplink_status.append({'多设备发令': 0, '相差': 0, '全部接收': 1})

    task_list = pd.concat([task_list, pd.DataFrame(uplink_status)], axis=1)

    uplink_frequencies = task_list[['多设备发令', '相差', '全部接收']].sum().to_dict()

    # Combine the counts with the task_list
    result = {
        'task_list': json.loads(task_list.to_json(orient='records')),
        'uplink_frequencies': uplink_frequencies
    }
    result = json.dumps(result, ensure_ascii=False)
    # print(result)

    return result


def reset_detect(orbit_service, mete_data_service, _influxdb, client, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    TMS002_data = obc_resetnew(mete_data_service, _influxdb, client, tf1, tf2, satID)
    anomal = [' '] * len(task_list)

    for i in range(len(task_list)):
        TMS002 = TMS002_data[
            (TMS002_data['time'] >= task_list['starting'].iloc[i]) &
            (TMS002_data['time'] <= task_list['ending'].iloc[i])
            ]

        if TMS002.empty:
            anomal[i] = '无遥测'
        else:
            if TMS002['obc_reset'].iloc[0] > 0:
                anomal[i] = '境外复位'
            elif TMS002['obc_reset'].iloc[0] == 0 and not TMS002['obc_reset'].eq(0).all():
                anomal[i] = '境内复位'
            elif len(TMS002['obc_switch'].unique()) == 2:
                anomal[i] = 'OBC切机'

    task_list['reset'] = anomal

    # # Count the frequency of reset values
    # reset_frequencies = task_list['reset'].value_counts().to_dict()
    # reset_frequencies['无复位'] = reset_frequencies.pop(' ')

    reset_frequencies = task_list['reset'].value_counts().to_dict()

    if ' ' in reset_frequencies:
        reset_frequencies['无复位'] = reset_frequencies.pop(' ')
    else:
        print('reset-statics warning: all mission anomal')
        pass

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['reset'] != " "]

    result = {
        # 'task_list': json.loads(task_list.to_json(orient='records')),
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'reset_frequencies': reset_frequencies
    }
    # pprint.pprint(result)

    return json.dumps(result, ensure_ascii=False)


def satcom(orbit_service, mete_data_service, _influxdb, client, _influxdb_action, client_action, tf1, tf2, satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    payload_power = payload_pwr(mete_data_service, _influxdb, client, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)
    com_status = [' '] * len(task_list)

    if len(payload_power) < 1:
        com_status = ['无'] * len(task_list)
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
                if (
                        (payload['payload_signal1'].between(1.8, 2.7).any() and
                         payload['payload_signal2'].between(1.8, 2.5).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = '无'

            elif satID == '2' or satID == '7':
                if (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any()) and
                        ('K8425' in command['cmd_code'].values or
                         'K8409' in command['cmd_code'].values)
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal3'].between(2.42, 3.02).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = '无'

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
                    com_status[i] = '无'

            else:
                if (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any()) and
                        'K8425' in command['cmd_code'].values
                ):
                    com_status[i] = '通信+v数传'
                elif (
                        (payload['payload_signal1'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any() or
                         payload['payload_signal2'].between(3.05, 3.65).any())
                ):
                    com_status[i] = '通信'
                else:
                    com_status[i] = '无'

    task_list['com_status'] = com_status

    # Count the frequency of com_status values
    com_status_frequencies = task_list['com_status'].value_counts().to_dict()

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['com_status'] != "无"]

    result = {
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'com_status_frequencies': com_status_frequencies
    }

    return json.dumps(result, ensure_ascii=False)


def my_fun(n):
    if n == 2 or n == 170:
        return True


def file_inspection(orbit_service, mete_data_service, _influxdb, _client, _influxdb_action, client_action, tf1, tf2,
                    satID):
    task_list = get_task_list(orbit_service, tf1, tf2, satID)
    fileinspectdata = file_inspect(mete_data_service, _influxdb, _client, tf1, tf2, satID)
    control_data = commands(mete_data_service, _influxdb_action, client_action, tf1, tf2, satID)

    fileinspect: list = [None] * len(task_list)

    for i in range(len(task_list)):
        if fileinspectdata.empty:
            fileinspect[i] = "无"
        else:
            controlK8643 = control_data[(control_data['time'] >= task_list['starting'].iloc[i]) &
                                        (control_data['time'] <= task_list['ending'].iloc[i])]

            filedata = fileinspectdata[(fileinspectdata['time'] >= task_list['starting'].iloc[i]) &
                                       (fileinspectdata['time'] <= task_list['ending'].iloc[i])]

            if any(controlK8643['cmd_code'].eq("K8643")) or any(controlK8643['cmd_code'].eq("TCH0343")):
                if (filedata.iloc[:, 1:] == 170).any().any() or (filedata.iloc[:, 1:] == 2).any().any():
                    abnormal_columns = ", ".join(
                        filedata.columns[1:][filedata.iloc[:, 1:].apply(lambda x: (x == 170) | (x == 2)).any()])
                    fileinspect[i] = f"文件巡检异常 {abnormal_columns} 损坏"
                else:
                    fileinspect[i] = "文件巡检正常"
            else:
                fileinspect[i] = "无"

    task_list['fileinspect'] = fileinspect

    # Filter 'task_list' to include only rows where 'reset' does not equal " "
    task_list_filtered = task_list[task_list['fileinspect'] != "无"]

    fileinspect_frequency = pd.Series(fileinspect).value_counts().to_dict()

    # Create a JSON object with 'task_list' and 'fileinspect_frequency'
    result = {
        'task_list': json.loads(task_list_filtered.to_json(orient='records')),
        'fileinspect_frequency': fileinspect_frequency
    }
    # print(result)

    return json.dumps(result, ensure_ascii=False)


# def orbit_precision_analysis(orbit_propagation_url, mete_data_service, _influxdb, client, tf1, tf2, satID,
#                              CD, M, a, dw, e, i, keplerID, label, periods, radiationFlow, satelliteArea,
#                              satelliteWeight, step, thrust, thrusterWorking, value, xw):
#     gnss_data = get_gnss_data(mete_data_service, _influxdb, client, tf1, tf2, satID)
#     propagation_data =


# if __name__ == '__main__':
#     downlink_statics()
