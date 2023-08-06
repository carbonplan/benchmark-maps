import argparse
import asyncio
import datetime
import json
import subprocess

import upath
from cloud_detect import provider
from playwright.async_api import async_playwright
from rich import print

BASE_URL = 'https://prototype-maps.vercel.app'
DATASETS_KEYS = ['1MB-chunks', '5MB-chunks', '10MB-chunks', '25MB-chunks']
ZARR_VERSIONS = ['v2', 'v3']
APPROACHES = ['direct-client']
SUPPORTED_ACTIONS = ['zoom_in', 'zoom_out']


# Get current timestamp
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')

# Initialize data storage
all_data = []


# Define console logging function
def log_console_message(msg):
    print(f'Browser console: {msg}')


async def mark_and_measure(*, page, start_mark: str, end_mark: str, label: str, timeout: int):
    # Define the JavaScript code to be executed
    javascript_code = f"""
        () => {{
            window._error = null;
            return new Promise((resolve, reject) => {{
                const THRESHOLD = '{timeout}';
                // timeout after THRESHOLD ms
                setTimeout(() => {{
                    console.log(`'{label}': ${{THRESHOLD}} ms threshold timeout reached.`);
                    if(window._error){{
                        reject(window._error);
                    }} else {{
                        window.performance.mark('{end_mark}');
                        window.performance.measure('{label}', '{start_mark}', '{end_mark}');
                        resolve();
                    }}
                }}, THRESHOLD);
            }})
            .catch((error) => {{
                window._error = `Error in page.evaluate: ${{error}}`;
                console.error(window._error)

            }});
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
    timeout: int,
    run_number: int,
    url: str,
    approach: str,
    dataset: str,
    zarr_version: str,
    playwright_python_version: str | None = None,
    benchmark_version: str | None = None,
    provider_name: str | None = None,
    trace_dir: upath.UPath,
    action: str | None = None,
    zoom_level: int | None = None,
    headless: bool = False,
):
    # Launch browser and create new page
    # https://chromium.googlesource.com/chromium/src/+/master/ui/gl/gl_switches.cc
    chrome_args = [
        '--enable-features=Vulkan,UseSkiaRenderer',
        '--enable-unsafe-webgpu',
        '--disable-vulkan-fallback-to-gl-for-testing',
        '--ignore-gpu-blocklist',
        # '--use-angle=vulkan', # this results in a Browser console: Error: Failed to initialize WebGL
    ]
    browser = await playwright.chromium.launch(headless=headless, args=chrome_args)

    context = await browser.new_context()
    page = await context.new_page()
    await browser.start_tracing(page=page, screenshots=True)

    # Log console messages
    page.on('console', log_console_message)

    # Start benchmark run
    print(f'[bold cyan]🚀 Starting benchmark run: {run_number}/{runs}...[/bold cyan]')

    # Go to URL
    print(
        f'🚀  Running benchmark for approach: {approach}, dataset: {dataset}, zarr_version: {zarr_version} on {url} 🚀'
    )
    await page.goto(url)

    # select approach in radio input
    await page.click(f'label:has(input[value="{approach}"])')

    # select 'Zarr version' dropdown
    await page.select_option('div:has-text("Zarr version") select', f'{zarr_version}')

    # Wait for the dropdown to be visible
    await page.wait_for_selector('text=Dataset')

    # Find the select element that is a child of the div containing the 'Dataset' text
    dataset_dropdown = await page.query_selector(
        'xpath=//div[text()="Dataset"]/following-sibling::div//select'
    )
    await dataset_dropdown.select_option(dataset)

    await asyncio.gather(
        page.evaluate(
            """
            () => (window.performance.mark("benchmark-initial-load:start"))
            """
        ),
        page.focus('.mapboxgl-canvas'),
        page.click('.mapboxgl-canvas'),
    )

    # Wait for the timeout to be reached
    await mark_and_measure(
        page=page,
        start_mark='benchmark-initial-load:start',
        end_mark='benchmark-initial-load:end',
        label='benchmark-initial-load',
        timeout=timeout,
    )

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
                page=page, start_mark=start_mark, end_mark=end_mark, label=label, timeout=timeout
            )

    # Stop tracing and save trace data
    trace_json = await browser.stop_tracing()
    await browser.close()

    trace_data = json.loads(trace_json)
    json_path = trace_dir / f'{now}-{run_number}.json'
    json_path.write_text(json.dumps(trace_data, indent=2))
    print(f"[bold cyan]📊 Trace data saved as '{json_path}'[/bold cyan]")

    # Record system metrics
    data = {
        'playwright_python_version': playwright_python_version,
        'benchmark_version': benchmark_version,
        'provider': provider_name,
        'browser_name': playwright.chromium.name,
        'browser_version': browser.version,
        'approach': approach,
        'zarr_version': zarr_version,
        'dataset': dataset,
        'action': action,
        'zoom_level': zoom_level,
        'trace_path': f'{now}-{run_number}.json',
        'url': url,
        'timeout': timeout,
    }

    all_data.append(data)


# Define main function
async def main(
    *,
    url: str,
    runs: int,
    timeout: int,
    approach: str,
    dataset: str,
    zarr_version: str,
    data_dir: upath.UPath,
    action: str | None = None,
    zoom_level: int | None = None,
    headless: bool,
    provider_name: str | None = None,
    benchmark_version: str | None = None,
):
    # Get Playwright versions
    playwright_python_version = subprocess.run(
        ['pip', 'show', 'playwright'],
        capture_output=True,
        text=True,
    )
    playwright_python_version = playwright_python_version.stdout.split('\n')[1].split(': ')[1]

    # Run benchmark
    async with async_playwright() as playwright:
        for run_number in range(runs):
            try:
                await run(
                    playwright=playwright,
                    url=url,
                    approach=approach,
                    dataset=dataset,
                    zarr_version=zarr_version,
                    runs=runs,
                    timeout=timeout,
                    run_number=run_number + 1,
                    playwright_python_version=playwright_python_version,
                    benchmark_version=benchmark_version,
                    provider_name=provider_name,
                    trace_dir=data_dir,
                    action=action,
                    zoom_level=zoom_level,
                    headless=headless,
                )
            except Exception as exc:
                print(f'{run_number + 1} timed out : {exc}')
                continue

    # Write the data to a json file
    data_path = data_dir / f'data-{now}.json'
    data_path.write_text(json.dumps(all_data, indent=2, sort_keys=True))
    print(f"[bold cyan]📊 Run metadata saved as '{data_path}'[/bold cyan]")


# Parse command line arguments and run main function
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to perform')
    parser.add_argument('--timeout', type=int, default=5000, help='Timeout limit in milliseconds')
    parser.add_argument(
        '--detect-provider', action='store_true', help='Detect provider', default=False
    )
    parser.add_argument(
        '--approach',
        type=str,
        default='direct-client',
        help=f'Approach to use. Must be one of: {APPROACHES}',
    )
    parser.add_argument(
        '--dataset',
        type=str,
        default=None,
        help=f'dataset name. Must be one of: {DATASETS_KEYS}',
    )
    parser.add_argument(
        '--zarr-version',
        type=str,
        default=None,
        help=f'Zarr version. Must be one of: {ZARR_VERSIONS}',
    )
    parser.add_argument('--non-headless', action='store_true', help='Run in non-headless mode')
    parser.add_argument('--s3-bucket', type=str, default=None, help='S3 bucket name')
    parser.add_argument(
        '--action',
        type=str,
        default=None,
        help=f'Action to perform. Must be one of: {SUPPORTED_ACTIONS}',
    )
    parser.add_argument('--zoom-level', type=int, default=None, help='Zoom level')

    args = parser.parse_args()

    # Validate arguments
    if args.action and args.action not in SUPPORTED_ACTIONS:
        raise ValueError(
            f'Invalid action: {args.action}. Supported operations are: {SUPPORTED_ACTIONS}'
        )

    if args.action and args.action.startswith('zoom') and args.zoom_level is None:
        raise ValueError(
            f'Invalid zoom level: {args.zoom_level}. Must be an integer greater than 0.'
        )

    if args.zoom_level and args.action is None:
        raise ValueError(
            f'Invalid zoom level: {args.zoom_level}. --action must be set if zoom-level is greater than 0.'
        )
    # Validate approach argument
    if args.approach not in APPROACHES:
        raise ValueError(f'Invalid approach: {args.approach}. Must be one of: {APPROACHES}')

    # Validate dataset argument
    if args.dataset not in DATASETS_KEYS:
        raise ValueError(f'Invalid dataset: {args.dataset}. Must be one of: {DATASETS_KEYS}')

    # Validate zarr version argument
    if args.zarr_version not in ZARR_VERSIONS:
        raise ValueError(
            f'Invalid zarr version: {args.zarr_version}. Must be one of: {ZARR_VERSIONS}'
        )

    # Detect benchmark version
    benchmark_version = (
        subprocess.check_output(['git', 'describe', '--always', '--dirty']).decode('ascii').strip()
    )

    # Define directories for data and screenshots
    root_dir = upath.UPath(__file__).parent
    data_dir = (
        upath.UPath(args.s3_bucket) / 'benchmark-data' / benchmark_version
        if args.s3_bucket
        else root_dir / 'data' / benchmark_version
    )
    data_dir.mkdir(exist_ok=True, parents=True)

    # Detect cloud provider
    provider_name = provider() if args.detect_provider else 'unknown'

    asyncio.run(
        main(
            runs=args.runs,
            timeout=args.timeout,
            approach=args.approach,
            dataset=args.dataset,
            zarr_version=args.zarr_version,
            url=BASE_URL,
            provider_name=provider_name,
            benchmark_version=benchmark_version,
            data_dir=data_dir,
            action=args.action,
            zoom_level=args.zoom_level,
            headless=not args.non_headless,
        )
    )
