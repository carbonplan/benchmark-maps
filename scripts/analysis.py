import argparse
import base64
import json

import cv2 as cv
import hvplot.pandas
import numpy as np
import pandas as pd
import s3fs
import upath
from parsing import extract_event_type, extract_frame_data, extract_request_data
from plotting import plot_frames, plot_requests, plot_zoom_levels

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


def process_zoom_levels(*, trace_events, screenshot_data, zoom_level):
    markers = extract_event_type(trace_events=trace_events, event_name='benchmark-', exact=False)
    action_data = pd.DataFrame(
        {
            'start_time': markers[markers['name'] == 'benchmark-initial-load:start'].iloc[0][
                'startTime'
            ],
            'end_time': screenshot_data.iloc[screenshot_data['rmse_snapshot_0'].argmin()][
                'startTime'
            ],
        },
        index=['0'],
    )
    for ind in range(1, zoom_level + 1):
        action_data.loc[ind, 'start_time'] = markers[
            markers['name'] == f'benchmark-zoom_in-level-{ind-1}:start'
        ].iloc[0]['startTime']
        action_data.loc[ind, 'end_time'] = screenshot_data.iloc[
            screenshot_data[f'rmse_snapshot_{ind}'].argmin()
        ]['startTime']
    return action_data


def process_run(*, metadata_path: upath.UPath, run: int):
    """
    Process the results from a benchmarking run.

    Parameters
    ----------

    metadata_path: upath
        Path to metadata file for a specific run.

    run: int
        Integer index of run to process.

    Returns
    -------
    data : Dict containing request_data, frames_data, and action_data for the run.
    """
    metadata = json.loads(metadata_path.read_text())[run]
    approach, zarr_version, dataset = metadata['url'].split('/')[-3:]
    # Load trace events
    trace_events = json.loads(upath.UPath(metadata['trace_path']).read_text())['traceEvents']
    # Extract request data
    url_filter = 'carbonplan-benchmarks.s3.us-west-2.amazonaws.com/data/'
    filtered_request_data = extract_request_data(trace_events=trace_events, url_filter=url_filter)
    # Extract frame data
    filtered_frames_data = extract_frame_data(trace_events=trace_events)
    # Extract screenshot data
    s3 = s3fs.S3FileSystem(anon=True)
    with s3.open('s3://carbonplan-benchmarks/benchmark-data/baselines.json') as f:
        snapshots = json.loads(f.read())[approach][zarr_version][dataset]
    screenshot_data = calculate_snapshot_rmse(trace_events=trace_events, snapshots=snapshots)
    # Get action durations
    action_data = process_zoom_levels(
        trace_events=trace_events,
        screenshot_data=screenshot_data,
        zoom_level=metadata['zoom_level'],
    )
    data = {
        'request_data': filtered_request_data,
        'frames_data': filtered_frames_data,
        'action_data': action_data,
    }
    return data


# Parse command line arguments and run main function
if __name__ == '__main__':
    # Parse input args
    parser = argparse.ArgumentParser()
    parser.add_argument('--timestamp', type=str)
    parser.add_argument('--run', type=int, default=0)
    parser.add_argument('--s3-bucket', type=str, default=None)
    args = parser.parse_args()
    if args.s3_bucket is not None:
        root_dir = upath.UPath(args.s3_bucket)
    else:
        root_dir = upath.UPath('.')
    metadata_fp = root_dir / f'data/data-{args.timestamp}.json'
    data = process_run(metadata_path=metadata_fp, run=args.run)
    # # Create plots
    requests_plt = plot_requests(data['request_data'])
    frames_plt = plot_frames(data['frames_data'], yl=2.5)
    zoom_plt_a = plot_zoom_levels(data['action_data'], yl=-1, yh=len(data['request_data']) + 1)
    zoom_plt_b = plot_zoom_levels(data['action_data'])
    # # Show plot using bokeh server
    hvplot.show(((zoom_plt_a * requests_plt) + (zoom_plt_b * frames_plt)).cols(1))
