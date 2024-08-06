# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt
import pandas as pd
from utils.db import OSS2
import statsmodels.api as sm
from statsmodels.tsa.seasonal import seasonal_decompose
import numpy as np


# def odprecision_plot_plotly(df):
#     # Create subplots
#     fig = make_subplots(rows=2, cols=2,
#                         subplot_titles=("Theoretical vs Actual Distance",
#                                         "Difference in Coordinates",
#                                         "Error over Time"))
#
#     # Add traces to subplot 1
#     fig.add_trace(
#         go.Scatter(x=df['timestamp'], y=df['theoretical_distance2'], mode='lines', name='Theoretical Distance'),
#         row=1, col=1)
#     fig.add_trace(go.Scatter(x=df['timestamp'], y=df['actual_distance2'], mode='lines', name='Actual Distance'),
#                   row=1, col=1)
#
#     # Add traces to subplot 2
#     fig.add_trace(go.Scatter(x=df['timestamp'], y=df['x_diff'], mode='lines', name='X Difference'),
#                   row=1, col=2)
#     fig.add_trace(go.Scatter(x=df['timestamp'], y=df['y_diff'], mode='lines', name='Y Difference'),
#                   row=1, col=2)
#     fig.add_trace(go.Scatter(x=df['timestamp'], y=df['z_diff'], mode='lines', name='Z Difference'),
#                   row=1, col=2)
#
#     # Add trace to subplot 3
#     fig.add_trace(go.Scatter(x=df['timestamp'], y=df['error'], mode='lines', name='Error'),
#                   row=2, col=1)
#
#     # Update layout
#     fig.update_layout(title='Orbit Precision Analysis')
#
#     # Update x-axis title for subplot 3
#     fig.update_xaxes(title_text='Timestamp', row=2, col=1)
#
#     fig.update_traces(
#         line=dict(width=1),  # Thin lines
#         marker=dict(size=3)  # Slightly thicker dots
#     )
#
#     return fig

def plot_od_precision(df, ossendpoint, ossaccess, osssecret, period=None):
    # Convert timestamp from seconds to datetime
    df['time'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Shanghai')
    # Determine the period if not provided
    if period is None:
        # Calculate ACF
        acf_result = sm.tsa.acf(df['error'], nlags=len(df) // 2)
        # Find the first significant peak in ACF (excluding the first element which is always 1)
        period = next(i for i, x in enumerate(acf_result[1:]) if x < acf_result[0] / 2) + 1

    # Perform decomposition on error
    decomposition = seasonal_decompose(df['error'], model='multiplicative', period=period, extrapolate_trend='freq')
    trend = decomposition.trend
    seasonal = decomposition.seasonal
    residual = decomposition.resid

    # Create a figure and subplots
    fig, axs = plt.subplots(5, 1, figsize=(12, 20))

    # Plot error by timestamp
    axs[0].plot(df['time'], df['error'], label='Error')
    axs[0].set_title('Error by Time')
    # axs[0].xaxis.set_major_locator(mdates.HourLocator(interval=3))
    # axs[0].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    axs[0].legend()

    # Plot difference by timestamp
    axs[1].plot(df['time'], df['x_diff'], label='X Diff')
    axs[1].plot(df['time'], df['y_diff'], label='Y Diff')
    axs[1].plot(df['time'], df['z_diff'], label='Z Diff')
    axs[1].set_title('Difference by Time')
    axs[1].legend()

    # Plot trend
    axs[2].plot(df['time'], trend, label='Trend')
    axs[2].set_title('Trend')
    axs[2].legend()

    # Plot seasonality
    axs[3].plot(df['time'], seasonal, label='Seasonality')
    axs[3].set_title('Seasonality')
    axs[3].legend()

    # Plot residual
    axs[4].plot(df['timestamp'], residual, label='Residual')
    axs[4].set_title('Residual')
    axs[4].legend()

    # Rotate x-axis labels for all subplots
    for ax in axs:
        plt.setp(ax.get_xticklabels(), rotation=60, ha='right')

    plt.tight_layout()
    oss_instance = OSS2(_endpoint=ossendpoint, _access=ossaccess, _secret=osssecret)

    localpath = f"data/{df['ephemeris_id'][0]}.png"
    osspath = f"flight-control-analysis/data/{df['ephemeris_id'][0]}.png"

    plt.savefig(localpath, format='png', bbox_inches='tight')
    # dest_file = f"{df['ephemeris_id'][0]}.png"
    # print(path)
    # print(dest_file)
    oss_instance.upload_file(key=osspath, filename=localpath)

    # Calculate the number of slices and the slice length
    num_slices = 22
    slice_length = len(trend) // num_slices

    # Initialize a list to store the average trend values for each specified slice
    average_trend_values = []

    # Calculate the average trend value for each specified slice
    for interval in [3, 6, 12, 18]:
        # Determine the slice index for the specified interval
        slice_index = int((interval / 22) * num_slices)

        # Calculate the start and end index of the slice
        start_index = slice_index * slice_length
        end_index = min((slice_index + 1) * slice_length, len(trend))

        slice_trend_values = trend[start_index:end_index]

        average_trend = np.mean(slice_trend_values)

        average_trend_values.append(average_trend)

    return average_trend_values
