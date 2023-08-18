import asyncio
import datetime
import json
import subprocess

import upath
from playwright.async_api import async_playwright
from rich import print

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
    variable: str,
    playwright_python_version: str | None = None,
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
    print(f'🚀  Running benchmark for approach: {approach}, dataset: {dataset} on {url} 🚀')
    await page.goto(f'{url}/{approach}/{dataset}')

    # Wait for the dropdown to be visible
    await page.wait_for_selector('text=Variable')

    # Find the select element that is a child of the div containing the 'Dataset' text
    variable_dropdown = await page.query_selector(
        'xpath=//div[text()="Variable"]/following-sibling::div//select'
    )
    await variable_dropdown.select_option(variable)

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
        'provider': provider_name,
        'browser_name': playwright.chromium.name,
        'browser_version': browser.version,
        'action': action,
        'zoom_level': zoom_level,
        'trace_path': str(json_path),
        'url': url,
        'timeout': timeout,
    }

    all_data.append(data)


# Define main function
async def start(
    *,
    url: str,
    runs: int,
    timeout: int,
    approach: str,
    dataset: str,
    variable: str,
    data_dir: upath.UPath,
    action: str | None = None,
    zoom_level: int | None = None,
    headless: bool,
    provider_name: str | None = None,
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
                    variable=variable,
                    runs=runs,
                    timeout=timeout,
                    run_number=run_number + 1,
                    playwright_python_version=playwright_python_version,
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
