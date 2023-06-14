import xarray as xr
from cmip6_downscaling.methods.common.utils import validate_zarr_store
from ndpyramid import pyramid_regrid


def calc_chunk_dict(
    ds: xr.Dataset | xr.DataArray, target_mb: int, pixels_per_tile: int = None
) -> dict:
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
    if isinstance(ds, xr.Dataset):
        for var in ds.data_vars:
            data_bytesize = ds[var].dtype.itemsize
    else:
        data_bytesize = ds.dtype.itemsize
    if pixels_per_tile is None:
        slice_mb = ds.nbytes * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
    else:
        slice_mb = data_bytesize * pixels_per_tile * pixels_per_tile * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
        target_chunks['x'] = pixels_per_tile
        target_chunks['y'] = pixels_per_tile
    return target_chunks


def pyramid(
    ds_path: str, target: str, levels: int = 2, pixels_per_tile: int = 128, target_mb: int = 5
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

    Returns
    -------
    target : str
    '''

    ds = xr.open_zarr(ds_path)

    chunks = calc_chunk_dict(ds, target_mb=target_mb, pixels_per_tile=pixels_per_tile)

    other_chunks = {'time': chunks['time']}

    # create pyramid
    dta = pyramid_regrid(
        ds,
        levels=levels,
        pixels_per_tile=pixels_per_tile,
        other_chunks=other_chunks,
        regridder_kws={'ignore_degenerate': True},
    )

    # write to target
    for child in dta.children.values():
        for variable in child.ds.data_vars:
            child[variable].encoding['write_empty_chunks'] = True

    dta.to_zarr(target, mode='w')
    validate_zarr_store(target)
    return target
