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

To run the benchmarks, you will need to install `playwright` and software packages specified in `binder/environment.yml`. This can be done by running the following commands:

```bash
# Create conda environment
conda env update -f binder/environment.yml

# Activate conda environment and install playwright browsers
conda activate benchmark-maps
playwright install
```

Once the environment is set up, you can run the benchmarks by running the following command:

```bash
python main.py
```

To run the benchmark using `coiled`, you can run the following command:

```bash
coiled run --container quay.io/carbonplan/benchmark-maps --file main.py bash main.sh
```

## license

All the code in this repository is [Apache-2.0](https://choosealicense.com/licenses/apache-2.0/) licensed. When possible, the data used by this project is licensed using the [CC-BY-4.0](https://choosealicense.com/licenses/cc-by-4.0/) license. We include attribution and additional license information for third party datasets, and we request that you also maintain that attribution if using this data.

## about us

CarbonPlan is a non-profit organization that uses data and science for climate action. We aim to improve the transparency and scientific integrity of carbon removal and climate solutions through open data and tools. Find out more at [carbonplan.org](https://carbonplan.org/) or get in touch by [opening an issue](https://github.com/carbonplan/offsets-db/issues/new) or [sending us an email](mailto:hello@carbonplan.org).
