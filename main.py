import argparse
import datetime
import json
import pathlib
import subprocess

import numpy as np
from cloud_detect import provider
from playwright.sync_api import sync_playwright
from rich import box, print
from rich.columns import Columns
from rich.panel import Panel

# Get current timestamp
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')

# Initialize data storage
all_data = []


# Define console logging function
def log_console_message(msg):
    print(f'Browser console: {msg}')


def calculate_frame_durations_and_fps(*, trace_events: list):
    """
    Calculate frame durations and frames per second (FPS) from a list of Chromium trace events.

    Parameters
    ----------
    trace_events : list
        The list of trace events.

    Returns
    -------
    frame_durations_s : list
        The list of frame durations in seconds.
    fps_values : list
        The list of frames per second (FPS) values.
    frame_timestamps_micros : list
        The list of timestamps corresponding to the start of each frame.
    """

    # Chromium trace events contain a 'name' field that indicates the type of the event.
    # 'Swap' events signify that a new frame is ready to be displayed. The 'ph' field
    # indicates the phase of the event: 'b' for begin and 'e' for end. We're interested in
    # the 'b' (begin) phase, which signifies the start of a new frame.

    # Filter out 'Swap' events that signify the start of a new frame
    swap_begin_events = [
        event for event in trace_events if event['name'] == 'Swap' and event['ph'] == 'b'
    ]

    # Initialize lists to hold the frame durations in seconds, FPS values, and frame timestamps
    frame_durations_s = []
    frame_timestamps_micros = []
    fps_values = []

    # Iterate over the 'Swap' events, starting from the second one
    for i in range(1, len(swap_begin_events)):
        # Calculate the duration of each frame in microseconds as the difference in timestamps
        # between consecutive 'Swap' events
        duration_micros = swap_begin_events[i]['ts'] - swap_begin_events[i - 1]['ts']

        # Exclude instances where the frame duration is zero, which could occur if two 'Swap'
        # events have the same timestamp due to simultaneous frame swaps or inaccuracies in
        # the timestamp recording
        if duration_micros > 0:
            # Convert the frame duration to seconds
            duration_s = duration_micros / 1e6
            frame_durations_s.append(duration_s)

            # Add the timestamp of the 'Swap' event, which signifies the start of the frame
            frame_timestamps_micros.append(swap_begin_events[i]['ts'])

            # Calculate the frames per second (FPS) as the reciprocal of the frame duration
            fps_values.append(1 / duration_s)

    return frame_durations_s, fps_values, frame_timestamps_micros


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
    request_data : list of dictionaries, each containing information about a request.
        A list of dictionaries, each containing information about a request.
    """
    send_request_events = {}
    finish_request_events = {}

    # Collect 'ResourceSendRequest' and 'ResourceFinish' events, indexed by request ID
    for event in trace_events:
        if event['name'] == 'ResourceSendRequest':
            request_id = event['args']['data']['requestId']
            send_request_events[request_id] = event
        elif event['name'] == 'ResourceFinish':
            request_id = event['args']['data']['requestId']
            finish_request_events[request_id] = event

    request_data = []

    # Combine the send and finish events for each request
    for request_id, send_event in send_request_events.items():
        finish_event = finish_request_events.get(request_id)
        if finish_event is not None:
            url = send_event['args']['data']['url']
            # If a URL filter is specified, skip URLs that don't contain the filter string
            if url_filter is not None and url_filter not in url:
                continue

            method = send_event['args']['data']['requestMethod']
            total_response_time_ms = (
                finish_event['ts'] - send_event['ts']
            ) / 1e3  # Convert to milliseconds
            response_end = finish_event['ts'] / 1e3  # Convert to milliseconds
            request_start = send_event['ts'] / 1e3  # Convert to milliseconds

            request_data.append(
                {
                    'method': method,
                    'url': url,
                    'total_response_time_ms': total_response_time_ms,
                    'response_end': response_end,
                    'request_start': request_start,
                }
            )

    return request_data


# Define main benchmarking function
def run(
    *,
    playwright,
    runs: int,
    run_number: int,
    url: str = 'https://maps-demo-git-katamartin-benchmarking-carbonplan.vercel.app/',
    playwright_python_version: str | None = None,
    provider_name: str | None = None,
    screenshot_dir: pathlib.Path,
    trace_dir: pathlib.Path,
):
    # Launch browser and create new page
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()
    browser.start_tracing(page=page, screenshots=True)
    # set new CDPSession to get performance metrics
    client = page.context.new_cdp_session(page)
    client.send('Performance.enable')
    # enable FPS counter and GPU metrics overlay
    client.send('Overlay.setShowFPSCounter', {'show': True})

    # Log console messages
    page.on('console', log_console_message)

    # Start benchmark run
    print(f'[bold cyan]🚀 Starting benchmark run: {run_number}/{runs}...[/bold cyan]')

    # Initialize request data storage
    request_data = []

    # Subscribe to "requestfinished" events
    page.on(
        'requestfinished',
        lambda request: request_data.append(
            {
                'method': request.method,
                'url': request.url,
                'total_response_time_in_ms': request.timing['responseEnd']
                - request.timing['requestStart'],
                'response_end': request.timing['responseEnd'],
                'request_start': request.timing['requestStart'],
            }
        )
        if 'carbonplan-maps.s3.us-west-2.amazonaws.com/v2/demo' in request.url
        else None,
    )

    # Go to URL
    page.goto(url)

    # Focus on and click the map element
    page.focus('.mapboxgl-canvas')
    page.click('.mapboxgl-canvas')

    # click the button that is a sibling of the div with the text "Display".
    page.click('//div[text()="Display"]/following-sibling::button')

    # Start frame counting
    page.evaluate(
        """
    window._frameCounter = 0;
    window._timerStart = performance.now();
    window._frameStarts = [];
    window._frameEnds = [];
    window._frameDurations = [];
    window._prevFrameTime = performance.now();
    window._rafId = requestAnimationFrame(function countFrames() {{
        const currentTime = performance.now();
        const duration = currentTime - window._prevFrameTime;
        window._frameStarts.push(window._prevFrameTime)
        window._frameEnds.push(currentTime)
        window._frameDurations.push(duration);
        window._prevFrameTime = currentTime;
        window._frameCounter++;
        window._rafId = requestAnimationFrame(countFrames);
    }});
    """
    )

    # Wait for the map to be idle and then stop frame counting
    page.evaluate(
        """
        () => {
        window._error = null;
        if (!window._map) {
            window._error = 'window._map does not exist'
            console.error(window._error)
            cancelAnimationFrame(window._rafId)
            window._timerEnd = performance.now()
        }

        return new Promise((resolve, reject) => {
            const THRESHOLD = 5000
            // timeout after THRESHOLD ms if idle event is not seen
            setTimeout(() => {
                window._error = `No idle events seen after ${THRESHOLD}ms`;
                reject(window._error)
            }, THRESHOLD)
            window._map.onIdle(() => {
                console.log('window._map.onIdle callback called')
                cancelAnimationFrame(window._rafId)
                window._timerEnd = performance.now()
                resolve()
            })
        }).catch((error) => {
            window._error = 'Error in page.evaluate: ' + error;
            console.error(window._error);
            cancelAnimationFrame(window._rafId)
            window._timerEnd = performance.now()
        })
        }

    """
    )

    if error := page.evaluate('window._error'):
        raise Exception(error)

    # Save screenshot to temporary file
    path = screenshot_dir / f'{now}-{run_number}.png'
    page.screenshot(path=path)
    print(f"[bold cyan]📸 Screenshot saved as '{path}'[/bold cyan]")

    # Get the captured frame durations and FPS
    frame_starts = page.evaluate('window._frameStarts')
    frame_ends = page.evaluate('window._frameEnds')
    frame_durations = page.evaluate('window._frameDurations')
    timer_end = page.evaluate('window._timerEnd')
    timer_start = page.evaluate('window._timerStart')
    frame_counter = page.evaluate('window._frameCounter')
    trace_json = browser.stop_tracing()
    trace_data = json.loads(trace_json)
    json_path = trace_dir / f'{now}-{run_number}.json'
    with open(json_path, 'w') as f:
        json.dump(trace_data, f, indent=2)
        print(f"[bold cyan]📊 Trace data saved as '{json_path}'[/bold cyan]")

    browser.close()
    fps = frame_counter / ((timer_end - timer_start) / 1000)
    url_filter = 'carbonplan-maps.s3.us-west-2.amazonaws.com/v2/demo'
    filtered_request_data = extract_request_data(
        trace_events=trace_data['traceEvents'], url_filter=url_filter
    )

    frame_durations_s, fps_values, frame_timestamps_micros = calculate_frame_durations_and_fps(
        trace_events=trace_data['traceEvents']
    )

    # Record system metrics
    data = {
        'average_fps': round(fps, 0),
        'frame_starts_in_ms': frame_starts,
        'frame_ends_in_ms': frame_ends,
        'frame_durations_in_ms': frame_durations,
        'request_data': request_data,
        'chromium_trace_request_data': filtered_request_data,
        'chromium_trace_frame_durations_in_s': frame_durations_s,
        'chromium_trace_fps': fps_values,
        'chromium_trace_frame_timestamps_in_micros': frame_timestamps_micros,
        'timer_start': timer_start,
        'timer_end': timer_end,
        'total_duration_in_ms': timer_end - timer_start,
        'playwright_python_version': playwright_python_version,
        'provider': provider_name,
        'browser_name': playwright.chromium.name,
        'browser_version': browser.version,
    }

    all_data.append(data)


# Define main function
def main(
    *,
    runs: int,
    detect_provider: bool = False,
    data_dir: pathlib.Path,
    screenshot_dir: pathlib.Path,
    trace_dir: pathlib.Path,
):
    # Get Playwright versions
    playwright_python_version = subprocess.run(
        ['pip', 'show', 'playwright'],
        capture_output=True,
        text=True,
    )
    playwright_python_version = playwright_python_version.stdout.split('\n')[1].split(': ')[1]

    # Detect cloud provider
    provider_name = provider() if detect_provider else 'unknown'

    # Run benchmark
    with sync_playwright() as playwright:
        for run_number in range(runs):
            try:
                run(
                    playwright=playwright,
                    runs=runs,
                    run_number=run_number + 1,
                    playwright_python_version=playwright_python_version,
                    provider_name=provider_name,
                    screenshot_dir=screenshot_dir,
                    trace_dir=trace_dir,
                )
            except Exception as exc:
                print(f'{run_number + 1} timed out : {exc}')
                continue

    # Compute an aggregate of the data
    average_fps = np.mean([x['average_fps'] for x in all_data])
    average_frame_duration = np.mean(
        [x['total_duration_in_ms'] / x['average_fps'] for x in all_data]
    )
    average_total_duration = np.mean([x['total_duration_in_ms'] for x in all_data])

    total_response_times = []

    for data in all_data:
        total_response_times.extend(
            request_data['total_response_time_in_ms'] for request_data in data['request_data']
        )
    average_request_duration = np.mean(total_response_times)
    median_request_duration = np.median(total_response_times)
    frame_duration_percentiles = np.percentile(total_response_times, [25, 50, 75, 90])

    # Display results
    configs = [
        Panel(f'[bold green]🔄 Number of runs: {runs}[/bold green]', box=box.DOUBLE, expand=False)
    ]

    frame_results = [
        Panel(
            f'[bold green]📊 Average FPS: {average_fps:.2f}[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ Average frame duration: {average_frame_duration:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ 25th percentile frame duration: {frame_duration_percentiles[0]:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ 50th percentile frame duration: {frame_duration_percentiles[1]:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ 75th percentile frame duration: {frame_duration_percentiles[2]:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ 90th percentile frame duration: {frame_duration_percentiles[3]:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
    ]

    duration_results = [
        Panel(
            f'[bold green]⏱️ Average total duration: {average_total_duration:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        )
    ]

    request_results = [
        Panel(
            f'[bold green]⏱️ Average request duration: {average_request_duration:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
        Panel(
            f'[bold green]⏱️ Median request duration: {median_request_duration:.2f} ms[/bold green]',
            box=box.DOUBLE,
            expand=False,
        ),
    ]

    # Print results
    print(Panel('[bold blue]Frame Results[/bold blue]', box=box.DOUBLE, expand=False))
    print(Columns(frame_results, equal=True, expand=False))

    print(Panel('[bold blue]Request Results[/bold blue]', box=box.DOUBLE, expand=False))
    print(Columns(request_results, equal=True, expand=False))

    print(Panel('[bold blue]Duration Results[/bold blue]', box=box.DOUBLE, expand=False))
    print(Columns(duration_results, equal=True, expand=False))

    print(Panel('[bold blue]Config[/bold blue]', box=box.DOUBLE, expand=False))
    print(Columns(configs, equal=True, expand=False))

    # Write the data to a json file
    with open(data_dir / f'data-{now}.json', 'w') as outfile:
        json.dump(all_data, outfile, indent=4, sort_keys=True)


# Parse command line arguments and run main function
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to perform')
    parser.add_argument(
        '--detect-provider', action='store_true', help='Detect provider', default=False
    )
    args = parser.parse_args()
    # Define directories for data and screenshots
    root_dir = pathlib.Path(__file__).parent
    data_dir = root_dir / 'data'
    data_dir.mkdir(exist_ok=True, parents=True)
    screenshot_dir = root_dir / 'playwright-screenshots'
    screenshot_dir.mkdir(exist_ok=True, parents=True)
    trace_dir = root_dir / 'chrome-devtools-traces'
    trace_dir.mkdir(exist_ok=True, parents=True)

    main(
        runs=args.runs,
        detect_provider=args.detect_provider,
        data_dir=data_dir,
        screenshot_dir=screenshot_dir,
        trace_dir=trace_dir,
    )
