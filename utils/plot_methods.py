# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
import pandas as pd
from utils.db import MinIO


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


def plot_od_precision(df, minioendpoint, minioaccess, miniosecret):
    # Create a figure and subplots
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))

    # Plot theoretical_distance2 and actual_distance2 by timestamp
    axs[0, 0].plot(df['timestamp'], df['theoretical_distance2'], label='Theoretical Distance2', alpha=0.5,
                   linestyle='-', marker='o', markersize=3)
    axs[0, 0].plot(df['timestamp'], df['actual_distance2'], label='Actual Distance2', alpha=0.5, linestyle='-',
                   marker='o', markersize=1)
    axs[0, 0].set_title('Distance by Timestamp')
    axs[0, 0].legend()

    # Plot x_diff, y_diff, and z_diff by timestamp
    axs[0, 1].plot(df['timestamp'], df['x_diff'], label='X Diff')
    axs[0, 1].plot(df['timestamp'], df['y_diff'], label='Y Diff')
    axs[0, 1].plot(df['timestamp'], df['z_diff'], label='Z Diff')
    axs[0, 1].set_title('Difference by Timestamp')
    axs[0, 1].legend()

    # Plot error by timestamp
    axs[1, 0].plot(df['timestamp'], df['error'], label='Error')
    axs[1, 0].set_title('Error by Timestamp')
    axs[1, 0].legend()

    # Calculate mean, max, and first values of the error
    error_mean = df['error'].mean()
    error_max = df['error'].max()
    error_first = df['error'].iloc[0]

    # Create summary table
    summary_table = pd.DataFrame({
        'Error Summary': [error_mean, error_max, error_first]
    }, index=['orbit_err', '24hr_max_err', 'ephemeris_err'])

    # Hide axes for the summary table subplot
    axs[1, 1].axis('off')
    axs[1, 1].table(cellText=summary_table.values,
                    rowLabels=summary_table.index,
                    colLabels=summary_table.columns,
                    loc='center')

    plt.tight_layout()
    minio_instance = MinIO(_endpoint=minioendpoint, _access=minioaccess, _secret=miniosecret)

    path = f"/flight-control-analysis/data/{df['ephemeris_id'][0]}.png"

    plt.savefig(path, format='png', bbox_inches='tight')
    dest_file = f"{df['ephemeris_id'][0]}.png"

    minio_instance.upload_file(bucket_name="odprecision", source_file=path,
                               destination_file=dest_file)
