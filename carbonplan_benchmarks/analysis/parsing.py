# Utilities for parsing information from chromium trace records

import pandas as pd


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


def process_rendering_events(df, trace_start_time):
    """
    Process rendering events by adding startTime in ms, normalizing dtypes, and sorting by time.

    Parameters
    ----------

    df: pd.DataFrame
        DataFrame containing event information

    trace_start_time: float
        Start time of the trace record in ms

    Returns
    -------
    df : Processed DataFrame containing event information
    """
    df['startTime'] = df['ts'] * 1e-3 - trace_start_time
    # df['startTimeOffset'] = df['startTime'] - traceStartTime
    if 'args.frameSeqId' in df.columns and ~df['args.frameSeqId'].isnull().values.any():
        df['args.frameSeqId'] = df['args.frameSeqId'].astype(int)
    return df.sort_values(by='startTime')


def extract_event_type(*, trace_events, event_name, exact=True):
    """
    Extract specific event type from a list of Chromium trace events.

    Parameters
    ----------

    trace_events: list
        The list of trace events.

    event_name: str
        Name of event to extract.

    exact: bool
        Require exact match of event_name

    Returns
    -------
    events : DataFrame containing information about events
    """
    trace_start_time = get_start_time(trace_events=trace_events)
    if exact:
        events = pd.json_normalize([event for event in trace_events if event['name'] == event_name])
    else:
        events = pd.json_normalize([event for event in trace_events if event_name in event['name']])
    events = process_rendering_events(events, trace_start_time)
    return events


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
    start_time = get_start_time(trace_events=trace_events)
    send_requests = extract_event_type(trace_events=trace_events, event_name='ResourceSendRequest')
    finish_requests = extract_event_type(trace_events=trace_events, event_name='ResourceFinish')
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
    data['request_start'] = data['request_start'] * 1e-3 - start_time
    data['response_end'] = data['response_end'] * 1e-3 - start_time
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
    begin_frame_events = extract_event_type(trace_events=trace_events, event_name='BeginFrame')
    draw_frame_events = extract_event_type(trace_events=trace_events, event_name='DrawFrame')
    dropped_frame_events = extract_event_type(trace_events=trace_events, event_name='DroppedFrame')
    commit_events = extract_event_type(trace_events=trace_events, event_name='Commit').dropna(
        subset=['args.frameSeqId']
    )
    commit_events['args.frameSeqId'] = commit_events['args.frameSeqId'].astype(int)
    # Drop duplicates
    begin_frame_events.drop_duplicates(subset=['args.frameSeqId'], inplace=True)

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
    frame_events['endTime'] = frame_events['startTime_Begin'].shift(periods=-1)
    frame_events = frame_events.drop(frame_events.tail(1).index)
    frame_events = frame_events.rename({'startTime_Begin': 'startTime'}, axis=1)
    frame_events['dropped'] = frame_events['name_Draw'] == 'DroppedFrame'
    frame_events['isPartial'] = False
    frame_events['drawn'] = ~frame_events['dropped']
    frame_events['idle'] = False
    return frame_events
