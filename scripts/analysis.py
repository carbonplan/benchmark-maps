import argparse
import base64
import json

import cv2 as cv
import holoviews as hv
import hvplot.pandas
import numpy as np
import pandas as pd
import upath
from holoviews import opts
from parsing import extract_event_type, extract_frame_data, extract_request_data

pd.options.plotting.backend = 'holoviews'


def base64_to_img(base64jpeg):
    """
    Load jpeg image encoded as base64

    Parameters
    ----------

    df: pd.DataFrame
        DataFrame containing event information

    Returns
    -------
    image : np.ndarray
        Numpy array containing image
    """
    arr = np.frombuffer(base64.b64decode(base64jpeg), np.uint8)
    return cv.imdecode(arr, cv.IMREAD_COLOR)


def calculate_snapshot_rmse(*, trace_events, snapshots):
    """
    Extract screenshots from a list of Chromium trace events.

    Parameters
    ----------

    trace_events: list
        The list of trace events.

    snapshots: list
        List of snapshots to compare screenshots against

    Returns
    -------
    screenshots : DataFrame containing screenshots
    """

    def calculate_rmse(predictions, targets):
        return np.sqrt(np.mean((predictions - targets) ** 2))

    screenshots = extract_event_type(trace_events=trace_events, event_name='Screenshot')
    for action_ind, snapshot_base64 in enumerate(snapshots):
        snapshot = base64_to_img(snapshot_base64)
        var = f'rmse_snapshot_{action_ind}'
        for ind, row in screenshots.iterrows():
            frame = base64_to_img(row['args.snapshot'])
            screenshots.loc[ind, var] = calculate_rmse(frame, snapshot)
    return screenshots


def plot_requests(df: pd.DataFrame):
    """
    Plot rectangles showing each request duration
    """
    df['rectangle'] = df.apply(
        lambda x: (
            x['request_start'],
            x.name,
            x['response_end'],
            x.name + 1,
        ),
        axis=1,
    )
    boxes = hv.Rectangles(df['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgrey', xlabel='Time (ms)', yaxis=None, title='Network')
    return boxes


def plot_frames(df: pd.DataFrame, *, yl: int = 1):
    """
    Plot rectangles showing each fra,e duration
    """
    df['rectangle'] = df.apply(lambda x: (x['startTime'], yl, x['endTime'], yl + 1), axis=1)
    plt_opts = {'width': 1000, 'xlabel': 'Time (ms)', 'yaxis': None, 'title': 'Frames'}
    subsets = {'idle': 'lightgrey', 'isPartial': 'yellow', 'dropped': 'red', 'drawn': 'lightgreen'}
    plots = {}
    for key, value in subsets.items():
        subset = df[df[key]]
        plots[key] = hv.Rectangles(subset['rectangle'].to_list())
        plots[key].opts(**plt_opts, color=value)
    return plots['idle'] * plots['isPartial'] * plots['dropped'] * plots['drawn']


def plot_screenshot_rmse(df: pd.DataFrame, markers: pd.DataFrame, zoom_level: int):
    """
    Plot difference between the screenshots and baseline frames
    """
    plt_opts = {'width': 1000, 'xlabel': 'Time (ms)', 'ylabel': 'RMSE', 'title': 'Sceenshots'}
    color_opts = [
        {'color': 'lightblue'},
        {'color': 'orange'},
        {'color': 'lightgreen'},
        {'color': 'red'},
        {'color': 'purple'},
    ]
    plt = df.plot.line(
        x='startTime', y='rmse_snapshot_0', label='zoom 0', color=color_opts[0]['color']
    )
    start_line = hv.VLine(
        markers[markers['name'] == 'benchmark-initial-load:start'].loc[0, 'startTime']
    )
    end_line = hv.VLine(df.iloc[df['rmse_snapshot_0'].argmin()]['startTime'])
    plt = (plt * start_line * end_line).opts(opts.VLine(**color_opts[0]))
    for ind in range(1, zoom_level + 1):
        rmse = df.plot.line(
            x='startTime',
            y=f'rmse_snapshot_{ind}',
            label=f'zoom {ind}',
            color=color_opts[ind]['color'],
        )
        markers[markers['name'] == f'benchmark-zoom_in-level-{ind-1}:start']
        df.iloc[df[f'rmse_snapshot_{ind-1}'].argmin()]['startTime']
        start_line = hv.VLine(
            markers[markers['name'] == f'benchmark-zoom_in-level-{ind-1}:start'].iloc[0][
                'startTime'
            ]
        )
        end_line = hv.VLine(df.iloc[df[f'rmse_snapshot_{ind}'].argmin()]['startTime'])
        plt = plt * rmse * (start_line * end_line).opts(opts.VLine(**color_opts[ind]))
    return plt.opts(**plt_opts)


# Parse command line arguments and run main function
if __name__ == '__main__':
    # Parse input args
    parser = argparse.ArgumentParser()
    parser.add_argument('--timestamp', type=str)
    parser.add_argument('--run', type=int, default=1)
    parser.add_argument('--s3-bucket', type=str, default=None)
    args = parser.parse_args()
    if args.s3_bucket is not None:
        root_dir = upath.UPath(args.s3_bucket)
    else:
        root_dir = upath.UPath('.')
    metadata_fp = root_dir / f'data/data-{args.timestamp}.json'
    metadata = json.loads(metadata_fp.read_text())[args.run - 1]
    approach, zarr_version, dataset = metadata['url'].split('/')[-3:]
    # Load trace events
    trace_events = json.loads(upath.UPath(metadata['trace_path']).read_text())['traceEvents']
    # Get markers
    markers = extract_event_type(trace_events=trace_events, event_name='benchmark-', exact=False)
    # Extract request data
    url_filter = 'carbonplan-benchmarks.s3.us-west-2.amazonaws.com/data/'
    filtered_request_data = extract_request_data(trace_events=trace_events, url_filter=url_filter)
    # Extract frame data
    filtered_frames_data = extract_frame_data(trace_events=trace_events)
    # Extract screenshot data
    snapshots = json.loads(upath.UPath('data/baselines.json').read_text())[approach][zarr_version][
        dataset
    ]
    screenshot_data = calculate_snapshot_rmse(trace_events=trace_events, snapshots=snapshots)
    # # Create plots
    requests_plt = plot_requests(filtered_request_data)
    frames_plt = plot_frames(filtered_frames_data, yl=2.5)
    rmse_plt = plot_screenshot_rmse(screenshot_data, markers, zoom_level=metadata['zoom_level'])
    # # Show plot using bokeh server
    hvplot.show((requests_plt + frames_plt + rmse_plt).cols(1))
