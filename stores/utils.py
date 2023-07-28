import rioxarray  # noqa
import xarray as xr
from carbonplan_data.utils import set_zarr_encoding as set_web_zarr_encoding
from ndpyramid import pyramid_reproject


def calc_chunk_dict(ds: xr.Dataset, target_mb: int, pixels_per_tile: int) -> dict:
    """Calculate chunks sizes for uncompressed chunks to match target size.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset that will be chunked.
    target_mb : int
        Target chunk size in MB.
    pixels_per_tile : int
        Chunk size for 'x' and 'y' dims.

    Returns
    -------
    target_chunks : dict
    """
    data_bytesize = next(iter(ds.data_vars.values())).dtype.itemsize
    if pixels_per_tile is None:
        slice_mb = ds.nbytes * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
    else:
        slice_mb = data_bytesize * pixels_per_tile * pixels_per_tile * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
        if target_chunks['time'] > ds.sizes['time']:
            target_chunks['time'] = ds.sizes['time']
        target_chunks['x'] = pixels_per_tile
        target_chunks['y'] = pixels_per_tile
    return target_chunks


def pyramid(
    ds_path: str,
    *,
    target: str,
    levels: int = 2,
    pixels_per_tile: int = 128,
    target_mb: int = 5,
    projection: str = 'web-mercator',
) -> str:
    '''Create a data pyramid from an xarray Dataset

    Based on https://github.com/carbonplan/cmip6-downscaling

    Parameters
    ----------
    ds_path : UPath
        Path to input dataset
    target : str
        Path to write output data pyamid to
    levels : int, optional
        Number of levels in pyramid, by default 2
    pixels_per_tile : int, optional
        Number of pixels along x and y per tile, by default 128
    target_mb : int, optional
        Target size in MB for each chunk; used to define chunking along time dimension, by default 5 MB

    Returns
    -------
    target : str
    '''

    ds = xr.open_zarr(ds_path, chunks={}).rio.write_crs('EPSG:4326')

    calc_chunk_dict(ds, target_mb=target_mb, pixels_per_tile=pixels_per_tile)

    # other_chunks = {'time': chunks['time']}
    other_chunks = {'time': 10}
    print(f'creating pyramids from {ds_path}...')

    # create pyramid
    dta = pyramid_reproject(
        ds,
        levels=levels,
        pixels_per_tile=pixels_per_tile,
        other_chunks=other_chunks,
        projection=projection,
    )

    print('setting metadata...')
    # set encoding
    for child in dta.children:
        dta[child].ds = set_web_zarr_encoding(
            dta[child].ds,
            codec_config={'id': 'gzip', 'level': 1},
            float_dtype='float32',
            int_dtype='int32',
        )
        for var in ['time', 'time_bnds']:
            if var in dta[child].ds:
                dta[child].ds[var].encoding['dtype'] = 'int32'

    # write to zarr
    print(f'writing to {target}...')
    dta.to_zarr(target, mode='w')
    return target
