import json
import pandas as pd
import pytz
import logging
from utils.flightcontrol_utils import get_task_list
from utils.LZ04satellitestatus_utils import get_LZ04_tmz009,get_LZ04_tmkp202, get_LZ04_hdi_switches


def LZ04_hdi_task(post_token_url,
                  post_token_user_name,
                  post_token_password,
                  orbit_service,
                  metedataservice_url,
                  _influxdb,
                  client,
                  tf1,
                  tf2,
                  satID):
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    task_list = get_task_list(
        post_token_url,
        post_token_user_name,
        post_token_password,
        orbit_service,
        tf1,
        tf2,
        satID
    )

    if not isinstance(task_list, pd.DataFrame) or task_list.empty:
        return json.dumps({"HDI": {}, "Error": "No task_list"}, ensure_ascii=False)

    # TMZ009
    tmz009_df = get_LZ04_tmz009(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if tmz009_df is None or tmz009_df.empty:
        tmz009_df = pd.DataFrame(columns=['time', 'TMZ009'])
    else:
        tmz009_df['time'] = pd.to_datetime(tmz009_df['time'], utc=True, errors='coerce')
        tmz009_df = tmz009_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    # switches
    sw_df = get_LZ04_hdi_switches(
        post_token_url=post_token_url,
        post_token_user_name=post_token_user_name,
        post_token_password=post_token_password,
        metedataservice_url=metedataservice_url,
        _influxdb=_influxdb,
        client=client,
        tf1=tf1,
        tf2=tf2,
        satID=satID
    )
    if sw_df is None or sw_df.empty:
        sw_df = pd.DataFrame(columns=['time', 'TMH4538', 'TMKS700'])
    else:
        sw_df['time'] = pd.to_datetime(sw_df['time'], utc=True, errors='coerce')
        sw_df = sw_df.dropna(subset=['time']).sort_values('time').reset_index(drop=True)

    result = {"HDI": {}}

    for idx in range(len(task_list)):
        mission_id = task_list['mission_id'].iat[idx]
        start_dt = pd.to_datetime(task_list['starting'].iat[idx], utc=True)
        end_dt   = pd.to_datetime(task_list['ending'].iat[idx], utc=True)

        # 1) 先判开关：取任务窗内第一条
        sw_win = sw_df[(sw_df['time'] >= start_dt) & (sw_df['time'] <= end_dt)]

        # 分别找“第一条非NaN”的开关值
        app_series = sw_win['TMH4538'].dropna() if ('TMH4538' in sw_win.columns) else pd.Series(dtype=float)
        aocs_series = sw_win['TMKS700'].dropna() if ('TMKS700' in sw_win.columns) else pd.Series(dtype=float)

        app_on = int(app_series.iloc[0]) if not app_series.empty else None
        aocs_on = int(aocs_series.iloc[0]) if not aocs_series.empty else None

        # 只有两者都明确为 1 才算 ON
        switches_on = (app_on == 1 and aocs_on == 1)

        # 如果你希望“没找到其中一个开关值”也直接算 off：
        # switches_on 已经会是 False，因为 None != 1

        # 2) 如果开关没开：直接 off
        if not switches_on:
            hdi_status = "off"
            hdi_no = 0
            last_tmz009 = "skip"  # 表示因为开关未开而跳过 TMZ009 判断
        else:
            # 3) 开关都开：执行原 TMZ009 逻辑
            df_tmz = tmz009_df[(tmz009_df['time'] >= start_dt) & (tmz009_df['time'] <= end_dt)]

            if df_tmz.empty:
                hdi_status = "nodata"
                hdi_no = "nodata"
                last_tmz009 = "nodata"
            else:
                vals = df_tmz['TMZ009'].tolist()
                last_tmz009 = int(vals[-1])

                if all(v == 0 for v in vals):
                    hdi_status = "off"
                    hdi_no = 0
                else:
                    hdi_status = "on"
                    hdi_no = last_tmz009  # 混合/固定非零都取最后一个值

        task_payload = {
            "mission_id": mission_id,
            "satellite_code": task_list['satellite_code'].iat[idx] if 'satellite_code' in task_list.columns else "",
            "station_name": task_list['station_name'].iat[idx] if 'station_name' in task_list.columns else "",
            "device": task_list['device'].iat[idx] if 'device' in task_list.columns else "",
            "company_name": task_list['company_name'].iat[idx] if 'company_name' in task_list.columns else "",
            "remark": task_list['remark'].iat[idx] if 'remark' in task_list.columns else "",
            "starting": int(start_dt.timestamp() * 1000),
            "ending": int(end_dt.timestamp() * 1000),

            # 开关状态（方便日报解释“为什么没 TMZ009”）
            "switches": {
                "TMH4538_app": app_on if app_on is not None else "nodata",
                "TMKS700_aocs": aocs_on if aocs_on is not None else "nodata",
                "both_on": int(switches_on)
            },

            "HDI": {
                "status": hdi_status,           # on/off/nodata
                "record_no": hdi_no,            # 0 / int / 'nodata'
                "last_tmz009": last_tmz009      # debug
            }
        }

        result["HDI"][f"Task_{idx+1}"] = task_payload

    return json.dumps(result, ensure_ascii=False, indent=4)


