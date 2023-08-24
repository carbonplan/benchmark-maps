<p align='left'>
  <a href='https://carbonplan.org/#gh-light-mode-only'>
    <img
      src='https://carbonplan-assets.s3.amazonaws.com/monogram/dark-small.png'
      height='48px'
    />
  </a>
  <a href='https://carbonplan.org/#gh-dark-mode-only'>
    <img
      src='https://carbonplan-assets.s3.amazonaws.com/monogram/light-small.png'
      height='48px'
    />
  </a>
</p>

# carbonplan / benchmark-maps

## Running the benchmarks

The repository contains a set of benchmarks that can be run locally or remotely using `coiled`. The benchmarks are run using the `carbonplan_benchmarks` CLI. The CLI takes the following arguments:

```bash
$ carbonplan_benchmarks --help
usage: carbonplan_benchmarks [-h] [--runs RUNS] [--timeout TIMEOUT] [--detect-provider] [--approach APPROACH] [--dataset DATASET] [--variable VARIABLE] [--non-headless]
                             [--s3-bucket S3_BUCKET] [--action ACTION] [--zoom-level ZOOM_LEVEL]

options:
  -h, --help            show this help message and exit
  --runs RUNS           Number of runs to perform
  --timeout TIMEOUT     Timeout limit in milliseconds
  --detect-provider     Detect provider
  --approach APPROACH   Approach to use. Must be one of: ['dynamic-client']
  --dataset DATASET     dataset name.
  --variable VARIABLE   Zarr version. Must be one of: ['tasmax']
  --non-headless        Run in non-headless mode
  --s3-bucket S3_BUCKET
                        S3 bucket name
  --action ACTION       Action to perform. Must be one of: ['zoom_in', 'zoom_out']
  --zoom-level ZOOM_LEVEL
                        Zoom level
```

### Local

To run the benchmarks, you will need to install `playwright` and software packages specified in `binder/environment.yml`. This can be done by running the following commands:

```bash
# Create conda environment
conda env create -f binder/environment.yml

# Activate conda environment and install playwright browsers
conda activate benchmark-maps
playwright install
```

Once the environment is set up, you can run the benchmarks by running the following command:

```bash
carbonplan_benchmarks --dataset pyramids-v2-3857-True-128-1-0-0-f4-0-0-0-gzipL1-100 --action zoom_in --zoom-level 4
```

### Remote via Coiled

To run the benchmark using `coiled`, you can run the following command:

```bash
coiled run --gpu --container quay.io/carbonplan/benchmark-maps bash main.sh
```

## license

All the code in this repository is [Apache-2.0](https://choosealicense.com/licenses/apache-2.0/) licensed. When possible, the data used by this project is licensed using the [CC-BY-4.0](https://choosealicense.com/licenses/cc-by-4.0/) license. We include attribution and additional license information for third party datasets, and we request that you also maintain that attribution if using this data.

## about us

CarbonPlan is a non-profit organization that uses data and science for climate action. We aim to improve the transparency and scientific integrity of carbon removal and climate solutions through open data and tools. Find out more at [carbonplan.org](https://carbonplan.org/) or get in touch by [opening an issue](https://github.com/carbonplan/offsets-db/issues/new) or [sending us an email](mailto:hello@carbonplan.org).
