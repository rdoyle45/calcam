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
Class for storing 'point pairs': coordinate of matching points
on 2D camera images and 3D CAD models.

Written by Scott Silburn (scott.silburn@ukaea.uk)
"""
 

import numpy as np

# Simple class for storing results.
class PointPairs():
    
    def __init__(self,loadhandle=None):

        self.n_subviews = 0
        self.image_points = []
        self.object_points = []
        
        if loadhandle is not None:
            self.load(loadhandle)


    def get_n_points(self,subview=0):

        if self.n_subviews == 0:
            return 0
            
        if subview > (self.n_subviews - 1) or subview < 0:
            raise ValueError('Subview index out of bounds!')

        npts = 0
        for point in self.image_points:
            if point[subview] is not None:
                npts = npts + 1

        return npts


    # Save point pairs to csv file
    def save(self,savefile):

        # Construct and write the file header and column headings
        fieldheaders = 'World Coordinates [m],,,'
        xyheaders = ''
        for i in range(len(self.image_points[0])):
            fieldheaders = fieldheaders + ',Sub-view {:d},,'.format(i)
            xyheaders = xyheaders + ',,Image X,Image Y'
            
        savefile.write( '{:s}\nMachine X,Machine Y,Machine Z{:s}\n'.format(fieldheaders,xyheaders))

        n_subviews = len(self.image_points[0])

        # Write the point coordinates
        for i in range(len(self.object_points)):

            row = '{:.4f},{:.4f},{:.4f}'.format(self.object_points[i][0],self.object_points[i][1],self.object_points[i][2])
            for j in range(n_subviews):
                if self.image_points[i][j] is None:
                    row = row + ',,,'
                else:
                    row = row + ',,{:.1f},{:.1f}'.format(self.image_points[i][j][0],self.image_points[i][j][1])

            savefile.write(row + '\n')

        savefile.close()



    def add_pointpair(self,obj_point,im_points):

        if self.n_subviews == 0:
            self.n_subviews = len(im_points)
        else:
            if len(im_points) != self.n_subviews:
                raise ValueError('{:d} image point(s) provided; expected {:d}!'.format(len(im_points),self.n_subviews))

        self.object_points.append(obj_point)
        self.image_points.append(im_points)



    def load(self,savefile):


        for headrow in savefile:
            if headrow.startswith('Machine X'):
                break

        # Read header info in second row...
        if not headrow.startswith('Machine X'):
            raise Exception('Header does not look like a Calcam point pairs file!')
        
        self.n_subviews = int(np.floor( (len(headrow.split(',')) - 4) / 2.))

        # Actually read the point pairs
        self.image_points = []
        self.object_points = []
        
        for frow in savefile:
            row = frow.rstrip().split(',')
            self.object_points.append((float(row[0]),float(row[1]),float(row[2])))
            self.image_points.append([])
            for field in range(self.n_subviews):
                if row[1 + (field+1)*3] != '':
                    self.image_points[-1].append( [float(row[1 + (field+1)*3]) , float(row[2 + (field+1)*3])] )
                else:
                    self.image_points[-1].append(None)