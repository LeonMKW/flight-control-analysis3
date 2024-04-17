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


# cumulative reset status for 02P
# def cumulative_reset_count(tf1, tf2, satIDs):
#
#
# def reset_time():
#
