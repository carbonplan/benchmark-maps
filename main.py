import argparse
import datetime
import json
import pathlib
import subprocess

from cloud_detect import provider
from playwright.sync_api import sync_playwright
from rich import print

# Get current timestamp
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')

# Initialize data storage
all_data = []


# Define console logging function
def log_console_message(msg):
    print(f'Browser console: {msg}')


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

    # Go to URL
    page.goto(url)

    # Focus on and click the map element
    page.focus('.mapboxgl-canvas')
    page.click('.mapboxgl-canvas')
    # use performance.mark API to mark the start of the benchmarks.
    page.evaluate(
        """
        () => (window.performance.mark("benchmark:start"))
                  """
    )

    # click the button that is a sibling of the div with the text "Display".
    page.click('//div[text()="Display"]/following-sibling::button')

    # Start timer
    page.evaluate(
        """
    window._timerStart = performance.now();
    """
    )

    # Wait for the map to be idle and then stop timer
    page.evaluate(
        """
        () => {
        window._error = null;
        if (!window._map) {
            window._error = 'window._map does not exist'
            console.error(window._error)
            window.performance.mark('benchmark:end')
            window.performance.measure('benchmark', 'benchmark:start', 'benchmark:end')
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
                window.performance.mark('benchmark:end')
                window.performance.measure('benchmark', 'benchmark:start', 'benchmark:end')
                window._timerEnd = performance.now()
                resolve()
            })
        }).catch((error) => {
            window._error = 'Error in page.evaluate: ' + error;
            console.error(window._error);
            window.performance.mark('benchmark:end')
            window.performance.measure('benchmark', 'benchmark:start', 'benchmark:end')
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

    timer_end = page.evaluate('window._timerEnd')
    timer_start = page.evaluate('window._timerStart')

    trace_json = browser.stop_tracing()
    trace_data = json.loads(trace_json)
    json_path = trace_dir / f'{now}-{run_number}.json'
    with open(json_path, 'w') as f:
        json.dump(trace_data, f, indent=2)
        print(f"[bold cyan]📊 Trace data saved as '{json_path}'[/bold cyan]")

    browser.close()

    # Record system metrics
    data = {
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
