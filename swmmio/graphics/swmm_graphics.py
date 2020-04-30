# graphical functions for SWMM files
import pandas as pd

from swmmio.defs.config import REPORT_DIR_NAME, BETTER_BASEMAP_PATH
from swmmio.graphics import config
from swmmio.defs.constants import white
from swmmio.graphics.utils import px_to_irl_coords, save_image
from swmmio.graphics.drawing import (annotate_streets, annotate_title, annotate_details, annotate_timestamp,
                                     draw_conduit, draw_node)
from swmmio.utils import spatial

import os
from PIL import Image, ImageDraw

from swmmio.version_control.inp import INPSectionDiff


def _draw_basemap(draw, img, bbox, px_width, shift_ratio):
    """
    given the shapefiles in config.basemap_options, render each layer
    on the model basemap.
    """

    for f in config.basemap_options['features']:

        shp_path = os.path.join(config.basemap_shapefile_dir, f['feature'])
        df = spatial.read_shapefile(shp_path)[f['cols'] + ['coords']]
        df = px_to_irl_coords(df, bbox=bbox, shift_ratio=shift_ratio,
                              px_width=px_width)[0]

        if 'ST_NAME' in df.columns:
            # this is a street, draw a polyline accordingly
            df.apply(lambda r: draw.line(r.draw_coords, fill=f['fill']), axis=1)
            annotate_streets(df, img, 'ST_NAME')
        else:
            df.apply(lambda r: draw.polygon(r.draw_coords,
                                            fill=f['fill']), axis=1)


def draw_model(model=None, nodes=None, conduits=None, parcels=None, title=None,
               annotation=None, file_path=None, bbox=None, px_width=2048.0):
    """create a png rendering of the model and model results.

    A swmmio.Model object can be passed in independently, or Pandas Dataframes
    for the nodes and conduits of a model may be passed in. A dataframe containing
    parcel data can optionally be passed in.

    model -> swmmio.Model object

    nodes -> Pandas Dataframe (optional, if model not provided)

    conduits -> Pandas Dataframe (optional, if model not provided)

    parcels - > Pandas Dataframe (optional)

    title -> string, to be written in top left of PNG

    annotation -> string, to be written in bottom left of PNG

    file_path -> stirng, file path where png should be drawn. if not specified,
        a PIL Image object is return (nice for IPython notebooks)

    bbox -> tuple of coordinates representing bottom left and top right corner
        of a bounding box. the rendering will be clipped to this box. If not
        provided, the rendering will clip tightly to the model extents
        e.g. bbox = ((2691647, 221073),    (2702592, 227171))

        Note: this hasn't been tested with anything other than PA StatePlane coords

    px_width -> float, width of image in pixels
    """

    # gather the nodes and conduits data if a swmmio Model object was passed in
    if model is not None:
        nodes = model.nodes()
        conduits = model.conduits()

    # antialias X2
    xplier = 1
    xplier *= px_width / 1024  # scale the symbology sizes
    px_width = px_width * 2

    # compute draw coordinates, and the image dimensions (in px)
    conduits, bb, h, w, shift_ratio = px_to_irl_coords(conduits, bbox=bbox, px_width=px_width)
    nodes = px_to_irl_coords(nodes, bbox=bb, px_width=px_width)[0]

    # create the PIL image and draw objects
    img = Image.new('RGB', (w, h), white)
    draw = ImageDraw.Draw(img)

    # draw the basemap if required
    if config.include_basemap is True:
        _draw_basemap(draw, img, bb, px_width, shift_ratio)

    if parcels is not None:
        # expects dataframe with coords and draw color column
        par_px = px_to_irl_coords(parcels, bbox=bb, shift_ratio=shift_ratio, px_width=px_width)[0]
        par_px.apply(lambda r: draw.polygon(r.draw_coords, fill=r.draw_color), axis=1)

    # start the draw fest, mapping draw methods to each row in the dataframes
    conduits.apply(lambda row: draw_conduit(row, draw), axis=1)
    nodes.apply(lambda row: draw_node(row, draw), axis=1)

    # ADD ANNOTATION AS NECESSARY
    if title:
        annotate_title(title, draw)
    if annotation:
        annotate_details(annotation, draw)
    annotate_timestamp(draw)

    # SAVE IMAGE TO DISK
    if file_path:
        save_image(img, file_path)

    return img


def create_map(model1, model2=None, bbox=None, crs=None, filename=None,
               subset=None, return_data=False):
    """
    export model as a geojson object
    """

    import geojson
    from geojson import LineString, FeatureCollection
    # try:
    #     import pyproj
    # except ImportError:
    #     raise ImportError('pyproj module needed. get this package here: ',
    #                       'https://pypi.python.org/pypi/pyproj')

    if model2 is not None:
        changes = INPSectionDiff(model1, model2, section='CONDUITS')
        df = pd.concat([changes.added, changes.altered])
        subset = df.index.tolist()

    # links2 = model2.links.
    # else:
    #     model2 = model1 #stupid, for file path

    # geometries = []  # array of features
    # # collect the links
    # for k, v in list(model2.list_objects('conduit', bbox, subset=subset).items()):
    #     props = {
    #         'MaxQPercent': v.maxQpercent,
    #         'id': v.id,
    #         'lifecycle': v.lifecycle,
    #         'geom1': v.geom1,
    #         'geom2': v.geom2,
    #     }
    #
    #     latlngs = [pyproj.transform(pa_plane, wgs, *xy) for xy in v.coordinates]
    #     geometry = LineString(latlngs, properties=props)
    #     geometries.append(geometry)

    if return_data is True:
        return model2.links.geojson

    if filename is None:
        filename = os.path.join(model2.inp.dir,
                                REPORT_DIR_NAME,
                                model2.name + '.html')

    # start writing that thing
    with open(BETTER_BASEMAP_PATH, 'r') as bm:
        with open(filename, 'w') as newmap:
            for line in bm:
                if 'INSERT GEOJSON HERE' in line:
                    newmap.write(f'conduits = {geojson.dumps(model2.links.geojson)}\n')
                    newmap.write(f'nodes = {geojson.dumps(model2.nodes.geojson)}\n')
                else:
                    newmap.write(line)
