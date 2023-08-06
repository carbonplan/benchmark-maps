import base64
import json

import cv2 as cv
import fsspec
import numpy as np
import pandas as pd

from .parsing import extract_event_type, extract_frame_data, extract_request_data

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


def calculate_snapshot_rmse(*, trace_events, snapshots, metadata):
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
    dataset = f"{metadata['approach']}-{metadata['zarr_version']}-{metadata['dataset']}"
    for zoom_level in range(metadata['zoom_level'] + 1):
        snapshot = base64_to_img(snapshots.loc[dataset, str(zoom_level)])
        var = f'rmse_snapshot_{zoom_level}'
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
            'action_end_time': markers[markers['name'] == 'benchmark-initial-load:end'].iloc[0][
                'startTime'
            ],
        },
        index=[0],
    )
    for ind in range(1, zoom_level + 1):
        action_data.loc[ind, 'start_time'] = markers[
            markers['name'] == f'benchmark-zoom_in-level-{ind-1}:start'
        ].iloc[0]['startTime']
        action_data.loc[ind, 'end_time'] = screenshot_data.iloc[
            screenshot_data[f'rmse_snapshot_{ind}'].argmin()
        ]['startTime']
        action_data.loc[ind, 'action_end_time'] = markers[
            markers['name'] == f'benchmark-zoom_in-level-{ind-1}:end'
        ].iloc[0]['startTime']
    action_data['duration'] = action_data['end_time'] - action_data['start_time']
    return action_data


def load_data(*, metadata_path: str, run: int):
    """
    Load data associated with a run

    metadata_path: str
        Path to metadata file for a specific run.

    run: int
        Integer index of run to process.

    Returns
    -------
    metadata, trace_data
    """
    if 's3' in metadata_path:
        fs = fsspec.filesystem('s3', anon=True)
    else:
        fs = fsspec.filesystem('file')
    with fs.open(metadata_path) as f:
        metadata = json.loads(f.read())[run]
    metadata['metadata_path'] = metadata_path
    if not metadata['zoom_level']:
        metadata['zoom_level'] = 0
    trace_path = f'{"/".join(metadata_path.split("/")[:-1])}/{metadata["trace_path"]}'
    metadata['full_trace_path'] = trace_path
    with fs.open(trace_path) as f:
        trace_events = json.loads(f.read())['traceEvents']
    return metadata, trace_events


def load_snapshots(*, snapshot_path: str):
    """
    Load snapshots

    snapshot_path: str
        Path to JSON contains baseline snapshots.

    Returns
    -------
    snapshots: dict containing base64 representation of baseline snapshots.
    """
    if 's3' in snapshot_path:
        fs = fsspec.filesystem('s3', anon=True)
    else:
        fs = fsspec.filesystem('file')
    with fs.open(snapshot_path) as f:
        snapshots = pd.read_json(f, orient='index')
    return snapshots


def create_summary(*, metadata, data):
    """
    Create summary DataFrame for a given run
    """
    metadata
    summary = pd.concat(
        [pd.DataFrame(metadata, index=[0])] * (metadata['zoom_level'] + 1), ignore_index=True
    )
    summary['chunk_size'] = summary['dataset'].apply(lambda x: int(x.split('MB')[0]))
    frames_data = data['frames_data']
    request_data = data['request_data']
    actions = data['action_data']
    for zoom in range(metadata['zoom_level'] + 1):
        frames = frames_data[
            (frames_data['startTime'] > actions.loc[zoom, 'start_time'])
            & (frames_data['startTime'] <= actions.loc[zoom, 'end_time'])
        ]
        requests = request_data[
            (request_data['request_start'] > actions.loc[zoom, 'start_time'])
            & (request_data['request_start'] <= actions.loc[zoom, 'action_end_time'])
        ]
        if requests['request_start'].max() > actions.loc[zoom, 'action_end_time']:
            raise Warning(f'Request for zoom level {zoom} started after timeout')
        if requests['response_end'].max() > actions.loc[zoom, 'action_end_time']:
            raise Warning(f'Response duration for zoom level {zoom} exceeded timeout')
        summary.loc[zoom, 'zoom'] = zoom
        summary.loc[zoom, 'duration'] = actions.loc[zoom, 'duration']
        summary.loc[zoom, 'fps'] = len(frames) / (actions.loc[zoom, 'duration'] * 1e-3)
        if requests.empty:
            summary.loc[zoom, 'request_duration'] = 0
        else:
            summary.loc[zoom, 'request_duration'] = (
                requests['response_end'].max() - requests['request_start'].min()
            )
    summary['request_percent'] = summary['request_duration'] / summary['duration'] * 100

    return summary


def process_run(*, metadata, trace_events, snapshots):
    """
    Process the results from a benchmarking run.

    Parameters
    ----------

    metadata: dict
        Metadata for a specific run.

    trace_events: list
        The list of trace events.

    snapshots: list
        List of snapshots to compare screenshots against
    Returns
    -------
    data : Dict containing request_data, frames_data, and action_data for the run.
    """
    # Extract request data
    url_filter = 'carbonplan-benchmarks.s3.us-west-2.amazonaws.com/data/'
    filtered_request_data = extract_request_data(trace_events=trace_events, url_filter=url_filter)
    # Extract frame data
    filtered_frames_data = extract_frame_data(trace_events=trace_events)
    # Extract screenshot data
    screenshot_data = calculate_snapshot_rmse(
        trace_events=trace_events, snapshots=snapshots, metadata=metadata
    )
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
        'screenshot_data': screenshot_data,
    }
    return data
