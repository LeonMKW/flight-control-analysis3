# -*- coding: UTF-8 -*-

def analyze_lock_status(df, satID):
    df = df.reset_index(drop=True)

    if satID == '1':
        # Check if 'XAlock' or 'XBlock' equals 1
        df['lock_status'] = ((df['XBlock'] == 1) | (df['XAlock'] == 1)).astype(int)
    else:
        # Check if 'XAlock' or 'XBlock' equals 2
        df['lock_status'] = ((df['XBlock'] == 2) | (df['XAlock'] == 2)).astype(int)

    # Calculate 'lock_interval'
    first_lock_rows = df[df['lock_status'] == 1]
    first_non_lock_rows = df[df['lock_status'] == 0]

    first_lock_time = round(first_lock_rows['timestamp'].iloc[0] / 1000) if not first_lock_rows.empty else None
    first_non_lock_time = round(
        first_non_lock_rows['timestamp'].iloc[0] / 1000) if not first_non_lock_rows.empty else None
    # print(first_lock_rows.to_string())
    # print(first_non_lock_rows.to_string())
    # print('flt:', first_lock_time)
    # print('fnlt:', first_non_lock_time)

    if first_lock_time is not None and first_non_lock_time is not None and first_lock_time > first_non_lock_time:

        lock_interval = first_lock_time - first_non_lock_time if first_lock_time is not None and first_non_lock_time is not None else 0

    else:

        lock_interval = 0

    # Analyze 'lock_status' column for 'lock_stat' starting after first_lock_rows
    unlock_stat = 0
    auto_lock = 0

    if first_lock_time is not None:
        start_index = df.index[df['timestamp'] == first_lock_rows.iloc[0]['timestamp']].tolist()[0]
        consecutive_zeros = sum(1 for status in df['lock_status'].iloc[start_index + 1:] if status == 0)
        unlock_stat = consecutive_zeros
        auto_lock = df['lock_status'].iloc[start_index + 1:].sum()
    elif first_lock_time is None and first_non_lock_time is not None:
        unlock_stat = len(df)

    return unlock_stat, lock_interval, auto_lock


def analyze_telemetry_intervals(df):
    df = df.sort_values(by='timestamp')

    # Group by 'timestamp' and calculate difference
    df['timestamp_diff'] = df['timestamp'].diff()

    # Fill NaN values in the difference column with 0
    df['timestamp_diff'] = df['timestamp_diff'].fillna(0)

    # Reset group counter when 'timestamp' difference exceeds 3 or when the previous timestamp_diff was greater than 3
    df['group'] = ((df['timestamp_diff'] > 3) | (df['timestamp_diff'].shift(1) > 3)).cumsum()

    # Group by the calculated 'group'
    grouped = df.groupby('group')

    # Count total number of groups
    total_group_number = grouped.ngroups

    # Find the longest group
    longest_group_length = grouped.size().max()
    longest_group_number = grouped.size().idxmax()

    # Count the number of groups where timestamp_diff is greater than 0 (interrupt_group)
    interrupt_group = df[df['timestamp_diff'] > 3]['group'].nunique()

    # Find the first and last timestamp of the longest group
    first_timestamp = df[df['group'] == longest_group_number]['timestamp'].iloc[0]
    last_timestamp = df[df['group'] == longest_group_number]['timestamp'].iloc[-1]

    return {
        "total_group_number": total_group_number,
        'interrupt_group': interrupt_group,
        "longest_down_length": longest_group_length,
        "longest_group_number": longest_group_number,
        "longestdown_start": first_timestamp,
        "longestdown_end": last_timestamp
    }


def analyze_lock_intervals(df, satID):
    if satID == '1':
        df['lockstatus'] = ((df['XAlock'] == 1) | (df['XBlock'] == 1)).astype(int)
    else:
        df['lockstatus'] = ((df['XAlock'] == 2) | (df['XBlock'] == 2)).astype(int)

    # Sort the DataFrame by timestamp
    df = df.sort_values(by='timestamp')

    # Group by 'timestamp' and calculate difference
    df['timestamp_diff'] = df['timestamp'].diff()

    # Fill NaN values in the difference column with 0
    df['timestamp_diff'] = df['timestamp_diff'].fillna(0)

    # Reset group counter when 'lockstatus' changes to 0 or 'timestamp' difference exceeds 3
    df['group'] = ((df['lockstatus'].shift(1) != df['lockstatus']) | (df['timestamp_diff'] > 3)).cumsum()

    # Group by the calculated 'group' and check if all lockstatuses are 1 in each group
    grouped = df.groupby('group')['lockstatus'].agg(lambda x: (x == 1).all())

    # Count number of groups where lockstatus is consecutive 1
    num_groups_locked = (grouped == True).sum()
    num_groups_unlock = (grouped == False).sum()
    total_group_number = df['group'].max()

    # Initialize variables for longest group
    longest_group_length = 0
    longest_group_number = 0
    first_timestamp = None
    last_timestamp = None

    # Find the first and last timestamp of the longest group
    if num_groups_locked > 0:
        for group, indices in df.groupby('group').groups.items():
            group_length = len(indices)
            if group_length > longest_group_length:
                longest_group_length = group_length
                longest_group_number = group
                first_timestamp = df.loc[indices[0], 'timestamp']
                last_timestamp = df.loc[indices[-1], 'timestamp']

    group_durations = {}
    for group, indices in df.groupby('group').groups.items():
        duration = df.loc[indices[-1], 'timestamp'] - df.loc[indices[0], 'timestamp']
        lock_status = df.loc[indices[0], 'lockstatus']
        group_durations[group] = {"duration": duration, "lock_status": lock_status}

    return {
        "total_group_number": total_group_number,
        "num_groups_locked": num_groups_locked,
        "num_groups_unlock": num_groups_unlock,
        "longestlock_start": first_timestamp,
        "longestlock_end": last_timestamp,
        "longest_group_length": longest_group_length,
        "longest_lock_group": longest_group_number,
        "group_info": group_durations
    }
