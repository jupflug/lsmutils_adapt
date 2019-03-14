from osgeo import gdal, gdal_array, ogr, osr
import numpy as np
import pandas as pd

#import mpl_toolkits.basemap as bm
#import matplotlib.pyplot as plt
#import matplotlib.colors as colors
#import matplotlib.patches as patches

import logging
from math import ceil, floor

from .utils import CoordProperty

class Dataset(object):

    def __init__(self, filepath):
        self.filepath = filepath

class DataFrameDataset(Dataset):

    def __init__(self, filepath, filetype='csv', **kwargs):
        self.filepath = filepath
        self.filetype = filetype
        self.csvargs = kwargs
        self._dataset = None
        
    @property
    def dataset(self):
        if self._dataset == None:
            self._dataset = pd.read_csv(self.filepath.path, **self.csvargs)
        return self._dataset

    def save(self):
        self.saveas('csv')
        
    def saveas(self, filetype, datatype=None):
        self.dataset.to_csv(self.filepath.ext[filetype], **csvargs)

class SpatialDataset():
    
    def __init__(self, ds_min, ds_max, padding=None):
        
        if not padding is None:
            ds_min = ds_min - padding
            ds_max = ds_max + padding
            
        self._min = ds_min
        self._max = ds_max
        self._resolution = None
        self._ul = None
        self._ur = None
        self._ll = None
        self._lr = None
        self._warp_output_bounds = None

    @property
    def min(self):
        return self._min

    @property
    def max(self):
        return self._max
    
    @property
    def ul(self):
        if not self._ul:
            self._ul = CoordProperty(x=self.min.x, y=self.max.y)
        return self._ul

    @property
    def ur(self):
        if not self._ur:
            self._ur = CoordProperty(x=self.max.x, y=self.max.y)
        return self._ur

    @property
    def ll(self):
        if not self._ll:
            self._ll = CoordProperty(x=self.min.x, y=self.min.y)
        return self._ll

    @property
    def lr(self):
        if not self._lr:
            self._lr = CoordProperty(x=self.max.x, y=self.min.y)
        return self._lr

    @property
    def warp_output_bounds(self):
        if not self._warp_output_bounds:
            self._warp_output_bounds = [self.min.x, self.min.y,
                                        self.max.x, self.max.y]
        return self._warp_output_bounds

    @property
    def rev_warp_output_bounds(self):
        if not self._rev_warp_output_bounds:
            self._rev_warp_output_bounds = [self.cmin.x, self.cmin.y,
                                            self.cmax.x, self.cmax.y]
        return self._rev_warp_output_bounds

    
class GDALDataset(SpatialDataset):

    filetypes = {
        'nc': 'netCDF',
        'asc': 'AAIGrid',
        'gtif': 'GTiff',
        'tif': 'GTiff'
    }
    
    def __init__(self, filepath, template=None, filetype='gtif'):
        self.filepath = filepath
        self.filetype = filetype
        self._dataset = None
        self._geotransform = None
        self._nodata = None
        self._datatype = None
        self._projection = None
        self._resolution = None
        self._size = None
        self._array = None
        self._masked = None
        self._min = None
        self._max = None
        self._cmin = None
        self._cmax = None
        self._cgrid = None
        self._center = None
        self._gridcorners = None
        self._grid = None
        self._ul = None
        self._ur = None
        self._ll = None
        self._lr = None
        self._warp_output_bounds = None
        self._rev_warp_output_bounds = None
        self.mod = gdal.GA_ReadOnly
        if template:
            driver = gdal.GetDriverByName('GTiff')
            self._dataset = driver.CreateCopy(filepath.path, template.dataset)
        
    @property
    def dataset(self):
        if self._dataset is None:
            if not hasattr(self.filepath, 'file_id'):
                gdal_path = self.filepath
            elif not self.filepath.netcdf_variable:
                gdal_path = self.filepath.path
            else:
                gdal_path = 'NETCDF:{path}:{variable}'.format(
                        path = self.filepath.path,
                        variable = self.filepath.netcdf_variable)
            self._dataset = gdal.Open(gdal_path, self.mod)
            
        if self._dataset is None:
            logging.warning('%s did not load as raster' % gdal_path)
            
        return self._dataset

    @dataset.setter
    def dataset(self, dataset):
        self.__init__(self.filename, filetype=self.filetype)
        self._dataset = dataset

    @dataset.deleter
    def dataset(self):
        self._dataset = None

    def save(self):
        self.saveas('gtif')
        
    def saveas(self, filetype, datatype=None):
        if datatype is None:
            datatype = self.datatype
        if filetype != self.filetype:
            gdal.Translate(self.filepath.ext(filetype),
                           self.dataset,
                           format=self.filetypes[filetype])
            logging.info('Translated to {ext} with datatype {dt}'.format(
                    ext=filetype, dt=datatype))
        return GDALDataset(self.filepath, filetype=filetype)

    def chmod(self, mod):
        if self.mod == mod:
            return self
        
        self.dataset.FlushCache()
        self._dataset = None
        self._dataset = gdal.Open(self.filepath.path, mod)
        if not self.dataset:
            logging.error('Dataset at %s did not load for writing',
                          self.filepath.path)
        self.mod = mod
        return self

    @property
    def geotransform(self):
        if not self._geotransform:
            self._geotransform = self.dataset.GetGeoTransform()
        return self._geotransform

    @property
    def srs(self):
        if not self._srs:
            self._srs = self.dataset.GetProjection()
        return self._srs

    @srs.setter
    def srs(self, new_espg):
        logging.debug('Trying projection {}'.format(self.espg))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(self.espg)
        self._dataset.SetProjection(srs.ExportToWkt())
        self._srs = srs

    @property
    def datatype(self):
        if not self._datatype:
            self._datatype=self.dataset.GetRasterBand(1).DataType
        return self._datatype
    
    @property
    def nodata(self):
        if not self._nodata:
            self._nodata = self.dataset.GetRasterBand(1).GetNoDataValue()
        return self._nodata

    @nodata.setter
    def nodata(self, new_nodata):
        try:
            self.chmod(gdal.GA_Update)
        except:
            logging.warning('Did not set no data value')
            return None
        old_nodata = self.nodata
        self.dataset.GetRasterBand(1).SetNoDataValue(new_nodata)
        array = self.array
        array[array==old_nodata] = new_nodata
        self.array = array
        self._masked = None
        self._dataset = None
        self._nodata = self.dataset.GetRasterBand(1).GetNoDataValue()
    
    @property
    def resolution(self):
        if not self._resolution:
            self._resolution = CoordProperty(x=abs(self.geotransform[1]),
                                             y=abs(self.geotransform[5]))
        return self._resolution

    @property
    def res(self):
        return self.resolution
    
    @property
    def array(self):
        if self._array is None:
            self._array = self.dataset.GetRasterBand(1).ReadAsArray()
            if self.geotransform[1] < 0:
                self._array = np.fliplr(self._array)
            if self.geotransform[5] < 0 :
                self._array = np.flipud(self._array)
        return self._array

    @array.setter
    def array(self, new_array):
        # Allow updates to the array
        self.chmod(gdal.GA_Update)

        # Deal with negative 'resolution' values
        if self.geotransform[1] < 0:
            new_array = np.fliplr(new_array)
        if self.geotransform[5] < 0 :
            new_array = np.flipud(new_array)

        # Set datatype to match the new array if necessary
        ds = self.dataset
        # GDAL doesn't have 64-bit integers
        if new_array.dtype == np.int64:
            new_array = new_array.astype(np.int32)
        new_dtype = gdal_array.NumericTypeCodeToGDALTypeCode(new_array.dtype)
        if not new_dtype == ds.GetRasterBand(1).DataType:
            geotransform = ds.GetGeoTransform()
            srs = ds.GetProjection()
            driver = ds.GetDriver()
            ds = driver.Create(self.filepath.path,
                               new_array.shape[1],
                               new_array.shape[0],
                               1, new_dtype)
            ds.SetGeoTransform(geotransform)
            ds.SetProjection(srs)
            
        ds.GetRasterBand(1).WriteArray(new_array)
        ds.FlushCache()
        self._dataset = ds
        self._array = None

    @property
    def masked(self):
        if self._masked is None:
            self._masked = np.ma.MaskedArray(
                    self.array, mask=self.array == self.nodata)
            np.ma.set_fill_value(self._masked, self.nodata)
        return self._masked

    @masked.setter
    def masked(self, new_ma):
        self.array = self.masked.filled()

    @property
    def size(self):
        if not self._size:
            shape = self.array.shape
            self._size = CoordProperty(x=shape[1], y=shape[0])
        return self._size

    @property
    def min(self):
        if not self._min:
            self.max
        return self._min

    @property
    def max(self):
        if not self._max:
            res_x = self.geotransform[1]
            res_y = self.geotransform[5]
            
            x_bounds = (self.geotransform[0] + res_x * self.size.x,
                        self.geotransform[0])
            y_bounds = (self.geotransform[3] + res_y * self.size.y,
                        self.geotransform[3])
            self._max = CoordProperty(x=max(x_bounds) + .5 * self.res.x,
                                      y=max(y_bounds) + .5 * self.res.y)
            self._min = CoordProperty(x=min(x_bounds) - .5 * self.res.x,
                                      y=min(y_bounds) - .5 * self.res.y)
        return self._max

    @property
    def cmax(self):
        if not self._cmax:
            res_x = self.geotransform[1]
            res_y = self.geotransform[5]
            
            x_bounds = (self.geotransform[0] + res_x * self.size.x,
                        self.geotransform[0])
            y_bounds = (self.geotransform[3] + res_y * self.size.y,
                        self.geotransform[3])
            self._cmax = CoordProperty(x=max(x_bounds), y=max(y_bounds))
            self._cmin = CoordProperty(x=min(x_bounds), y=min(y_bounds))
        return self._cmax

    @property
    def cmin(self):
        if not self._cmin:
            self.cmax
        return self._cmin
            
    @property
    def grid(self):
        if self._grid is None:
            xgrid = np.linspace(self.min.x + .5 * self.res.x,
                                self.max.x - .5 * self.res.x,
                                self.size.x + 1)
            ygrid = np.linspace(self.min.y + .5 * self.res.y,
                                self.max.y - .5 * self.res.y,
                                self.size.y + 1)
            self._grid = CoordProperty(x=xgrid, y=ygrid)
        return self._grid

    @property
    def cgrid(self):
        if self._cgrid is None:
            xgrid = np.linspace(self.cmin.x + .5 * self.res.x,
                                self.cmax.x - .5 * self.res.x,
                                self.size.x)
            ygrid = np.linspace(self.cmin.y + .5 * self.res.y,
                                self.cmax.y - .5 * self.res.y,
                                self.size.y)
            self._cgrid = CoordProperty(x=xgrid, y=ygrid)
        return self._cgrid

    def gridmin(self, res):
        return self.min.grid_coord(res, method=floor)

    def gridmax(self, res):
        return self.max.grid_coord(res, method=ceil)

    def gridcmin(self, res):
        return self.cmin.grid_coord(res, method=floor)

    def gridcmax(self, res):
        return self.cmax.grid_coord(res, method=ceil)

    def gridcorners(self, res, padding=None):
        return SpatialDataset(
                ds_min=self.gridcmin(res),
                ds_max=self.gridcmax(res),
                padding=padding)
    
    @property
    def center(self):
        if not self._center:
            self._center = (self.max - self.min) / 2.
        return self._center


    def plot(self, title, uri, boundary_ds=None, outlet_ds=None,
             show=True, padding=1/240., quiver=False, colorlog=False,
             cmap='RdBu_r', **kwargs):
        fig = plt.figure()

        # Clip plot to boundary if given or to raster extent if not
        #if not boundary_ds is None:
            # Basemap requires epsg:4326 - reproject if necessary
        """
            wgs84srs = osr.SpatialReference().ImportFromEPSG(4326)
            layer = boundary_ds.dataset.GetLayer()
            srs = layer.GetSpatialRef()
            if not srs == wgs84srs:
                new_ds = driver.CreateDataSource()
                transform = osr.CoordinateTransformation(srs, wgs84srs)
                new_layer = 
                feature = layer.GetNextFeature()
                while feature:
                    geom = feature.GetGeometryRef()
                    geom.Transform(transform)
                    new_feature = ogr.Feature(
        """
        #    corners = boundary_ds.gridcorners(CoordProperty(x=1/16., y=1/16.))
        #else:
        corners = Dataset(ds_min=self.cmin, ds_max = self.cmax)
        basemap = bm.Basemap(
                llcrnrlon = corners.ll.lon - padding,
                llcrnrlat = corners.ll.lat - padding,
                urcrnrlon = corners.ur.lon + padding,
                urcrnrlat = corners.ur.lat + padding,
                resolution = 'i')

        # Overlay watershed boundary and outlet if given
        #if not boundary_ds is None:
        #    basemap.readshapefile(boundary_ds.filepath.no_ext, 'watershed')
        if not outlet_ds is None:
            basemap.readshapefile(outlet_ds.filepath.no_ext, 'outlet')

        # Add bounding box rectangle
        bb_rect = patches.Polygon(
                [corners.ul.coord, corners.ur.coord,
                 corners.lr.coord, corners.ll.coord],
                facecolor='none', edgecolor='black')
        plt.gca().add_patch(bb_rect)

        # Print dataset information
        logging.debug('geotransform: {}'.format(self.geotransform))
        logging.debug('resolution x: {}, y: {}'.format(self.res.x, self.res.y))
        logging.debug('min x: {}, min y: {}'.format(self.min.x, self.min.y))
        logging.debug('max x: {}, max y: {}'.format(self.max.x, self.max.y))
        logging.debug('ll x: {}, ll y: {}'.format(
                corners.ll.lon, corners.ll.lat))
        logging.debug('ur x: {}, ur y: {}'.format(
                corners.ur.lon, corners.ur.lat))

        # Draw and label parallels and meridians
        parallels = np.linspace(
                floor(corners.min.lat), ceil(corners.max.lat), 5)
        basemap.drawparallels(parallels, labels=[True, False, False, True])
        meridians = np.linspace(
                floor(corners.min.lon), ceil(corners.max.lon), 5)
        basemap.drawmeridians(meridians, labels=[True, False, False, True])
        
        # Mask raster array at nodata locations
        z = self.array
        z = np.ma.masked_where(z==self.nodata, z)

        # Modify normalization for log color scale
        if colorlog:
            norm = colors.LogNorm(vmin=z.min(), vmax=z.max())
        else:
            norm = None

        # Plot grid cells
        lon, lat = np.meshgrid(self.grid.lon, self.grid.lat)
        im = basemap.pcolormesh(lon, lat, z, cmap=cmap, latlon=True,
                                rasterized=True, norm=norm, **kwargs)
        basemap.colorbar(im)

        # Add arrows for quiver plot
        if quiver:
            lon, lat = np.meshgrid(self.cgrid.lon, self.cgrid.lat)
            u = np.cos((3 - z) / 4. * np.pi)
            v = np.sin((3 - z) / 4. * np.pi)
            basemap.quiver(lon, lat, u, v, latlon=True, scale=50)

        # Add title
        plt.title(title)

        # Save and show
        plt.savefig(uri, dpi=100)
        if show:
            plt.show()
            
        return basemap

class BoundaryDataset(SpatialDataset):
    def __init__(self, filepath, update=False, driver='ESRI Shapefile'):
        self.filepath = filepath
        self.update = update
        self.driver = driver
        self._dataset = None
        self._layers = None
        self._srs = None
        self._min = None
        self._max = None
        self._ul = None
        self._ur = None
        self._ll = None
        self._lr = None

    def new(self):
        driver = ogr.GetDriverByName(self.driver)
        self._dataset = driver.CreateDataSource(self.filepath.path)
        return self
        
    @property
    def dataset(self):
        if self._dataset is None:
            self._dataset = ogr.Open(self.filepath.path, update=self.update)
        if self._dataset is None:
            logging.debug('Dataset at %s did not load as shapefile',
                          self.filepath.shp)
        return self._dataset

    @dataset.deleter
    def dataset(self):
        self._dataset = None

    @property
    def layers(self):
        if not self._layers:
            self._layers = []
            n = self.dataset.GetLayerCount()
            for i in range(0, n):
                self._layers.append(self.dataset.GetLayerByIndex(i))
        return self._layers
    
    @property
    def min(self):
        if not self._min:
            layer = self.dataset[0]
            (minx, maxx, miny, maxy) = layer.GetExtent()
            self._min = CoordProperty(x=minx, y=miny)
            self._max = CoordProperty(x=maxx, y=maxy)
        return self._min

    @property
    def max(self):
        if not self._max:
            self.min
        return self._max

    def gridmin(self, res):
        return self.min.grid_coord(res, method=floor)

    def gridmax(self, res):
        return self.max.grid_coord(res, method=ceil)

    def gridcorners(self, res, padding=None):
        return Dataset(ds_min=self.gridmin(res), ds_max=self.gridmax(res),
                       padding=padding)

    def chmod(self, update):
        self.update = update
        self._dataset = None

    def plot(self, *args, **kwargs):
        pass
        

