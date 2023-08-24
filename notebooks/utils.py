import rioxarray  # noqa
import xarray as xr
from carbonplan_data.utils import set_zarr_encoding as set_web_zarr_encoding
from ndpyramid import pyramid_reproject
import numpy as np


def calc_shard_size(arr: np.ndarray, *, chunks: tuple, target_mb: int, orientation: str) -> tuple:
    """Calculate shard sizes for uncompressed shards to match target size.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset that will be sharded.
    target_mb : int
        Target shard size in MB.
    chunks : tuple
        Chunk size for 'time, 'x', and 'y' dims.
    orientation: str
        Whether chunks should be grouped into shards primarily in space, time, or both.

    Returns
    -------
    target_shards : tuple
    """
    chunk_size = arr[: chunks[0], : chunks[1], : chunks[2]].nbytes * 1e-6
    if orientation == 'space':
        time_shard = chunks[0]
        x_shard = y_shard = chunks[1]
        shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size <= (target_mb - chunk_size)) and (x_shard <= (arr.shape[1] - chunks[1])):
            x_shard += chunks[1]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size * 1e-6 <= (target_mb - shard_size)) and (
            y_shard <= (arr.shape[1] - chunks[1])
        ):
            y_shard += chunks[1]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
    elif orientation == 'time':
        x_shard = y_shard = chunks[1]
        time_shard = chunks[0]
        shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size <= (target_mb - chunk_size)) and (
            time_shard <= (arr.shape[0] - chunks[0])
        ):
            time_shard += chunks[0]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
    elif orientation == 'both':
        x_shard = y_shard = chunks[1]
        time_shard = chunks[0]
        shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size <= (target_mb - chunk_size)) and (x_shard <= (arr.shape[1] - chunks[1])):
            x_shard += chunks[1]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size * 1e-6 <= (target_mb - shard_size)) and (
            y_shard <= (arr.shape[1] - chunks[1])
        ):
            y_shard += chunks[1]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
        while (shard_size <= (target_mb - shard_size)) and (
            time_shard <= (arr.shape[0] - chunks[0])
        ):
            time_shard += chunks[0]
            shard_size = arr[:time_shard, :x_shard, :y_shard].nbytes * 1e-6
    else:
        raise ValueError("Orientation must be either 'space' or 'time'")
    return (time_shard, x_shard, y_shard)


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
        time_chunk = int(target_mb // slice_mb)
        while (ds.sizes['time'] % time_chunk) > 0:
            time_chunk -= 1
        target_chunks = {'time': time_chunk}
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
    extra_attrs: dict = None,
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
    projection : str
        Projection for pyramids
    extra_attrs: dict
        Extra attrs to include in metadata


    Returns
    -------
    target : str
        URI for Zarr store containing pyramids
    '''

    ds = xr.open_zarr(ds_path, chunks={}).rio.write_crs('EPSG:4326')

    chunks = calc_chunk_dict(ds, target_mb=target_mb, pixels_per_tile=pixels_per_tile)

    other_chunks = {'time': chunks['time']}
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

    extra_attrs['target_mb'] = target_mb
    extra_attrs['projection'] = projection
    extra_attrs['pixels_per_tile'] = pixels_per_tile
    dta.attrs['config'] = extra_attrs

    # write to zarr
    print(f'writing to {target}...')
    dta.to_zarr(target, mode='w')
    return target
