import argparse
import datetime
import json
import pathlib
import tempfile

import numpy as np
from playwright.sync_api import sync_playwright
from rich import box, print
from rich.columns import Columns
from rich.panel import Panel

data_dir = pathlib.Path(__file__).parent / 'data'
data_dir.mkdir(exist_ok=True, parents=True)

# get temporary folder for screenshots
temp_dir_path = pathlib.Path(tempfile.gettempdir())


now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
all_data = []


def run(*, playwright, runs: int, run_number: int, time_since_last_paint_threshold: int):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    print(f'[bold cyan]🚀 Starting benchmark run: {run_number}/{runs}...[/bold cyan]')

    request_data = []

    # Subscribe to "requestfinished" events.
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
        if 'storage.googleapis.com/carbonplan-maps/v2/demo' in request.url
        else None,
    )

    page.goto('https://maps.demo.carbonplan.org/')

    # Focus on the map element
    page.focus('.mapboxgl-canvas')

    # Click on the map element
    page.click('.mapboxgl-canvas')

    # Create the PerformanceObserver in the page's context
    page.evaluate(
        """
        window._lastPaint = performance.now();
        window._perfObserver = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (entry.entryType === 'paint') {
                    window._lastPaint = performance.now();
                }
            }
        });
        window._perfObserver.observe({ entryTypes: ['paint'] });
    """
    )

    # Start the timer and initialize frame counter in the page
    # this measures the frame rate and frame durations only during actual content changes,
    # by counting frames when a paint event has occurred.
    # the following approach involves storing the time of the last paint event and
    # only counting a frame if the time since the last paint event is less than a certain threshold (e.g., 500 ms)
    # the _frameCounter and _frameDurations will only be updated when the page is actively being painted.

    page.evaluate(
        """
    window._frameCounter = 0;
    window._timerStart = performance.now();
    window._frameDurations = [];
    window._prevFrameTime = performance.now();
    window._rafId = requestAnimationFrame(function countFrames() {
        const currentTime = performance.now();
        const timeSinceLastPaint = currentTime - window._lastPaint;
        if (timeSinceLastPaint < 500) {  // Change this threshold as needed
            window._frameDurations.push(currentTime - window._prevFrameTime);
            window._frameCounter++;
        }
        window._prevFrameTime = currentTime;
        window._rafId = requestAnimationFrame(countFrames);
    });
"""
    )

    # Wait until no paint events have occurred for the duration of the threshold
    page.wait_for_function(
        f"""
        () => {{
            const timeSinceLastPaint = performance.now() - window._lastPaint;
            return timeSinceLastPaint > {time_since_last_paint_threshold};  // If time since last paint is more than threshold
        }}

    """
    )

    # Cancel the frame counting and calculate FPS, total duration and frame durations
    durations = page.evaluate(
        """
        cancelAnimationFrame(window._rafId);
        const timerEnd = performance.now();
        const durationInSeconds = (timerEnd - window._timerStart) / 1000;
        const fps = window._frameCounter / durationInSeconds;
        const frameDurations = window._frameDurations;
        [fps, frameDurations, window._timerStart, timerEnd];
    """
    )

    # save screenshot to temporary file
    path = temp_dir_path / f'{now}-{run_number}.png'

    page.screenshot(path=path)
    print(f"[bold cyan]📸 Screenshot saved as '{path}'[/bold cyan]")
    browser.close()
    fps = durations[0]
    frame_durations = durations[1]
    timer_start = durations[2]
    timer_end = durations[3]

    # record frame duration and fps

    data = {
        'average_fps': round(fps, 0),
        'frame_durations_in_ms': frame_durations,
        'request_data': request_data,
        'timer_start': timer_start,
        'timer_end': timer_end,
        'total_duration_in_ms': timer_end - timer_start,
        'time_since_last_paint_threshold': time_since_last_paint_threshold,
    }

    all_data.append(data)


def main(*, runs: int, time_since_last_paint_threshold: int):
    with sync_playwright() as playwright:
        for run_number in range(runs):
            run(
                playwright=playwright,
                runs=runs,
                run_number=run_number + 1,
                time_since_last_paint_threshold=time_since_last_paint_threshold,
            )

        # compute an aggregate of the data
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

        configs = [
            Panel(
                f'[bold green]🔄 Number of runs: {runs}[/bold green]', box=box.DOUBLE, expand=False
            ),
            Panel(
                f"[bold green]⏱️ Time since last paint threshold: {all_data[0]['time_since_last_paint_threshold']} ms[/bold green]",
                box=box.ROUNDED,
                expand=False,
            ),
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to perform')
    parser.add_argument(
        '--time-since-last-paint-threshold',
        type=int,
        default=700,
        help='Time since last paint threshold in ms',
    )
    args = parser.parse_args()
    main(runs=args.runs, time_since_last_paint_threshold=args.time_since_last_paint_threshold)
