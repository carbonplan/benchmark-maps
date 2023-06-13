import datatree as dt
import xarray as xr
import zarr
from carbonplan_data.utils import set_zarr_encoding as set_web_zarr_encoding
from ndpyramid import pyramid_regrid


def calc_chunk_dict(ds: xr.Dataset, target_mb: int, pixels_per_tile: int = None) -> dict:
    """Calculate chunks that for uncompressed chunks to match target size.

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
    for var in ds.data_vars:
        data_bytesize = ds[var].dtype.itemsize
    if pixels_per_tile is None:
        slice_mb = ds.nbytes * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
    else:
        slice_mb = data_bytesize * pixels_per_tile * pixels_per_tile * 1e-6
        target_chunks = {'time': int(target_mb // slice_mb)}
        target_chunks['x'] = pixels_per_tile
        target_chunks['y'] = pixels_per_tile
    return target_chunks


def validate_zarr_store(target: str, raise_on_error=True) -> bool:
    """Validate a zarr store.

    Based on https://github.com/carbonplan/cmip6-downscaling

    Parameters
    ----------
    target : str
        Path to zarr store.
    raise_on_error : bool
        Flag to turn on/off raising when the store is not valid. If `False`, the function will return
        `True` when the store is valid (complete) and `False` when the store is not valid.

    Returns
    -------
    valid : bool
    """
    errors = []

    try:
        store = zarr.open_consolidated(target)
    except:  # noqa
        errors.append('error opening zarr store')

    if not errors:
        groups = list(store.groups())
        # if groups is empty (not a datatree)
        if not groups:
            groups = [('root', store['/'])]

        for key, group in groups:
            data_group = group

            variables = list(data_group.keys())
            for variable in variables:
                variable_array = data_group[variable]
                if variable_array.nchunks_initialized != variable_array.nchunks:
                    errors.append(
                        f'{variable} has {variable_array.nchunks - variable_array.nchunks_initialized} uninitialized chunks'
                    )

    if errors:
        if raise_on_error:
            raise ValueError(f'Found {len(errors)} errors: {errors}')
        return False
    return True


def _pyramid_postprocess(
    dt: dt.DataTree, levels: int, chunks: dict, pixels_per_tile: int
) -> dt.DataTree:
    '''Postprocess data pyramid

    Adds multiscales metadata and sets Zarr encoding

    Based on https://github.com/carbonplan/cmip6-downscaling

    Parameters
    ----------
    dt : dt.DataTree
        Input data pyramid
    levels : int
        Number of levels in pyramid
    chunks : dict
        Chunks for dims

    Returns
    -------
    dt.DataTree
        Updated data pyramid with metadata / encoding set
    '''

    for level in range(levels):
        slevel = str(level)
        dt.ds.attrs['multiscales'][0]['datasets'][level]['pixels_per_tile'] = pixels_per_tile

        # set dataset chunks
        dt[slevel].ds = dt[slevel].ds.chunk(chunks)

        # set dataset encoding
        dt[slevel].ds = set_web_zarr_encoding(
            dt[slevel].ds, codec_config={'id': 'zlib', 'level': 1}, float_dtype='float32'
        )
        for var in ['time', 'time_bnds']:
            if var in dt[slevel].ds:
                dt[slevel].ds[var].encoding['dtype'] = 'int32'

    # set global metadata
    dt.ds.attrs.update({'title': 'multiscale data pyramid'})
    return dt


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

    dta = _pyramid_postprocess(dta, levels=levels, chunks=chunks, pixels_per_tile=pixels_per_tile)

    # write to target
    for child in dta.children.values():
        for variable in child.ds.data_vars:
            child[variable].encoding['write_empty_chunks'] = True

    dta.to_zarr(target, mode='w')
    validate_zarr_store(target)
    return target
