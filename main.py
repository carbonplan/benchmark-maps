import argparse
import asyncio
import datetime
import json
import pathlib
import subprocess

from cloud_detect import provider
from playwright.async_api import async_playwright
from rich import print

# Get current timestamp
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')

# Initialize data storage
all_data = []


# Define console logging function
def log_console_message(msg):
    print(f'Browser console: {msg}')


async def mark_and_measure(*, page, start_mark: str, end_mark: str, label: str):
    # Define the JavaScript code to be executed
    javascript_code = f"""
    () => {{
    window._error = null;
    if (!window._map) {{
        window._error = 'window._map does not exist'
        console.error(window._error)
        window.performance.mark('{end_mark}')
        window.performance.measure('{label}', '{start_mark}', '{end_mark}')

    }}

    return new Promise((resolve, reject) => {{
        const THRESHOLD = 5000
        // timeout after THRESHOLD ms if idle event is not seen
        setTimeout(() => {{
            window._error = `No idle events seen after ${{THRESHOLD}}ms`;
            reject(window._error)
        }}, THRESHOLD)
        window._map.onIdle(() => {{
            console.log('window._map.onIdle callback called')
            window.performance.mark('{end_mark}')
            window.performance.measure('{label}', '{start_mark}', '{end_mark}')

            resolve()
        }})
    }}).catch((error) => {{
        window._error = 'Error in page.evaluate: ' + error;
        console.error(window._error);
        window.performance.mark('{end_mark}')
        window.performance.measure('{label}', '{start_mark}', '{end_mark}')

    }})
    }}
    """

    # Use the JavaScript code in the page.evaluate() call
    await page.evaluate(javascript_code)

    # If there was an error, raise an exception
    if error := await page.evaluate('window._error'):
        raise RuntimeError(error)


# Define main benchmarking function
async def run(
    *,
    playwright,
    runs: int,
    run_number: int,
    url: str = 'https://maps-demo-git-katamartin-benchmarking-carbonplan.vercel.app/',
    playwright_python_version: str | None = None,
    provider_name: str | None = None,
    screenshot_dir: pathlib.Path,
    trace_dir: pathlib.Path,
    action: str | None = None,
    zoom_level: int | None = None,
):
    # Launch browser and create new page
    browser = await playwright.chromium.launch()
    context = await browser.new_context()
    page = await context.new_page()
    await browser.start_tracing(page=page, screenshots=True)
    # set new CDPSession to get performance metrics
    client = await page.context.new_cdp_session(page)
    await client.send('Performance.enable')
    # enable FPS counter and GPU metrics overlay
    await client.send('Overlay.setShowFPSCounter', {'show': True})

    # Log console messages
    page.on('console', log_console_message)

    # Start benchmark run
    print(f'[bold cyan]🚀 Starting benchmark run: {run_number}/{runs}...[/bold cyan]')

    # Go to URL
    await page.goto(url)

    # Focus on and click the map element
    await page.focus('.mapboxgl-canvas')
    await page.click('.mapboxgl-canvas')
    await asyncio.gather(
        page.evaluate(
            """
            () => (window.performance.mark("benchmark:start"))
            """
        ),
        page.click('//div[text()="Display"]/following-sibling::button'),
    )

    await asyncio.gather(page.focus('.mapboxgl-canvas'), page.click('.mapboxgl-canvas'))

    if zoom_level:
        for level in range(zoom_level):
            start_mark = f'benchmark-{action}-level-{level}:start'
            end_mark = f'benchmark-{action}-level-{level}:end'
            label = f'benchmark-{action}-level-{level}'
            if action == 'zoom_in':
                await asyncio.gather(
                    page.evaluate(
                        f"""
                        () => (window.performance.mark("{start_mark}"))
                        """
                    ),
                    page.keyboard.press('='),
                )
                await mark_and_measure(
                    page=page, start_mark=start_mark, end_mark=end_mark, label=label
                )
            elif action == 'zoom_out':
                await asyncio.gather(
                    page.evaluate(
                        f"""
                        () => (window.performance.mark("{start_mark}"))
                        """
                    ),
                    page.keyboard.press('-'),
                )
                await mark_and_measure(
                    page=page, start_mark=start_mark, end_mark=end_mark, label=label
                )

    # Wait for the map to be idle and then stop timer
    await mark_and_measure(
        page=page, start_mark='benchmark:start', end_mark='benchmark:end', label='benchmark'
    )
    # Save screenshot to temporary file
    path = screenshot_dir / f'{now}-{run_number}.png'
    await page.screenshot(path=path)
    print(f"[bold cyan]📸 Screenshot saved as '{path}'[/bold cyan]")

    trace_json = await browser.stop_tracing()
    await browser.close()

    trace_data = json.loads(trace_json)
    json_path = (
        trace_dir / f'{now}-{run_number}.json'
        if action is None
        else trace_dir / f'{now}-{run_number}-{action}.json'
    )
    with open(json_path, 'w') as f:
        json.dump(trace_data, f, indent=2)
        print(f"[bold cyan]📊 Trace data saved as '{json_path}'[/bold cyan]")

    # Record system metrics
    data = {
        'playwright_python_version': playwright_python_version,
        'provider': provider_name,
        'browser_name': playwright.chromium.name,
        'browser_version': browser.version,
        'action': action,
        'zoom_level': zoom_level,
    }

    all_data.append(data)


# Define main function
async def main(
    *,
    runs: int,
    detect_provider: bool = False,
    data_dir: pathlib.Path,
    screenshot_dir: pathlib.Path,
    trace_dir: pathlib.Path,
    action: str | None = None,
    zoom_level: int | None = None,
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
    async with async_playwright() as playwright:
        for run_number in range(runs):
            try:
                await run(
                    playwright=playwright,
                    runs=runs,
                    run_number=run_number + 1,
                    playwright_python_version=playwright_python_version,
                    provider_name=provider_name,
                    screenshot_dir=screenshot_dir,
                    trace_dir=trace_dir,
                    action=action,
                    zoom_level=zoom_level,
                )
            except Exception as exc:
                print(f'{run_number + 1} timed out : {exc}')
                continue

    # Write the data to a json file
    data_path = (
        data_dir / f'data-{now}.json' if action is None else data_dir / f'data-{now}-{action}.json'
    )
    with open(data_path, 'w') as outfile:
        json.dump(all_data, outfile, indent=4, sort_keys=True)


# Parse command line arguments and run main function
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to perform')
    parser.add_argument(
        '--detect-provider', action='store_true', help='Detect provider', default=False
    )
    parser.add_argument('--action', type=str, default=None, help='Action to perform')
    parser.add_argument('--zoom-level', type=int, default=None, help='Zoom level')

    args = parser.parse_args()

    # Perform operation
    supported_actions = ['zoom_in', 'zoom_out']
    if args.action and args.action not in supported_actions:
        raise ValueError(
            f'Invalid action: {args.action}. Supported operations are: {supported_actions}'
        )

    if args.action and args.action.startswith('zoom') and args.zoom_level is None:
        raise ValueError(
            f'Invalid zoom level: {args.zoom_level}. Must be an integer greater than 0.'
        )

    # Define directories for data and screenshots
    root_dir = pathlib.Path(__file__).parent
    data_dir = root_dir / 'data'
    data_dir.mkdir(exist_ok=True, parents=True)
    screenshot_dir = root_dir / 'playwright-screenshots'
    screenshot_dir.mkdir(exist_ok=True, parents=True)
    trace_dir = root_dir / 'chrome-devtools-traces'
    trace_dir.mkdir(exist_ok=True, parents=True)

    asyncio.run(
        main(
            runs=args.runs,
            detect_provider=args.detect_provider,
            data_dir=data_dir,
            screenshot_dir=screenshot_dir,
            trace_dir=trace_dir,
            action=args.action,
            zoom_level=args.zoom_level,
        )
    )
