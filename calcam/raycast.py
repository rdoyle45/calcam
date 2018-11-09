'''
* Copyright 2015-2018 European Atomic Energy Community (EURATOM)
*
* Licensed under the EUPL, Version 1.1 or - as soon they
  will be approved by the European Commission - subsequent
  versions of the EUPL (the "Licence");
* You may not use this work except in compliance with the
  Licence.
* You may obtain a copy of the Licence at:
*
* https://joinup.ec.europa.eu/software/page/eupl
*
* Unless required by applicable law or agreed to in
  writing, software distributed under the Licence is
  distributed on an "AS IS" basis,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
  express or implied.
* See the Licence for the specific language governing
  permissions and limitations under the Licence.
'''

""" 
Ray tracing tools for CalCam_py

Written by Scott Silburn
2015-05-17
"""


import vtk
import numpy as np
import datetime
import time
import sys
import os
from . import coordtransformer
from scipy.io.netcdf import netcdf_file
import random




def raycast_sightlines(calibration,cadmodel,x=None,y=None,binning=1,coords='Display',verbose=True,force_subview=None):

    if not verbose:
        original_callback = cadmodel.get_status_callback()
        cadmodel.set_status_callback(None)


    # Work out how big the model is. This is to make sure the rays we cast aren't too short.
    model_extent = cadmodel.get_extent()
    model_size = model_extent[1::2] - model_extent[::2]
    max_ray_length = model_size.max() * 4
    
    if verbose:
        sys.stdout.write('Getting CAD model octree...')

    # Get the CAD model's octree
    cell_locator = cadmodel.get_cell_locator()

    if verbose:
        sys.stdout.write('Done.\n')


    # If no pixels are specified, do the whole chip at the specified binning level.
    fullchip = False
    if x is None and y is None:
        fullchip = True
        if coords.lower() == 'display':
            shape = calibration.geometry.get_display_shape()
            xl = np.linspace( (binning-1.)/2,float(shape[0]-1)-(binning-1.)/2,(1+float(shape[0]-1))/binning)
            yl = np.linspace( (binning-1.)/2,float(shape[1]-1)-(binning-1.)/2,(1+float(shape[1]-1))/binning)
            x,y = np.meshgrid(xl,yl)
        else:
            shape = calibration.geometry.get_original_shape()
            xl = np.linspace( (binning-1.)/2,float(shape[0]-1)-(binning-1.)/2,(1+float(shape[0]-1))/binning)
            yl = np.linspace( (binning-1.)/2,float(shape[1]-1)-(binning-1.)/2,(1+float(shape[1]-1))/binning)
            x,y = np.meshgrid(xl,yl)
            x,y = calibration.geometry.original_to_display_coords(x,y)
        valid_mask = np.ones(x.shape,dtype=bool)
    elif x is None or y is None:
        raise ValueError('Either both or none of x and y pixel coordinates must be given!')
    else:

        if np.array(x).ndim == 0:
            x = np.array([x])
        else:
            x = np.array(x)
   		
        if np.array(y).ndim == 0:
            y = np.array([y])
        else:
            y = np.array(y)
   	
        if x.shape != y.shape:
            raise ValueError('x and y arrays must be the same shape!')
        valid_mask = np.logical_and(np.isnan(x) == 0 , np.isnan(y) == 0 )
        if coords.lower() == 'original':
            x,y = calibration.geometry.original_to_display_coords(x,y)

    results = RayData()
    results.fullchip = fullchip
    results.x = np.copy(x).astype('float')
    results.x[valid_mask == 0] = 0
    results.y = np.copy(y).astype('float')
    results.y[valid_mask == 0] = 0
    results.transform = calibration.geometry

    orig_shape = np.shape(results.x)
    results.x = np.reshape(results.x,np.size(results.x),order='F')
    results.y = np.reshape(results.y,np.size(results.y),order='F')
    valid_mask = np.reshape(valid_mask,np.size(valid_mask),order='F')
    totpx = np.size(results.x)


    # New results object to store results
    if fullchip:
        results.binning = binning
    else:
        results.binning = None


    results.ray_end_coords = np.ndarray([np.size(x),3])

    # Line of sight directions
    LOSDir = calibration.get_los_direction(results.x,results.y,coords='Display',subview=force_subview)
    if len(LOSDir.shape) == 1:
        LOSDir = [LOSDir]
    results.ray_start_coords = calibration.get_pupilpos(results.x,results.y,coords='Display',subview=force_subview)

    
    if verbose:
        now = datetime.datetime.now()
        print(datetime.datetime.now().strftime('Started casting {:d} rays at %Y-%m-%d %H:%M'.format(np.size(x))))


    # Some variables to give to VTK becasue of its annoying C-like interface
    t = vtk.mutable(0)
    pos = np.zeros(3)
    coords_ = np.zeros(3)
    subid = vtk.mutable(0)

    starttime = time.time()
    etime_printed = False
    n_done = 0
    
    # We will do the ray casting in a random order,
    # purely to get better time remaining estimation.
    inds = list(range(np.size(x)))
    random.shuffle(inds)
    
    for ind in inds:

        if not valid_mask[ind]:
            results.ray_end_coords[ind,:] = np.nan
            results.ray_start_coords[ind,:] = np.nan
            continue

        # Do the raycast and put the result in the output array
        rayend = results.ray_start_coords[ind] + max_ray_length * LOSDir[ind]
        retval = cell_locator.IntersectWithLine(results.ray_start_coords[ind],rayend,1.e-6,t,pos,coords_,subid)

        if abs(retval) > 0:
            results.ray_end_coords[ind,:] = pos[:]
        else:
            results.ray_end_coords[ind,:] = rayend

        n_done = n_done + 1
        # Progress printing stuff
        if verbose and not etime_printed:
            if time.time() - starttime > 10:
                est_time = (time.time() - starttime) / n_done * np.size(x)
                if est_time > 15:
                    est_time_string = ''
                    if est_time > 3600:
                        est_time_string = est_time_string + '{:.0f} hr '.format(np.floor(est_time/3600))
                    if est_time > 600:
                        est_time_string = est_time_string + '{:.0f} min.'.format((est_time - 3600*np.floor(est_time/3600))/60)
                    elif est_time > 60:
                        est_time_string = est_time_string + '{:.0f} min {:.0f} sec.'.format(np.floor(est_time/60),est_time % 60)
                    else:
                        est_time_string ='{:.0f} sec.'.format(est_time)

                    print('Estimated calculation time: ' + est_time_string)
                etime_printed = True

    if verbose:
        tot_time = time.time() - starttime
        time_string = ''
        if tot_time > 3600:
            time_string = time_string + '{0:.0f} hr '.format(np.floor(tot_time / 3600))
        if tot_time > 60:
            time_string = time_string + '{0:.0f} min '.format(np.floor( (tot_time - 3600*np.floor(tot_time / 3600))  / 60))
        time_string = time_string + '{0:.0f} sec. '.format( tot_time - 60*np.floor(tot_time / 60) )

        print('Finished casting {:d} rays in '.format(np.size(x)) + time_string)

    results.x[valid_mask == 0] = np.nan
    results.y[valid_mask == 0] = np.nan

    results.ray_end_coords = np.reshape(results.ray_end_coords,orig_shape + (3,),order='F')
    results.ray_start_coords = np.reshape(results.ray_start_coords,orig_shape + (3,),order='F')
    results.x = np.reshape(results.x,orig_shape,order='F')
    results.y = np.reshape(results.y,orig_shape,order='F')

    if not verbose:
        cadmodel.set_status_callback(original_callback)

    return results


def check_visible(start_coords,target,cadmodel,verbose=False,tol=1e-3):

    start_coords = np.array(start_coords)
    target = np.array(target)

    # Work out how big the model is. This is to make sure the rays we cast aren't too short.
    model_extent = cadmodel.get_extent()
    model_size = model_extent[1::2] - model_extent[::2]
    max_ray_length = model_size.max() * 4
    
    if verbose:
        sys.stdout.write('Getting CAD model octree...')

    # Get the CAD model's octree
    cell_locator = cadmodel.get_cell_locator()

    if verbose:
        sys.stdout.write('Done.\n')


    # Line of sight directions
    LOSDir = target - start_coords
    LOSDir = LOSDir / np.sqrt(np.sum(LOSDir**2))



    # Some variables to give to VTK becasue of its annoying C-like interface
    t = vtk.mutable(0)
    pos = np.zeros(3)
    coords_ = np.zeros(3)
    subid = vtk.mutable(0)


    # Do the raycast
    rayend = start_coords + LOSDir*max_ray_length
    retval = cell_locator.IntersectWithLine(start_coords,rayend,1.e-6,t,pos,coords_,subid)

    if abs(retval) > 0:
        hit_coords = pos
    else:
        return True

    target_vect = target - start_coords
    hit_vect = hit_coords - start_coords

    if np.sqrt(np.sum(hit_vect**2)) > np.sqrt(np.sum(target_vect**2)) - tol:
        return True
    else:
        return False


# Class for storing ray data
class RayData:
    def __init__(self,filename=None):
        self.ray_end_coords = None
        self.ray_start_coords = None
        self.binning = None
        self.transform = None
        self.fullchip = None
        self.x = None
        self.y = None
        if filename is not None:
            self.load(filename)


    # Save to a netCDF file
    def save(self,filename):
		
        if not filename.endswith('.nc'):
            filename = filename + '.nc'
			
        f = netcdf_file(filename,'w')
        setattr(f,'history','CalCam_py output file')
        setattr(f,'image_transform_actions',"['" + "','".join(self.transform.transform_actions) + "']")

        pointdim = f.createDimension('pointdim',3)

        if len(self.x.shape) == 2:
            udim = f.createDimension('udim',self.x.shape[1])
            vdim = f.createDimension('vdim',self.x.shape[0])
            rayhit = f.createVariable('RayEndCoords','f4',('vdim','udim','pointdim'))
            raystart = f.createVariable('RayStartCoords','f4',('vdim','udim','pointdim'))
            x = f.createVariable('PixelXLocation','i4',('vdim','udim'))
            y = f.createVariable('PixelYLocation','i4',('vdim','udim'))
            
            rayhit[:,:,:] = self.ray_end_coords
            raystart[:,:,:] = self.ray_start_coords
            x[:,:] = self.x
            y[:,:] = self.y
        elif len(self.x.shape) == 1:
            udim = f.createDimension('udim',self.x.size)
            rayhit = f.createVariable('RayEndCoords','f4',('udim','pointdim'))
            raystart = f.createVariable('RayStartCoords','f4',('udim','pointdim'))
            x = f.createVariable('PixelXLocation','i4',('udim',))
            y = f.createVariable('PixelYLocation','i4',('udim',))

            rayhit[:,:] = self.ray_end_coords
            raystart[:,:] = self.ray_start_coords

            x[:] = self.x
            y[:] = self.y
        else:
            raise Exception('Cannot save RayData with >2D x and y arrays!')

        binning = f.createVariable('Binning','i4',())

        if self.binning is not None:
            binning.assignValue(self.binning)
        else:
            binning.assignValue(0)

        pixelsdim = f.createDimension('pixelsdim',2)

        xpx = f.createVariable('image_original_shape','i4',('pixelsdim',))
        xpx[:] = [self.transform.x_pixels,self.transform.y_pixels]

        pixelaspect = f.createVariable('image_original_pixel_aspect','f4',())
        pixelaspect.assignValue(self.transform.pixel_aspectratio)

        binning.units = 'pixels'
        raystart.units = 'm'
        rayhit.units = 'm'
        x.units = 'pixels'
        y.units = 'pixels'
        f.close()


    # Load from a netCDF file
    def load(self,filename):
        f = netcdf_file(filename, 'r',mmap=False)
        self.ray_end_coords = f.variables['RayEndCoords'].data
        self.ray_start_coords = f.variables['RayStartCoords'].data
        self.binning = f.variables['Binning'].data
        if self.binning == 0:
            self.binning = None
            self.fullchip = False
        else:
            self.fullchip = True

        self.x = f.variables['PixelXLocation'].data
        self.y = f.variables['PixelYLocation'].data

        self.transform = coordtransformer.CoordTransformer()
        self.transform.set_transform_actions(eval(f.image_transform_actions))
        self.transform.x_pixels = f.variables['image_original_shape'][0]
        self.transform.y_pixels = f.variables['image_original_shape'][1]
        self.transform.pixel_aspectratio = f.variables['image_original_pixel_aspect'].data

        f.close()

    # Return array of the sight-line length for each pixel.
    def get_ray_lengths(self,x=None,y=None,PositionTol = 3,Coords='Display'):

        # Work out ray lengths for all raytraced pixels
        RayLength = np.sqrt(np.sum( (self.ray_end_coords - self.ray_start_coords) **2,axis=-1))
        # If no x and y given, return them all
        if x is None and y is None:
            if self.fullchip:
                if Coords.lower() == 'display':
                    return RayLength
                else:
                    return self.transform.display_to_original_image(RayLength,binning=self.binning)
            else:
                return RayLength
        else:
            if self.x is None or self.y is None:
                raise Exception('This ray data does not have x and y pixel indices!')

            # Otherwise, return the ones at given x and y pixel coords.
            if np.shape(x) != np.shape(y):
                raise ValueError('x and y arrays must be the same shape!')
            else:

                if Coords.lower() == 'original':
                    x,y = self.transform.original_to_display_coords(x,y)

                orig_shape = np.shape(x)
                x = np.reshape(x,np.size(x),order='F')
                y = np.reshape(y,np.size(y),order='F')
                RL = np.zeros(np.shape(x))
                RayLength = RayLength.flatten()
                xflat = self.x.flatten()
                yflat = self.y.flatten()
                for pointno in range(x.size):
                    if np.isnan(x[pointno]) or np.isnan(y[pointno]):
                        RL[pointno] = np.nan
                        continue

                    deltaX = xflat - x[pointno]
                    deltaY = yflat - y[pointno]
                    deltaR = np.sqrt(deltaX**2 + deltaY**2)
                    if np.nanmin(deltaR) <= PositionTol:
                        RL[pointno] = RayLength[np.nanargmin(deltaR)]
                    else:
                        raise Exception('No ray-traced pixel within PositionTol of requested pixel!')
                return np.reshape(RL,orig_shape,order='F')


    # Return unit vectors of sight-line direction for each pixel.
    def get_ray_directions(self,x=None,y=None,PositionTol=3,Coords='Display'):
        
        lengths = self.get_ray_lengths()
        dirs = (self.ray_end_coords - self.ray_start_coords) / np.repeat(lengths.reshape(np.shape(lengths)+(1,)),3,axis=-1)

        if x is None and y is None:
            if self.fullchip:
                if Coords.lower() == 'display':
                    return dirs
                else:
                    return self.transform.display_to_original_image(dirs,binning=self.binning)
            else:
                return dirs
        else:
            if self.x is None or self.y is None:
                raise Exception('This ray data does not have x and y pixel indices!')
            if np.shape(x) != np.shape(y):
                raise ValueError('x and y arrays must be the same shape!')
            else:

                if Coords.lower() == 'original':
                    x,y = self.transform.original_to_display_coords(x,y)

                oldshape = np.shape(x)
                x = np.reshape(x,np.size(x),order='F')
                y = np.reshape(y,np.size(y),order='F')
                [dirs_X,dirs_Y,dirs_Z] = np.split(dirs,3,-1)
                dirs_X = dirs_X.flatten()
                dirs_Y = dirs_Y.flatten()
                dirs_Z = dirs_Z.flatten()
                xflat = self.x.flatten()
                yflat = self.y.flatten()
                Xout = np.zeros(np.shape(x))
                Yout = np.zeros(np.shape(x))
                Zout = np.zeros(np.shape(x))
                for pointno in range(x.size):
                    deltaX = xflat - x[pointno]
                    deltaY = yflat - y[pointno]
                    deltaR = np.sqrt(deltaX**2 + deltaY**2)
                    if np.min(deltaR) <= PositionTol:
                        Xout[pointno] = dirs_X[np.argmin(deltaR)]
                        Yout[pointno] = dirs_Y[np.argmin(deltaR)]
                        Zout[pointno] = dirs_Z[np.argmin(deltaR)]
                    else:
                        raise Exception('No ray-traced pixel within PositionTol of requested pixel!')
                out = np.hstack([Xout,Yout,Zout])

                return np.reshape(out,oldshape + (3,),order='F')