import argparse
import asyncio

import upath
from cloud_detect import provider

from .. import __version__
from .run import start

BASE_URL = 'https://prototype-maps.vercel.app'
DATASETS_KEYS = ['pyramids-v3-sharded-4326-1MB', 'pyramids-v3-sharded-4326-5MB']
VARIABLES = ['tasmax']
APPROACHES = ['dynamic-client']
SUPPORTED_ACTIONS = ['zoom_in', 'zoom_out']


# Parse command line arguments and run main function
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to perform')
    parser.add_argument('--timeout', type=int, default=5000, help='Timeout limit in milliseconds')
    parser.add_argument(
        '--detect-provider', action='store_true', help='Detect provider', default=False
    )
    parser.add_argument(
        '--approach',
        type=str,
        default='dynamic-client',
        help=f'Approach to use. Must be one of: {APPROACHES}',
    )
    parser.add_argument(
        '--dataset',
        type=str,
        default=None,
        help=f'dataset name. Must be one of: {DATASETS_KEYS}',
    )
    parser.add_argument(
        '--variable',
        type=str,
        default='tasmax',
        help=f'Zarr version. Must be one of: {VARIABLES}',
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
    if args.variable not in VARIABLES:
        raise ValueError(f'Invalid zarr version: {args.variable}. Must be one of: {VARIABLES}')

    # Define directories for data and screenshots
    benchmark_version = '.'.join(__version__.split('.')[0:2])

    data_dir = (
        upath.UPath(args.s3_bucket) / 'benchmark-data' / benchmark_version
        if args.s3_bucket
        else upath.UPath('data') / benchmark_version
    )
    data_dir.mkdir(exist_ok=True, parents=True)

    # Detect cloud provider
    provider_name = provider() if args.detect_provider else 'unknown'

    asyncio.run(
        start(
            runs=args.runs,
            timeout=args.timeout,
            approach=args.approach,
            dataset=args.dataset,
            variable=args.variable,
            url=BASE_URL,
            provider_name=provider_name,
            data_dir=data_dir,
            action=args.action,
            zoom_level=args.zoom_level,
            headless=not args.non_headless,
            benchmark_version=benchmark_version,
        )
    )


if __name__ == '__main__':
    main()
