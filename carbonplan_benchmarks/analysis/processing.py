import base64
import json

import cv2 as cv
import fsspec
import numpy as np
import pandas as pd
import zarrita

from .parsing import extract_event_type, extract_frame_data, extract_request_data

pd.options.plotting.backend = 'holoviews'
pd.options.mode.chained_assignment = None


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


def calculate_snapshot_rmse(*, trace_events, snapshots, metadata, xstart: int = 133):
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
    for zoom_level in range(metadata['zoom_level'] + 1):
        snapshot = base64_to_img(snapshots.loc[zoom_level, 0])
        var = f'rmse_snapshot_{zoom_level}'
        for ind, row in screenshots.iterrows():
            frame = base64_to_img(row['args.snapshot'])
            screenshots.loc[ind, var] = calculate_rmse(frame[:, xstart:], snapshot[:, xstart:])
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
    event_types = [
        'ResourceSendRequest',
        'ResourceFinish',
        'BeginFrame',
        'DrawFrame',
        'DroppedFrame',
        'Commit',
        'Screenshot',
        'benchmark-initial-load:start',
        'benchmark-initial-load:end',
        'benchmark-zoom_in-level-0:start'
        'benchmark-zoom_in-level-1:start'
        'benchmark-zoom_in-level-2:start'
        'benchmark-zoom_in-level-0:end'
        'benchmark-zoom_in-level-1:end'
        'benchmark-zoom_in-level-2:end',
    ]
    trace_events = [
        event
        for event in trace_events
        if event['name'] in event_types or 'benchmark-zoom' in event['name']
    ]
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


def get_chunk_size(URI, zarr_version, sharded, var='tasmax'):
    """
    Get chunk size based on zoom level 0.
    """
    source_store = zarrita.RemoteStore(URI)
    if zarr_version == 2:
        source_array = zarrita.ArrayV2.open(source_store / '0' / var)
        chunks = source_array.metadata.chunks
        itemsize = source_array.metadata.dtype.itemsize
    else:
        source_array = zarrita.Array.open(source_store / '0' / var)
        if sharded:
            chunks = source_array.metadata.codecs[0].configuration.chunk_shape
        else:
            chunks = source_array.metadata.chunk_grid.configuration.chunk_shape
        itemsize = source_array.metadata.dtype.itemsize
    chunk_size = np.prod(chunks) * itemsize * 1e-6
    return chunk_size


def add_chunk_size(
    summary: pd.DataFrame,
    *,
    root_path: str = 's3://carbonplan-benchmarks/data/NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/tasmax/tasmax_day_ACCESS-CM2_historical_r1i1p1f1_gn',
):
    """
    Add a column to the summary DataFrame containing the chunk size.
    """
    datasets = summary[
        ['zarr_version', 'dataset', 'shard_size', 'target_chunk_size']
    ].drop_duplicates()
    datasets['URI'] = root_path + '/' + datasets['dataset']
    datasets['actual_chunk_size'] = datasets.apply(
        lambda x: get_chunk_size(x['URI'], x['zarr_version'], x['shard_size']), axis=1
    )
    datasets = datasets[['dataset', 'actual_chunk_size']]
    return summary.set_index('dataset').join(datasets.set_index('dataset'))


def create_summary(*, metadata: pd.DataFrame, data: dict, url_filter: str = None):
    """
    Create summary DataFrame for a given run
    """
    summary = pd.concat(
        [pd.DataFrame(metadata, index=[0])] * (metadata['zoom_level'] + 1), ignore_index=True
    )
    summary['metadata_path'] = metadata['metadata_path']
    summary['trace_path'] = metadata['trace_path']
    summary['zarr_version'] = summary['dataset'].apply(lambda x: int(x.split('-')[1][1]))
    summary['projection'] = summary['dataset'].apply(lambda x: int(x.split('-')[2]))
    summary['pixels_per_tile'] = summary['dataset'].apply(lambda x: int(x.split('-')[4]))
    summary['target_chunk_size'] = summary['dataset'].apply(lambda x: int(x.split('-')[5]))
    summary['shard_orientation'] = summary['dataset'].apply(lambda x: x.split('-')[6])
    summary['shard_size'] = summary['dataset'].apply(lambda x: int(x.split('-')[7]))
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
        summary.loc[zoom, 'total_requests'] = len(requests)
        if url_filter:
            requests = requests[requests['url'].str.contains(url_filter)]
        summary.loc[zoom, 'filtered_requests'] = len(requests)
        summary.loc[zoom, 'filtered_requests_average_encoded_data_length'] = requests[
            'encoded_data_length'
        ].mean()
        summary.loc[zoom, 'filtered_requests_maximum_encoded_data_length'] = requests[
            'encoded_data_length'
        ].max()
        summary.loc[zoom, 'zoom'] = zoom
        summary.loc[zoom, 'duration'] = actions.loc[zoom, 'duration']
        summary.loc[zoom, 'timeout'] = False
        if requests['request_start'].max() > actions.loc[zoom, 'action_end_time']:
            actions.loc[zoom, 'action_end_time'] = np.nan
            summary.loc[zoom, 'duration'] = metadata['timeout']
            summary.loc[zoom, 'timeout'] = True
        if requests['response_end'].max() > actions.loc[zoom, 'action_end_time']:
            actions.loc[zoom, 'action_end_time'] = np.nan
            summary.loc[zoom, 'duration'] = metadata['timeout']
            summary.loc[zoom, 'timeout'] = True
        if summary.loc[zoom, 'duration'] > metadata['timeout']:
            summary.loc[zoom, 'duration'] = metadata['timeout']
            summary.loc[zoom, 'timeout'] = True
        summary.loc[zoom, 'fps'] = len(frames) / (actions.loc[zoom, 'duration'] * 1e-3)
        if requests.empty:
            summary.loc[zoom, 'request_duration'] = 0
        else:
            summary.loc[zoom, 'request_duration'] = (
                requests['response_end'].max() - requests['request_start'].min()
            )
    summary['request_percent'] = summary['request_duration'] / summary['duration'] * 100
    summary['non_request_duration'] = summary['duration'] - summary['request_duration']
    summary = add_chunk_size(summary)

    return summary


def process_run(*, metadata, trace_events, snapshots, url_filter=None):
    """
    Process the results from a benchmarking run.

    Parameters
    ----------

    metadata: dict
        Metadata for a specific run.

    trace_events: list
        The list of trace events.

    snapshots: list
        List of snapshots to compare screenshots against.

    url_filter: str
        Filter requests based on this url.
    Returns
    -------
    data : Dict containing request_data, frames_data, and action_data for the run.
    """
    # Extract request data
    filtered_request_data = extract_request_data(trace_events=trace_events)
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
