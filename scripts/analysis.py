import argparse
import base64
import json

import cv2 as cv
import holoviews as hv
import hvplot.pandas
import numpy as np
import pandas as pd
import upath

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


def process_rendering_events(df):
    """
    Process rendering events by adding startTime in ms, normalizing dtypes, and sorting by time.

    Parameters
    ----------

    df: pd.DataFrame
        DataFrame containing event information

    Returns
    -------
    df : Processed DataFrame containing event information
    """
    df['startTime'] = df['ts'] * 1e-3
    # df['startTimeOffset'] = df['startTime'] - traceStartTime
    if 'args.frameSeqId' in df.columns:
        df['args.frameSeqId'] = df['args.frameSeqId'].astype(int)
    return df.sort_values(by='startTime')


def combine_first_two_frames(df):
    """
    Combine the first two frames into one frame

    Parameters
    ----------

    df: pd.DataFrame
        DataFrame containing event information

    Returns
    -------
    df : Processed DataFrame with first two frames combined
    """
    df.loc[1, 'startTime_Begin'] = df.loc[0, 'startTime_Draw']
    df.loc[1, 'startTime_Begin_Diff'] = df.loc[2, 'startTime_Begin'] - df.loc[1, 'startTime_Begin']
    return df.drop(df.head(1).index)


def get_start_time(*, trace_events):
    """
    Extract the time of the first event that has a startTime


    Parameters
    ----------

    trace_events: list
         The list of trace events.

    Returns
    -------
    start_time: int
        First non-zero start time from events
    """
    return next((x['ts'] for x in trace_events if x['ts']), None) * 1e-3


def extract_screenshots(*, trace_events):
    """
    Extract screenshots from a list of Chromium trace events.

    Parameters
    ----------

    trace_events: list
         The list of trace events.

    Returns
    -------
    screenshots : DataFrame containing screenshots
    """

    def calculate_rmse(predictions, targets):
        return np.sqrt(np.mean((predictions - targets) ** 2))

    screenshots = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'Screenshot']
    )
    screenshots = process_rendering_events(screenshots)
    baseline = pd.read_json('data/baselines.json', orient='index')
    zoom0_baseline = base64_to_img(baseline.loc[0, 'baseline'])
    zoom1_baseline = base64_to_img(baseline.loc[1, 'baseline'])
    zoom2_baseline = base64_to_img(baseline.loc[2, 'baseline'])
    for ind, row in screenshots.iterrows():
        frame = base64_to_img(row['args.snapshot'])
        screenshots.loc[ind, 'rmse_zoom0'] = calculate_rmse(frame, zoom0_baseline)
        screenshots.loc[ind, 'rmse_zoom1'] = calculate_rmse(frame, zoom1_baseline)
        screenshots.loc[ind, 'rmse_zoom2'] = calculate_rmse(frame, zoom2_baseline)
    return screenshots


def extract_request_data(*, trace_events, url_filter: str = None):
    """
    Extract request data from a list of Chromium trace events, optionally filtering by URL.

    Parameters
    ----------

    trace_events: list
         The list of trace events.
    url_filter : str, optional
        If specified, only include requests where the URL contains this string.

    Returns
    -------
    request_data : DataFrame containing information about requests
    """
    send_requests = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'ResourceSendRequest']
    )
    finish_requests = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'ResourceFinish']
    )
    data = send_requests.merge(
        finish_requests, on='args.data.requestId', how='left', suffixes=('_send', '_finish')
    )[
        [
            'ts_send',
            'ts_finish',
            'args.data.encodedDataLength',
            'args.data.priority',
            'args.data.url',
            'args.data.requestMethod',
        ]
    ].rename(
        {
            'ts_send': 'request_start',
            'ts_finish': 'response_end',
            'args.data.encodedDataLength': 'encoded_data_length',
            'args.data.url': 'url',
            'args.data.requestMethod': 'method',
        },
        axis=1,
    )
    data['request_start'] = data['request_start'] * 1e-3
    data['response_end'] = data['response_end'] * 1e-3
    data['total_response_time_ms'] = data['response_end'] - data['request_start']
    if url_filter:
        data = data[data['url'].str.contains(url_filter)]
    data = data.reset_index(drop=True)
    return data


def extract_frame_data(*, trace_events):
    """
    Extract frame data from a list of Chromium trace events.

    Parameters
    ----------

    trace_events: list
         The list of trace events.

    Returns
    -------
    frame_data : DataFrame containing information about frames
    """
    # Fetch events of type 'BeginFrame', 'DrawFrame', and 'DroppedFrame'
    begin_frame_events = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'BeginFrame']
    )
    draw_frame_events = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'DrawFrame']
    )
    dropped_frame_events = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'DroppedFrame']
    )
    commit_events = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'Commit']
    ).dropna(subset=['args.frameSeqId'])
    # Drop duplicates
    begin_frame_events.drop_duplicates(subset=['args.frameSeqId'], inplace=True)

    for df in [begin_frame_events, draw_frame_events, dropped_frame_events, commit_events]:
        process_rendering_events(df)

    frame_events = (
        pd.concat([draw_frame_events, dropped_frame_events])
        .sort_values(by='startTime')
        .merge(begin_frame_events, on='args.frameSeqId', suffixes=('_Draw', '_Begin'))
        .merge(commit_events, on='args.frameSeqId', suffixes=('', '_Commit'), how='left')[
            [
                'name_Draw',
                'name_Begin',
                'args.frameSeqId',
                'pid_Draw',
                'pid_Begin',
                'startTime_Draw',
                'startTime_Begin',
                'startTime',
            ]
        ]
        .rename({'startTime': 'startTime_Commit'}, axis=1)
    )
    frame_events['commit_before_draw'] = (
        frame_events['startTime_Commit'] < frame_events['startTime_Draw']
    )
    frame_events = frame_events.drop_duplicates(subset=['name_Begin', 'startTime_Begin'])
    frame_events['duration'] = -frame_events['startTime_Begin'].diff(periods=-1)
    frame_events = combine_first_two_frames(frame_events)
    frame_events['endTime'] = frame_events['startTime_Begin'].shift(periods=-1)
    frame_events = frame_events.drop(frame_events.tail(1).index)
    frame_events = frame_events.rename({'startTime_Begin': 'startTime'}, axis=1)
    frame_events['dropped'] = frame_events['name_Draw'] == 'DroppedFrame'
    frame_events['isPartial'] = False
    frame_events['drawn'] = ~frame_events['dropped']
    frame_events['idle'] = False
    return frame_events


def plot_requests(df: pd.DataFrame, start_time: float):
    """
    Plot rectangles showing each request duration
    """
    df['rectangle'] = df.apply(
        lambda x: (
            x['request_start'] - start_time,
            x.name,
            x['response_end'] - start_time,
            x.name + 1,
        ),
        axis=1,
    )
    boxes = hv.Rectangles(df['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgrey', xlabel='Time (ms)', yaxis=None, title='Network')
    return boxes


def plot_frames(df: pd.DataFrame, start_time: float, *, yl: int = 1):
    """
    Plot rectangles showing each fra,e duration
    """
    df['rectangle'] = df.apply(
        lambda x: (x['startTime'] - start_time, yl, x['endTime'] - start_time, yl + 1), axis=1
    )
    opts = {'width': 1000, 'xlabel': 'Time (ms)', 'yaxis': None, 'title': 'Frames'}
    subsets = {'idle': 'lightgrey', 'isPartial': 'yellow', 'dropped': 'red', 'drawn': 'lightgreen'}
    plots = {}
    for key, value in subsets.items():
        subset = df[df[key]]
        plots[key] = hv.Rectangles(subset['rectangle'].to_list())
        plots[key].opts(**opts, color=value)
    return plots['idle'] * plots['isPartial'] * plots['dropped'] * plots['drawn']


def plot_screenshot_rmse(
    df: pd.DataFrame,
    start_time: float,
):
    """
    Plot difference between the screenshots and baseline frames
    """
    opts = {'width': 1000, 'xlabel': 'Time (ms)', 'ylabel': 'RMSE', 'title': 'Sceenshots'}
    df['startTime_relative'] = df['startTime'] - start_time
    z0 = df.plot.line(x='startTime_relative', y='rmse_zoom0', label='Zoom 0 baseline')
    z1 = df.plot.line(x='startTime_relative', y='rmse_zoom1', label='Zoom 1 baseline')
    z2 = df.plot.line(x='startTime_relative', y='rmse_zoom2', label='Zoom 2 baseline')
    return (z0 * z1 * z2).opts(**opts)


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
    trace_data_fp = root_dir / f'chrome-devtools-traces/{args.timestamp}-{args.run}.json'
    # Load trace events
    trace_events = json.loads(trace_data_fp.read_text())['traceEvents']
    # Get start time
    start_time = get_start_time(trace_events=trace_events)
    # Extract request data
    url_filter = 'carbonplan-maps.s3.us-west-2.amazonaws.com/v2/demo'
    filtered_request_data = extract_request_data(trace_events=trace_events, url_filter=url_filter)
    # Extract frame data
    filtered_frames_data = extract_frame_data(trace_events=trace_events)
    # Extract screenshot data
    screenshot_data = extract_screenshots(trace_events=trace_events)
    # # Create plots
    requests_plt = plot_requests(filtered_request_data, start_time)
    frames_plt = plot_frames(filtered_frames_data, start_time, yl=2.5)
    rmse_plt = plot_screenshot_rmse(screenshot_data, start_time)
    # # Show plot using bokeh server
    hvplot.show((requests_plt + frames_plt + rmse_plt).cols(1))
