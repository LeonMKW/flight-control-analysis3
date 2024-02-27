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
